import sys
import os
from datetime import datetime
from typing import Dict

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

class GLPIIngestion:
    def __init__(self):
        self.glpi = GLPIService()
        self.vector_store = vector_store_service
        self.embedding = embedding_service

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

                # Recriar
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

        for i, article in enumerate(articles, 1):
            try:
                logger.info(f"\n[{i}/{len(articles)}] Processando: {article['title']}")

                document = DocumentCreate(
                    title=article['title'],
                    category=article['category'],
                    content=article['content'],
                    metadata=article['metadata']
                )

                logger.debug("   Gerando embedding...")

                vector = self.embedding.encode_document(
                    title=document.title,
                    content=document.content,
                    title_weight=3
                )

                glpi_id = int(article['id'])

                logger.debug("   Salvando no Qdrant...")
                doc_id = self.vector_store.add_document(
                    document=document,
                    vector=vector,
                    document_id=glpi_id
                )

                stats['articles_indexed'] += 1
                logger.info(f"   ✓ Indexado com ID: {doc_id}")

            except Exception as e:
                stats['articles_failed'] += 1
                error_msg = f"Artigo '{article['title']}': {str(e)}"
                stats['errors'].append(error_msg)
                logger.error(f"   ✗ Erro: {e}")
                continue

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
        logger.info(f"❌ Falhas: {stats['articles_failed']}")

        if stats['errors']:
            logger.warning(f"\n⚠️  {len(stats['errors'])} erros encontrados:")
            for error in stats['errors'][:5]:  # Mostrar apenas os 5 primeiros
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

            vector = self.embedding.encode_text(document.content)
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