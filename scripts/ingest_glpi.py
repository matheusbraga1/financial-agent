import sys
import os
from datetime import datetime
from typing import Dict, List
import signal
from contextlib import contextmanager
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.glpi_service import GLPIService
from app.services.vector_store_service import get_vector_store_instance
from app.services.embedding_service import get_embedding_service_instance
from app.models.document import DocumentCreate
from app.core.config import get_settings
from app.domain.value_objects.document_metadata import (
    DocumentMetadata,
    ChunkMetadata,
    Department,
    DocType,
)
from app.domain.services.rag.classification.domain_classifier import DomainClassifier

# Get service instances
vector_store_service = get_vector_store_instance()
embedding_service = get_embedding_service_instance()
domain_classifier = DomainClassifier()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
# Reduz ruído do httpx durante a ingestão
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
settings = get_settings()


class TimeoutException(Exception):
    """Exceção lançada quando uma operação excede o timeout."""


@contextmanager
def timeout(seconds: int):
    """Context manager para timeout de operações."""

    def timeout_handler(signum, frame):
        raise TimeoutException(f"Operação excedeu {seconds} segundos")

    if hasattr(signal, "SIGALRM"):
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    else:
        yield


class GLPIIngestion:
    def __init__(self):
        self.glpi = GLPIService()
        self.vector_store = vector_store_service
        self.embedding = embedding_service
        self.classifier = domain_classifier
        # Optimized for all-MiniLM-L6-v2 (384 dim): ~700 chars with semantic overlap
        self.chunk_size = 700
        self.chunk_overlap = 100

    def _assess_chunk_quality(self, chunk: str) -> float:
        """
        Avalia a qualidade de um chunk (0-1).

        Args:
            chunk: Texto do chunk

        Returns:
            Score de qualidade (0=baixa, 1=alta)
        """
        if not chunk or len(chunk) < 50:
            return 0.0

        # Penalizar chunks muito repetitivos (menus de navegação)
        words = chunk.lower().split()
        if len(words) > 0:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.3:  # Menos de 30% palavras únicas
                return 0.3

        # Penalizar chunks com muitos caracteres especiais
        alpha_chars = sum(c.isalnum() or c.isspace() for c in chunk)
        if len(chunk) > 0:
            alpha_ratio = alpha_chars / len(chunk)
            if alpha_ratio < 0.6:  # Menos de 60% caracteres alfanuméricos
                return 0.4

        # Bonus para chunks com sentenças completas
        sentence_endings = chunk.count('. ') + chunk.count('! ') + chunk.count('? ')
        if sentence_endings >= 2:
            return 1.0

        return 0.8  # Qualidade padrão OK

    def _split_into_chunks(self, text: str, title: str) -> List[Dict[str, any]]:
        """
        Divide texto longo em chunks menores com sobreposição semântica.

        MELHORIA: Inclui título em cada chunk e avalia qualidade.

        Args:
            text: Texto completo do documento
            title: Título do documento

        Returns:
            Lista de dicts com {'text': str, 'quality_score': float}
        """
        if not text or not isinstance(text, str):
            logger.warning(f"Documento '{title}' com texto inválido")
            return []

        text = text.strip()
        if len(text) < 10:
            logger.warning(f"Documento '{title}' muito curto ({len(text)} chars)")
            return []

        MAX_DOCUMENT_SIZE = 50000
        if len(text) > MAX_DOCUMENT_SIZE:
            logger.warning(
                f"Documento '{title}' muito grande ({len(text)} chars), truncando para {MAX_DOCUMENT_SIZE}"
            )
            text = text[:MAX_DOCUMENT_SIZE]

        # MELHORIA: Incluir título no contexto de cada chunk
        title_prefix = f"[{title}]\n\n"

        # Se texto cabe em um chunk, retornar com título
        if len(text) <= (self.chunk_size - len(title_prefix)):
            chunk_with_title = title_prefix + text
            quality = self._assess_chunk_quality(text)
            if quality >= 0.4:  # Threshold mínimo de qualidade
                return [{"text": chunk_with_title, "quality_score": quality}]
            return []

        chunks: List[Dict[str, any]] = []
        start = 0
        iterations = 0
        step = max(1, self.chunk_size - self.chunk_overlap - len(title_prefix))
        max_iterations = len(text) // step + 10

        while start < len(text) and iterations < max_iterations:
            iterations += 1
            # Ajustar tamanho considerando o título
            end = start + (self.chunk_size - len(title_prefix))

            if end < len(text):
                snapped = False
                # MELHORIA: Separadores semânticos ordenados por prioridade
                for sep in ["\n\n", ".\n", ". ", "! ", "? ", "\n", " "]:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep != -1 and last_sep > start + 50:  # Mínimo 50 chars
                        end = last_sep + len(sep)
                        snapped = True
                        break
                if not snapped:
                    end = min(end, len(text))

            chunk_content = text[start:end].strip()

            # Avaliar qualidade do chunk
            quality = self._assess_chunk_quality(chunk_content)

            # MELHORIA: Só incluir chunks com qualidade mínima
            if chunk_content and len(chunk_content) >= 50 and quality >= 0.4:
                chunk_with_title = title_prefix + chunk_content
                chunks.append({
                    "text": chunk_with_title,
                    "quality_score": quality
                })
            else:
                logger.debug(
                    f"Chunk ignorado: len={len(chunk_content)}, quality={quality:.2f}"
                )

            if end < len(text):
                start = max(end - self.chunk_overlap, start + 1)
            else:
                break

        if iterations >= max_iterations and start < len(text):
            remaining = text[start:].strip()
            quality = self._assess_chunk_quality(remaining)
            if len(remaining) >= 50 and quality >= 0.4:
                chunk_with_title = title_prefix + remaining
                chunks.append({
                    "text": chunk_with_title,
                    "quality_score": quality
                })
                logger.info(
                    f"Documento '{title}' excedeu iterações máximas; resto anexado como último chunk"
                )

        avg_quality = sum(c["quality_score"] for c in chunks) / len(chunks) if chunks else 0
        logger.debug(
            f"Documento '{title}' dividido em {len(chunks)} chunks (qualidade média: {avg_quality:.2f})"
        )
        return chunks

    def _classify_department(self, title: str, content: str, glpi_category: str) -> Department:
        """
        Classifica o departamento do artigo baseado em título, conteúdo e categoria GLPI.

        MELHORIA: Usa DomainClassifier para pré-classificar durante ingestão.

        Args:
            title: Título do artigo
            content: Conteúdo completo (truncado para análise)
            glpi_category: Categoria do GLPI

        Returns:
            Department enum
        """
        # Usar primeiros 500 chars do conteúdo para análise
        sample = f"{title} {content[:500]}"

        # Classificar usando o DomainClassifier
        departments = self.classifier.classify(sample, top_n=1)

        if departments:
            return departments[0]

        # Fallback: mapear categoria GLPI para departamento
        category_lower = glpi_category.lower()
        if any(kw in category_lower for kw in ["ti", "tecnologia", "sistema", "email", "senha"]):
            return Department.TI
        elif any(kw in category_lower for kw in ["rh", "recursos humanos", "férias", "ponto"]):
            return Department.RH
        elif any(kw in category_lower for kw in ["financeiro", "pagamento", "nota fiscal"]):
            return Department.FINANCEIRO
        elif any(kw in category_lower for kw in ["loteamento", "lote", "terreno"]):
            return Department.LOTEAMENTO
        elif any(kw in category_lower for kw in ["aluguel", "locação", "imóvel"]):
            return Department.ALUGUEL
        elif any(kw in category_lower for kw in ["jurídico", "contrato", "legal"]):
            return Department.JURIDICO

        return Department.GERAL

    def _determine_doc_type(self, glpi_metadata: dict) -> DocType:
        """
        Determina o tipo de documento baseado nos metadados GLPI.

        Args:
            glpi_metadata: Metadados do GLPI (is_faq, category, etc.)

        Returns:
            DocType enum
        """
        if glpi_metadata.get("is_faq"):
            return DocType.FAQ
        # Por padrão, artigos GLPI são "article"
        return DocType.ARTICLE

    def _extract_tags(self, title: str, content: str, category: str) -> List[str]:
        """
        Extrai tags relevantes do título, conteúdo e categoria.

        MELHORIA: Gera tags automaticamente para melhorar busca.

        Args:
            title: Título do artigo
            content: Conteúdo completo
            category: Categoria GLPI

        Returns:
            Lista de tags
        """
        tags = []

        # Tag da categoria GLPI
        if category and category != "Geral":
            # Pegar subcategorias (e.g., "TI > Email > Config" -> ["TI", "Email", "Config"])
            category_parts = [p.strip() for p in category.split(">")]
            tags.extend(category_parts)

        # Keywords importantes do título (palavras com 4+ chars)
        title_words = [w.lower() for w in title.split() if len(w) >= 4 and w.isalpha()]
        tags.extend(title_words[:5])  # Máximo 5 palavras do título

        # Remover duplicatas mantendo ordem
        seen = set()
        unique_tags = []
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower not in seen:
                seen.add(tag_lower)
                unique_tags.append(tag)

        return unique_tags[:10]  # Máximo 10 tags

    def _build_enhanced_metadata(self, article: dict) -> DocumentMetadata:
        """
        Constrói metadados enriquecidos usando DocumentMetadata.

        MELHORIA: Usa schema adequado com classificação automática.

        Args:
            article: Artigo do GLPI (dict com id, title, content, category, metadata)

        Returns:
            DocumentMetadata completo
        """
        title = article.get("title", "Sem título")
        content = article.get("content", "")
        category = article.get("category", "Geral")
        glpi_meta = article.get("metadata", {})

        # Classificar departamento automaticamente
        department = self._classify_department(title, content, category)

        # Determinar tipo de documento
        doc_type = self._determine_doc_type(glpi_meta)

        # Extrair tags
        tags = self._extract_tags(title, content, category)

        # Construir DocumentMetadata
        metadata = DocumentMetadata(
            source_id=f"glpi_{article['id']}",
            title=title,
            department=department,
            doc_type=doc_type,
            category=category,  # Preservar categoria hierárquica do GLPI
            tags=tags,
            file_format="html",
            created_at=glpi_meta.get("date_creation"),
            updated_at=glpi_meta.get("date_mod"),
            author=glpi_meta.get("source", "GLPI"),
            version="1.0",
            glpi_id=int(article['id']),
            is_public=glpi_meta.get("visibility") == "public",
        )

        logger.debug(
            f"Metadata criado: {title} -> Department={department}, DocType={doc_type}, Tags={len(tags)}"
        )

        return metadata

    def run_full_sync(
        self, include_private: bool = False, clear_existing: bool = False
    ) -> Dict[str, int]:
        logger.info("=" * 70)
        logger.info("INICIANDO SINCRONIZAÇÃO COMPLETA GLPI -> QDRANT")
        logger.info("=" * 70)

        stats: Dict[str, int] = {
            "started_at": datetime.now().isoformat(),
            "total_articles_glpi": 0,
            "articles_processed": 0,
            "articles_indexed": 0,
            "articles_failed": 0,
            "total_chunks_indexed": 0,
        }

        try:
            articles = self.glpi.get_all_articles(
                include_private=include_private,
                min_content_length=settings.glpi_min_content_length,
            )
            stats["total_articles_glpi"] = len(articles)

            if clear_existing:
                try:
                    logger.info("Limpando collection existente no Qdrant...")
                    self.vector_store.client.delete_collection(
                        self.vector_store.collection_name
                    )
                except Exception as e:
                    logger.warning(
                        f"Falha ao deletar collection (pode não existir): {e}"
                    )
                try:
                    self.vector_store._ensure_collection()
                except Exception as e:
                    logger.warning(f"Falha ao recriar collection: {e}")

            for idx, article in enumerate(articles, 1):
                article_title = article.get("title", "Sem título")
                try:
                    # MELHORIA: Construir metadados enriquecidos primeiro
                    doc_metadata = self._build_enhanced_metadata(article)

                    # MELHORIA: Dividir em chunks com qualidade e título incluído
                    chunk_dicts = self._split_into_chunks(
                        article.get("content", ""), article_title
                    )
                    if not chunk_dicts:
                        logger.warning(
                            f"[{idx}/{stats['total_articles_glpi']}] Nenhum chunk gerado para '{article_title}', ignorando"
                        )
                        continue

                    chunks_indexed_for_article = 0
                    for chunk_idx, chunk_dict in enumerate(chunk_dicts):
                        chunk_text = chunk_dict["text"]
                        quality_score = chunk_dict["quality_score"]

                        try:
                            # MELHORIA: Usar encode_text direto, título já está no chunk_text
                            vector = self.embedding.encode_text(chunk_text)
                        except Exception as embed_error:
                            logger.error(
                                f"Erro ao gerar embedding para chunk {chunk_idx}: {embed_error}"
                            )
                            continue

                        try:
                            # Criar ChunkMetadata completo
                            chunk_metadata = ChunkMetadata.from_document_metadata(
                                doc_metadata=doc_metadata,
                                chunk_index=chunk_idx,
                                total_chunks=len(chunk_dicts),
                                text=chunk_text
                            )

                            # Adicionar quality_score ao metadata dict
                            metadata_dict = chunk_metadata.model_dump()
                            metadata_dict["quality_score"] = quality_score

                            # Indexar no Qdrant
                            doc_id = self.vector_store.add_document(
                                document=DocumentCreate(
                                    title=article_title,
                                    category=doc_metadata.category or "Geral",
                                    content=chunk_text,
                                    metadata=metadata_dict,
                                ),
                                vector=vector,
                                document_id=None,
                            )
                            logger.debug(
                                f"Chunk {chunk_idx+1}/{len(chunk_dicts)} indexado com ID: {doc_id} "
                                f"(quality={quality_score:.2f}, dept={doc_metadata.department})"
                            )
                            chunks_indexed_for_article += 1
                        except Exception as chunk_error:
                            logger.error(
                                f"Erro ao indexar chunk {chunk_idx}: {chunk_error}"
                            )

                    if chunks_indexed_for_article > 0:
                        stats["articles_indexed"] += 1
                        stats["articles_processed"] += 1
                        stats["total_chunks_indexed"] += chunks_indexed_for_article
                        logger.info(
                            f"[{idx}/{stats['total_articles_glpi']}] '{article_title}' indexado "
                            f"({chunks_indexed_for_article}/{len(chunk_dicts)} chunks, "
                            f"dept={doc_metadata.department}, tags={len(doc_metadata.tags)})"
                        )
                    else:
                        stats["articles_failed"] += 1

                except Exception as e:
                    stats["articles_failed"] += 1
                    logger.error(f"[{idx}/{stats['total_articles_glpi']}] Erro geral ao processar '{article_title}': {e}")
                    continue

            logger.info("\nVerificando resultado...")
            try:
                info = self.vector_store.get_collection_info()
                logger.info(
                    f"   Total de documentos no Qdrant: {info.get('vectors_count')}"
                )
            except Exception as e:
                logger.error(f"   Erro ao verificar: {e}")

            stats["finished_at"] = datetime.now().isoformat()

            logger.info("\n" + "=" * 70)
            logger.info("RESUMO DA SINCRONIZAÇÃO")
            logger.info("=" * 70)
            logger.info(f"Artigos no GLPI: {stats['total_articles_glpi']}")
            logger.info(f"Artigos extraídos: {stats['articles_processed']}")
            logger.info(f"Indexados com sucesso: {stats['articles_indexed']}")
            logger.info(
                f"Total de chunks indexados: {stats.get('total_chunks_indexed', 0)}"
            )
            logger.info(f"Falhas: {stats['articles_failed']}")

            success_rate = (
                stats["articles_indexed"] / stats["articles_processed"] * 100
                if stats["articles_processed"] > 0
                else 0
            )

            if success_rate >= 90:
                logger.info(
                    f"Sincronização concluída com sucesso! ({success_rate:.1f}%)"
                )
            elif success_rate >= 50:
                logger.warning(
                    f"Sincronização concluída com avisos ({success_rate:.1f}%)"
                )
            else:
                logger.error(
                    f"Sincronização com muitas falhas ({success_rate:.1f}%)"
                )

            return stats

        except Exception as e:
            logger.error(f"Erro na sincronização: {e}")
            raise

    def sync_single_article(self, article_id: int) -> bool:
        """
        Sincroniza um único artigo do GLPI usando metadados enriquecidos.

        MELHORIA: Usa mesmo processo de chunking e metadata do sync completo.
        """
        logger.info(f"Sincronizando artigo {article_id}...")
        try:
            article = self.glpi.get_article_by_id(article_id)
            if not article:
                logger.error(f"Artigo {article_id} não encontrado no GLPI")
                return False

            # Construir metadados enriquecidos
            doc_metadata = self._build_enhanced_metadata(article)

            # Dividir em chunks com qualidade
            chunk_dicts = self._split_into_chunks(
                article.get("content", ""), article["title"]
            )

            if not chunk_dicts:
                logger.warning(f"Nenhum chunk gerado para artigo {article_id}")
                return False

            # Indexar cada chunk
            chunks_indexed = 0
            for chunk_idx, chunk_dict in enumerate(chunk_dicts):
                chunk_text = chunk_dict["text"]
                quality_score = chunk_dict["quality_score"]

                # Gerar embedding (título já está no chunk)
                vector = self.embedding.encode_text(chunk_text)

                # Criar ChunkMetadata
                chunk_metadata = ChunkMetadata.from_document_metadata(
                    doc_metadata=doc_metadata,
                    chunk_index=chunk_idx,
                    total_chunks=len(chunk_dicts),
                    text=chunk_text
                )

                metadata_dict = chunk_metadata.model_dump()
                metadata_dict["quality_score"] = quality_score

                # Indexar
                doc_id = self.vector_store.add_document(
                    document=DocumentCreate(
                        title=article["title"],
                        category=doc_metadata.category or "Geral",
                        content=chunk_text,
                        metadata=metadata_dict,
                    ),
                    vector=vector,
                    document_id=None,
                )
                logger.debug(f"Chunk {chunk_idx+1} indexado com ID: {doc_id}")
                chunks_indexed += 1

            logger.info(
                f"Artigo {article_id} sincronizado com sucesso "
                f"({chunks_indexed} chunks, dept={doc_metadata.department})"
            )
            return True

        except Exception as e:
            logger.error(f"Erro ao sincronizar artigo {article_id}: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Importar artigos do GLPI para o Qdrant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  # Sincronização completa (padrão)
  python scripts/ingest_glpi.py

  # Limpar dados existentes e reimportar tudo
  python scripts/ingest_glpi.py --clear

  # Incluir artigos privados
  python scripts/ingest_glpi.py --include-private

  # Sincronizar apenas um artigo específico
  python scripts/ingest_glpi.py --article-id 123
        """
    )
    parser.add_argument(
        "--include-private", action="store_true", help="Incluir artigos privados"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Limpar dados existentes antes de importar",
    )
    parser.add_argument(
        "--article-id", type=int, help="Sincronizar apenas um artigo específico"
    )

    args = parser.parse_args()

    try:
        ingestion = GLPIIngestion()
        if args.article_id:
            success = ingestion.sync_single_article(args.article_id)
            sys.exit(0 if success else 1)
        else:
            stats = ingestion.run_full_sync(
                include_private=args.include_private, clear_existing=args.clear
            )
            success_rate = (
                stats["articles_indexed"] / stats["articles_processed"] * 100
                if stats["articles_processed"] > 0
                else 0
            )
            sys.exit(0 if success_rate >= 90 else 1)
    except KeyboardInterrupt:
        logger.info("\nOperação cancelada pelo usuário")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\nErro fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

