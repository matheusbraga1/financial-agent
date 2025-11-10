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

# Get service instances
vector_store_service = get_vector_store_instance()
embedding_service = get_embedding_service_instance()


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
        self.chunk_size = 1000
        self.chunk_overlap = 200

    def _split_into_chunks(self, text: str, title: str) -> List[str]:
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
            logger.warning(
                f"Documento '{title}' muito grande ({len(text)} chars), truncando para {MAX_DOCUMENT_SIZE}"
            )
            text = text[:MAX_DOCUMENT_SIZE]

        if len(text) <= self.chunk_size:
            return [text]

        chunks: List[str] = []
        start = 0
        iterations = 0
        step = max(1, self.chunk_size - self.chunk_overlap)
        max_iterations = len(text) // step + 10

        while start < len(text) and iterations < max_iterations:
            iterations += 1
            end = start + self.chunk_size

            if end < len(text):
                snapped = False
                for sep in [". ", "\n", " "]:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep != -1 and last_sep > start:
                        end = last_sep + len(sep)
                        snapped = True
                        break
                if not snapped:
                    end = min(end, len(text))

            chunk = text[start:end].strip()

            if chunk and len(chunk) >= 10:
                chunks.append(chunk)
            else:
                logger.debug(f"Chunk muito curto ignorado: {len(chunk)} chars")

            if end < len(text):
                start = max(end - self.chunk_overlap, start + 1)
            else:
                break

        if iterations >= max_iterations and start < len(text):
            chunks.append(text[start:].strip())
            logger.info(
                f"Documento '{title}' excedeu iterações máximas; resto anexado como último chunk"
            )

        logger.debug(
            f"Documento '{title}' dividido em {len(chunks)} chunks válidos"
        )
        return chunks

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

            for article in articles:
                article_title = article.get("title", "Sem título")
                try:
                    content_chunks = self._split_into_chunks(
                        article.get("content", ""), article_title
                    )
                    if not content_chunks:
                        logger.warning(
                            f"Nenhum chunk gerado para '{article_title}', ignorando"
                        )
                        continue

                    chunks_indexed_for_article = 0
                    for chunk in content_chunks:
                        try:
                            vector = self.embedding.encode_document(
                                title=article_title, content=chunk, title_weight=3
                            )
                        except Exception as embed_error:
                            logger.error(
                                f"Erro ao gerar embedding: {embed_error}"
                            )
                            stats["articles_failed"] += 1
                            continue

                        try:
                            doc_id = self.vector_store.add_document(
                                document=DocumentCreate(
                                    title=article_title,
                                    category=article.get("category") or "Geral",
                                    content=chunk,
                                    metadata=article.get("metadata", {}),
                                ),
                                vector=vector,
                                document_id=None,
                            )
                            logger.debug(f"Chunk indexado com ID: {doc_id}")
                            chunks_indexed_for_article += 1
                        except Exception as chunk_error:
                            logger.error(
                                f"Erro ao processar chunk: {chunk_error}"
                            )
                            stats["articles_failed"] += 1

                    if chunks_indexed_for_article > 0:
                        stats["articles_indexed"] += 1
                        stats["articles_processed"] += 1
                        stats["total_chunks_indexed"] += chunks_indexed_for_article
                        logger.info(
                            f"Artigo indexado ({chunks_indexed_for_article}/{len(content_chunks)} chunk(s))"
                        )
                except Exception as e:
                    stats["articles_failed"] += 1
                    logger.error(f"Erro geral ao processar '{article_title}': {e}")
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
        logger.info(f"Sincronizando artigo {article_id}...")
        try:
            article = self.glpi.get_article_by_id(article_id)
            if not article:
                logger.error(f"Artigo {article_id} não encontrado no GLPI")
                return False

            document = DocumentCreate(
                title=article["title"],
                category=article["category"],
                content=article["content"],
            )
            vector = self.embedding.encode_document(
                title=document.title, content=document.content, title_weight=3
            )
            doc_id = self.vector_store.add_document(
                document=document,
                vector=vector,
                document_id=f"glpi_{article['id']}",
            )
            logger.info(f"Artigo sincronizado com ID: {doc_id}")
            return True
        except Exception as e:
            logger.error(f"Erro ao sincronizar artigo: {e}")
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

