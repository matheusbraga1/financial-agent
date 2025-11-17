#!/usr/bin/env python3
"""
GLPI to Qdrant Ingestion Script (Clean Architecture Version)

This script ingests GLPI knowledge base articles into Qdrant vector database
following Clean Architecture principles, SOLID principles, and Clean Code practices.

Architecture:
    - Domain Layer: Business logic and entities
    - Application Layer: Use cases and orchestration
    - Infrastructure Layer: External services and adapters
    - Presentation Layer: CLI interface (this script)

Usage:
    # Full sync with semantic chunking
    python scripts/ingest_glpi_clean.py

    # Clear and reimport everything
    python scripts/ingest_glpi_clean.py --clear

    # Test run without indexing
    python scripts/ingest_glpi_clean.py --dry-run --max-articles 10

    # Use different chunking strategy
    python scripts/ingest_glpi_clean.py --strategy hierarchical
"""
import sys
import logging
import argparse
from pathlib import Path
from typing import NoReturn

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

# Domain imports
from app.domain.document_chunking.intelligent_chunker import (
    IntelligentChunker,
    ChunkConfig,
    ChunkingStrategy
)
from app.domain.services.rag.domain_classifier import DomainClassifier

# Infrastructure imports
from app.infrastructure.adapters.external.glpi_client import GLPIClient
from app.infrastructure.adapters.vector_store.qdrant_adapter import QdrantAdapter
from app.infrastructure.adapters.embeddings.sentence_transformer_adapter import SentenceTransformerAdapter
from app.infrastructure.config.settings import get_settings

# Application imports (our clean architecture modules)
from glpi_ingestion.content_cleaner import create_content_cleaner
from glpi_ingestion.article_processor import create_article_processor
from glpi_ingestion.statistics import create_statistics_tracker
from glpi_ingestion.orchestrator import (
    create_ingestion_orchestrator,
    IngestionConfig
)


def setup_logging() -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # Suppress noisy logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Enhanced GLPI to Qdrant ingestion with intelligent chunking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full sync with semantic chunking (recommended)
  python scripts/ingest_glpi_clean.py

  # Use hierarchical chunking for structured docs
  python scripts/ingest_glpi_clean.py --strategy hierarchical

  # Clear and reimport everything
  python scripts/ingest_glpi_clean.py --clear

  # Test run without indexing
  python scripts/ingest_glpi_clean.py --dry-run --max-articles 10

  # Sync specific article
  python scripts/ingest_glpi_clean.py --article-id 123

  # Use specific embedding model
  python scripts/ingest_glpi_clean.py --embedding-model BGE-M3
        """
    )

    parser.add_argument(
        "--include-private",
        action="store_true",
        help="Include private articles"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing data before import"
    )
    parser.add_argument(
        "--article-id",
        type=int,
        help="Sync only specific article ID"
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        help="Maximum number of articles to process (for testing)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process but don't index (for testing)"
    )
    parser.add_argument(
        "--strategy",
        choices=["semantic", "hierarchical", "sliding_window"],
        default="semantic",
        help="Chunking strategy to use (default: semantic)"
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        help="Override embedding model (e.g., BGE-M3)"
    )

    return parser.parse_args()


def create_dependencies(
    settings,
    embedding_model: str,
    chunking_strategy: ChunkingStrategy
):
    """
    Create and configure all dependencies.

    This function follows Dependency Injection pattern,
    creating all required services and injecting them.

    Args:
        settings: Application settings
        embedding_model: Name of embedding model
        chunking_strategy: Chunking strategy to use

    Returns:
        Tuple of configured services
    """
    logger = logging.getLogger(__name__)

    logger.info("Initializing services...")
    logger.info(f"  - Embedding Model: {embedding_model}")
    logger.info(f"  - Embedding Dimension: {settings.embedding_dimension}")
    logger.info(f"  - Chunking Strategy: {chunking_strategy.value}")

    # Infrastructure Layer - External adapters
    glpi_client = GLPIClient(
        host=settings.glpi_db_host,
        port=settings.glpi_db_port,
        database=settings.glpi_db_name,
        user=settings.glpi_db_user,
        password=settings.glpi_db_password,
        table_prefix=settings.glpi_db_prefix
    )

    embedding_service = SentenceTransformerAdapter(model_name=embedding_model)

    vector_store = QdrantAdapter(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        collection_name=settings.qdrant_collection,
        vector_size=settings.embedding_dimension
    )

    # Domain Layer - Business logic services
    classifier = DomainClassifier()

    chunk_config = ChunkConfig(
        strategy=chunking_strategy,
        min_chunk_size=500,
        max_chunk_size=2000,
        overlap_size=200,
        preserve_sentences=True,
        preserve_paragraphs=True,
        include_title_context=True,
        quality_threshold=0.5
    )
    chunker = IntelligentChunker(chunk_config)

    # Application Layer - Use case services
    content_cleaner = create_content_cleaner(
        min_content_length=settings.glpi_min_content_length
    )

    article_processor = create_article_processor(
        content_cleaner=content_cleaner,
        chunker=chunker,
        classifier=classifier,
        embedding_service=embedding_service,
        vector_store=vector_store,
        embedding_dimension=settings.embedding_dimension
    )

    statistics_tracker = create_statistics_tracker(
        embedding_model=embedding_model,
        embedding_dimension=settings.embedding_dimension,
        chunking_strategy=chunking_strategy.value
    )

    orchestrator = create_ingestion_orchestrator(
        glpi_client=glpi_client,
        article_processor=article_processor,
        statistics_tracker=statistics_tracker,
        vector_store=vector_store,
        collection_name=settings.qdrant_collection
    )

    return orchestrator, glpi_client, article_processor


def sync_single_article(
    article_id: int,
    glpi_client: GLPIClient,
    article_processor,
) -> bool:
    """
    Sync a single article from GLPI.

    Args:
        article_id: GLPI article ID
        glpi_client: GLPI client
        article_processor: Article processor

    Returns:
        True if successful
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Syncing single article: {article_id}")

    try:
        # Fetch article from GLPI
        article = glpi_client.get_article_by_id(article_id)
        if not article:
            logger.error(f"Article {article_id} not found in GLPI")
            return False

        # Process and index
        success, num_chunks, _ = article_processor.process_article(
            article=article,
            dry_run=False
        )

        if success:
            logger.info(
                f"✅ Article {article_id} synced successfully "
                f"({num_chunks} chunks indexed)"
            )
            return True
        else:
            logger.error(f"❌ Failed to index article {article_id}")
            return False

    except Exception as e:
        logger.error(f"Error syncing article {article_id}: {e}", exc_info=True)
        return False


def main() -> NoReturn:
    """
    Main entry point for the script.

    Follows Clean Code principles:
    - Single responsibility (just orchestrates)
    - Clear error handling
    - Proper exit codes
    """
    # Setup
    setup_logging()
    logger = logging.getLogger(__name__)
    args = parse_arguments()
    settings = get_settings()

    # Map strategy string to enum
    strategy_map = {
        "semantic": ChunkingStrategy.SEMANTIC,
        "hierarchical": ChunkingStrategy.HIERARCHICAL,
        "sliding_window": ChunkingStrategy.SLIDING_WINDOW,
    }
    strategy = strategy_map[args.strategy]

    # Determine embedding model
    embedding_model = args.embedding_model or settings.embedding_model

    try:
        # Create dependencies (Dependency Injection)
        orchestrator, glpi_client, article_processor = create_dependencies(
            settings=settings,
            embedding_model=embedding_model,
            chunking_strategy=strategy
        )

        # Handle single article sync
        if args.article_id:
            success = sync_single_article(
                article_id=args.article_id,
                glpi_client=glpi_client,
                article_processor=article_processor
            )
            sys.exit(0 if success else 1)

        # Full sync - create configuration
        config = IngestionConfig(
            include_private=args.include_private,
            clear_existing=args.clear,
            max_articles=args.max_articles,
            dry_run=args.dry_run,
            min_content_length=settings.glpi_min_content_length
        )

        # Run ingestion
        stats = orchestrator.run(config)

        # Exit with appropriate code based on success rate
        if stats.articles_processed > 0:
            sys.exit(0 if stats.is_successful else 1)
        else:
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("\n⚠️ Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
