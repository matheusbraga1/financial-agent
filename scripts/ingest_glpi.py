import sys
import os
from datetime import datetime
from typing import Dict
import signal
from contextlib import contextmanager

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.glpi_service import GLPIService
from app.services.vector_store_service import vector_store_service
from app.services.embedding_service import embedding_service
from app.models.document import DocumentCreate
from app.core.config import get_settings
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
settings = get_settings()

class TimeoutException(Exception):
    """Exceção lançada quando uma operação excede o timeout."""
    pass

@contextmanager
def timeout(seconds):
    """Context manager para timeout de operações."""
    def timeout_handler(signum, frame):
        raise TimeoutException(f"Operação excedeu {seconds} segundos")

    if hasattr(signal, 'SIGALRM'):
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
        self.chunk_size = 1000
        self.chunk_overlap = 200

    def _split_into_chunks(self, text: str, title: str) -> list:
        """
        Divide texto longo em chunks menores com sobreposição.

        Args:
            text: Texto completo do documento
            title: Título do documento

        Returns:
            Lista de chunks de texto
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
            logger.warning(f"Documento '{title}' muito grande ({len(text)} chars), truncando para {MAX_DOCUMENT_SIZE}")
            text = text[:MAX_DOCUMENT_SIZE]

        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0
        iterations = 0
        max_iterations = len(text) // (self.chunk_size - self.chunk_overlap) + 10

        while start < len(text) and iterations < max_iterations:
            iterations += 1
            end = start + self.chunk_size

            if end < len(text):
                for sep in ['. ', '\n', ' ']:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep != -1 and last_sep > start:
                        end = last_sep + len(sep)
                        break

            chunk = text[start:end].strip()

            if chunk and len(chunk) >= 10:
                chunks.append(chunk)
            else:
                logger.debug(f"Chunk muito curto ignorado: {len(chunk)} chars")

            if end < len(text):
                start = max(end - self.chunk_overlap, start + 1)
            else:
                break

        if iterations >= max_iterations:
            logger.warning(f"Documento '{title}' excedeu iterações máximas de chunking")

        logger.debug(f"Documento '{title}' dividido em {len(chunks)} chunks válidos")
        return chunks

    def run_full_sync(
            self,
            include_private: bool = False,
            clear_existing: bool = False
    ) -> Dict[str, int]:
        logger.info("=" * 70)
        logger.info("INICIANDO SINCRONIZAÇÃO COMPLETA GLPI → QDRANT")
        logger.info("=" * 70)

        stats = {
            'started_at': datetime.now().isoformat(),
            'total_articles_glpi': 0,
            'articles_processed': 0,
            'articles_indexed': 0,
            'articles_skipped': 0,
            'articles_failed': 0,
            'errors': []
        }

        logger.info("\n📡 Testando conexão com GLPI...")
        if not self.glpi.test_connection():
            logger.error("❌ Falha na conexão com GLPI")
            return stats

        glpi_stats = self.glpi.get_stats()
        stats['total_articles_glpi'] = glpi_stats.get('total_articles', 0)

        logger.info(f"\n📊 Estatísticas do GLPI:")
        logger.info(f"   Total de artigos: {glpi_stats.get('total_articles', 0)}")
        logger.info(f"   Artigos públicos: {glpi_stats.get('public_articles', 0)}")
        logger.info(f"   Artigos FAQ: {glpi_stats.get('faq_articles', 0)}")
        logger.info(f"   Categorias: {glpi_stats.get('total_categories', 0)}")

        if clear_existing:
            logger.info("\n🗑️  Limpando collection existente...")
            try:
                from qdrant_client import QdrantClient
                client = QdrantClient(
                    host=settings.qdrant_host,
                    port=settings.qdrant_port
                )
                client.delete_collection(settings.qdrant_collection)
                logger.info("   ✓ Collection deletada")

                self.vector_store._ensure_collection()
                logger.info("   ✓ Collection recriada")
            except Exception as e:
                logger.error(f"   ✗ Erro ao limpar collection: {e}")
                stats['errors'].append(str(e))

        logger.info(f"\n📥 Extraindo artigos do GLPI...")
        logger.info(f"   Incluir privados: {include_private}")
        logger.info(f"   Tamanho mínimo: {settings.glpi_min_content_length} caracteres")

        try:
            articles = self.glpi.get_all_articles(
                include_private=include_private,
                min_content_length=settings.glpi_min_content_length
            )
            stats['articles_processed'] = len(articles)
            logger.info(f"   ✓ {len(articles)} artigos extraídos")
        except Exception as e:
            logger.error(f"   ✗ Erro ao extrair artigos: {e}")
            stats['errors'].append(f"Extração: {str(e)}")
            return stats

        if not articles:
            logger.warning("⚠️  Nenhum artigo encontrado para indexar")
            return stats

        logger.info(f"\n🔄 Indexando artigos no Qdrant...")

        total_chunks_indexed = 0
        start_time = datetime.now()

        for i, article in enumerate(articles, 1):
            if i % 10 == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                avg_time = elapsed / i
                remaining = (len(articles) - i) * avg_time
                logger.info(f"\n⏱️ Progresso: {i}/{len(articles)} ({i/len(articles)*100:.1f}%) - Tempo estimado restante: {remaining/60:.1f}min")
            article_title = article.get('title', 'Sem título')
            try:
                logger.info(f"\n[{i}/{len(articles)}] Processando: {article_title}")

                if not article.get('content') or len(article['content'].strip()) < 10:
                    logger.warning(f"   ⚠️ Artigo '{article_title}' sem conteúdo válido, ignorando")
                    stats['articles_skipped'] += 1
                    continue

                try:
                    content_chunks = self._split_into_chunks(
                        article['content'],
                        article_title
                    )
                except Exception as chunk_error:
                    logger.error(f"   ✗ Erro ao dividir em chunks: {chunk_error}")
                    stats['articles_failed'] += 1
                    stats['errors'].append(f"Chunking '{article_title}': {str(chunk_error)}")
                    continue

                if not content_chunks:
                    logger.warning(f"   ⚠️ Nenhum chunk gerado para '{article_title}', ignorando")
                    stats['articles_skipped'] += 1
                    continue

                if len(content_chunks) > 1:
                    logger.info(f"   📄 Documento dividido em {len(content_chunks)} chunks")

                chunks_indexed_for_article = 0
                for chunk_idx, chunk_content in enumerate(content_chunks):
                    try:
                        if not chunk_content or len(chunk_content.strip()) < 10:
                            logger.warning(f"   ⚠️ Chunk {chunk_idx} vazio, ignorando")
                            continue

                        chunk_metadata = article['metadata'].copy()
                        chunk_metadata['is_chunk'] = len(content_chunks) > 1
                        chunk_metadata['chunk_index'] = chunk_idx
                        chunk_metadata['total_chunks'] = len(content_chunks)

                        document = DocumentCreate(
                            title=article_title,
                            category=article['category'],
                            content=chunk_content,
                            metadata=chunk_metadata
                        )

                        logger.debug(f"   Gerando embedding para chunk {chunk_idx + 1}/{len(content_chunks)}...")

                        try:
                            vector = self.embedding.encode_document(
                                title=document.title,
                                content=document.content,
                                title_weight=3
                            )
                        except Exception as embed_error:
                            logger.error(f"   ✗ Erro ao gerar embedding: {embed_error}")
                            raise

                        if not vector or len(vector) != settings.embedding_dimension:
                            logger.error(f"   ✗ Vetor inválido gerado (tamanho: {len(vector) if vector else 0})")
                            continue

                        base_id = int(article['id'])
                        glpi_id = (base_id * 1000) + chunk_idx

                        logger.debug("   Salvando no Qdrant...")
                        doc_id = self.vector_store.add_document(
                            document=document,
                            vector=vector,
                            document_id=glpi_id
                        )

                        total_chunks_indexed += 1
                        chunks_indexed_for_article += 1
                        logger.debug(f"   ✓ Chunk indexado com ID: {doc_id}")

                    except Exception as chunk_error:
                        logger.error(f"   ✗ Erro ao processar chunk {chunk_idx}: {chunk_error}")
                        continue

                if chunks_indexed_for_article > 0:
                    stats['articles_indexed'] += 1
                    logger.info(f"   ✓ Artigo indexado ({chunks_indexed_for_article}/{len(content_chunks)} chunk(s))")
                else:
                    stats['articles_failed'] += 1
                    error_msg = f"Nenhum chunk indexado para '{article_title}'"
                    stats['errors'].append(error_msg)
                    logger.error(f"   ✗ {error_msg}")

            except Exception as e:
                stats['articles_failed'] += 1
                error_msg = f"Artigo '{article_title}': {str(e)}"
                stats['errors'].append(error_msg)
                logger.error(f"   ✗ Erro geral: {e}")
                continue

        stats['total_chunks_indexed'] = total_chunks_indexed

        logger.info("\n📊 Verificando resultado...")
        try:
            info = self.vector_store.get_collection_info()
            logger.info(f"   Total de documentos no Qdrant: {info['vectors_count']}")
        except Exception as e:
            logger.error(f"   Erro ao verificar: {e}")

        stats['finished_at'] = datetime.now().isoformat()

        logger.info("\n" + "=" * 70)
        logger.info("RESUMO DA SINCRONIZAÇÃO")
        logger.info("=" * 70)
        logger.info(f"Artigos no GLPI: {stats['total_articles_glpi']}")
        logger.info(f"Artigos extraídos: {stats['articles_processed']}")
        logger.info(f"✅ Indexados com sucesso: {stats['articles_indexed']}")
        logger.info(f"📄 Total de chunks indexados: {stats.get('total_chunks_indexed', 0)}")
        logger.info(f"❌ Falhas: {stats['articles_failed']}")

        if stats['errors']:
            logger.warning(f"\n⚠️  {len(stats['errors'])} erros encontrados:")
            for error in stats['errors'][:5]:
                logger.warning(f"   - {error}")
            if len(stats['errors']) > 5:
                logger.warning(f"   ... e mais {len(stats['errors']) - 5} erros")

        logger.info("=" * 70)

        success_rate = (stats['articles_indexed'] / stats['articles_processed'] * 100) if stats['articles_processed'] > 0 else 0

        if success_rate >= 90:
            logger.info(f"✅ Sincronização concluída com sucesso! ({success_rate:.1f}%)")
        elif success_rate >= 50:
            logger.warning(f"⚠️  Sincronização concluída com avisos ({success_rate:.1f}%)")
        else:
            logger.error(f"❌ Sincronização com muitas falhas ({success_rate:.1f}%)")

        return stats

    def sync_single_article(self, article_id: int) -> bool:
        logger.info(f"Sincronizando artigo {article_id}...")

        try:
            article = self.glpi.get_article_by_id(article_id)

            if not article:
                logger.error(f"Artigo {article_id} não encontrado no GLPI")
                return False

            document = DocumentCreate(
                title=article['title'],
                category=article['category'],
                content=article['content']
            )

            vector = self.embedding.encode_document(
                title=document.title,
                content=document.content,
                title_weight=3
            )
            doc_id = self.vector_store.add_document(
                document=document,
                vector=vector,
                document_id=f"glpi_{article['id']}"
            )

            logger.info(f"✓ Artigo sincronizado com ID: {doc_id}")
            return True

        except Exception as e:
            logger.error(f"Erro ao sincronizar artigo: {e}")
            return False

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Importar artigos do GLPI para o Qdrant'
    )
    parser.add_argument(
        '--include-private',
        action='store_true',
        help='Incluir artigos privados'
    )
    parser.add_argument(
        '--clear',
        action='store_true',
        help='Limpar dados existentes antes de importar'
    )
    parser.add_argument(
        '--article-id',
        type=int,
        help='Sincronizar apenas um artigo específico'
    )

    args = parser.parse_args()

    try:
        ingestion = GLPIIngestion()

        if args.article_id:
            success = ingestion.sync_single_article(args.article_id)
            sys.exit(0 if success else 1)
        else:
            stats = ingestion.run_full_sync(
                include_private=args.include_private,
                clear_existing=args.clear
            )

            success_rate = (stats['articles_indexed'] / stats['articles_processed'] * 100) if stats[
                                                                                                  'articles_processed'] > 0 else 0
            sys.exit(0 if success_rate >= 90 else 1)

    except KeyboardInterrupt:
        logger.info("\n⚠️  Operação cancelada pelo usuário")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\n❌ Erro fatal: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
