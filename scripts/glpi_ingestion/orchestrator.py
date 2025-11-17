"""
Ingestion Orchestrator Module

Responsible for orchestrating the full GLPI ingestion process.
Follows Single Responsibility Principle and Open/Closed Principle.
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from app.infrastructure.adapters.external.glpi_client import GLPIClient
from app.infrastructure.adapters.vector_store.qdrant_adapter import QdrantAdapter

from .article_processor import ArticleProcessor
from .statistics import StatisticsTracker, IngestionStatistics

logger = logging.getLogger(__name__)


@dataclass
class IngestionConfig:
    """
    Configuration for ingestion process.
    Immutable configuration object.
    """
    include_private: bool = False
    clear_existing: bool = False
    max_articles: Optional[int] = None
    dry_run: bool = False
    min_content_length: int = 50


class IngestionOrchestrator:
    """
    Orchestrates the GLPI to Qdrant ingestion process.

    This class is responsible for:
    - Fetching articles from GLPI
    - Managing collection lifecycle
    - Coordinating article processing
    - Tracking overall statistics
    - Providing progress updates

    Follows Open/Closed Principle - extensible without modification.
    """

    def __init__(
        self,
        glpi_client: GLPIClient,
        article_processor: ArticleProcessor,
        statistics_tracker: StatisticsTracker,
        vector_store: QdrantAdapter,
        collection_name: str
    ):
        """
        Initialize orchestrator with dependencies.

        Args:
            glpi_client: Client for fetching GLPI articles
            article_processor: Processor for individual articles
            statistics_tracker: Tracker for statistics
            vector_store: Vector store adapter
            collection_name: Name of the Qdrant collection
        """
        self.glpi_client = glpi_client
        self.article_processor = article_processor
        self.stats_tracker = statistics_tracker
        self.vector_store = vector_store
        self.collection_name = collection_name

    def run(self, config: IngestionConfig) -> IngestionStatistics:
        """
        Execute the full ingestion process.

        Args:
            config: Ingestion configuration

        Returns:
            Final statistics
        """
        self._log_configuration(config)

        # Fetch articles
        articles = self._fetch_articles(config)

        # Prepare collection
        if config.clear_existing and not config.dry_run:
            self._clear_collection()

        if not config.dry_run:
            self._ensure_collection_exists()

        # Process articles
        self._process_articles(articles, config.dry_run)

        # Finalize and report
        return self._finalize_and_report(config.dry_run)

    def _log_configuration(self, config: IngestionConfig) -> None:
        """Log ingestion configuration."""
        logger.info("=" * 80)
        logger.info("ENHANCED GLPI → QDRANT SYNCHRONIZATION")
        logger.info("=" * 80)
        logger.info(f"Configuration:")
        logger.info(f"  - Embedding Model: {self.stats_tracker._stats.embedding_model}")
        logger.info(f"  - Embedding Dimensions: {self.stats_tracker._stats.embedding_dimension}")
        logger.info(f"  - Chunking Strategy: {self.stats_tracker._stats.chunking_strategy}")
        logger.info(f"  - Include Private: {config.include_private}")
        logger.info(f"  - Clear Existing: {config.clear_existing}")
        logger.info(f"  - Dry Run: {config.dry_run}")
        logger.info("=" * 80)

    def _fetch_articles(self, config: IngestionConfig) -> List[Dict[str, Any]]:
        """
        Fetch articles from GLPI.

        Args:
            config: Ingestion configuration

        Returns:
            List of articles
        """
        logger.info("Fetching articles from GLPI...")

        articles = self.glpi_client.get_all_articles(
            include_private=config.include_private,
            min_content_length=config.min_content_length
        )

        # Apply limit if specified
        if config.max_articles:
            articles = articles[:config.max_articles]

        self.stats_tracker.set_total_articles(len(articles))
        logger.info(f"Found {len(articles)} articles to process")

        return articles

    def _clear_collection(self) -> None:
        """Clear existing collection."""
        try:
            logger.info("Clearing existing collection...")
            self.vector_store.client.delete_collection(self.collection_name)
            self.vector_store.ensure_collection()
            logger.info("Collection cleared and recreated")
        except Exception as e:
            logger.warning(f"Failed to clear collection: {e}")

    def _ensure_collection_exists(self) -> None:
        """Ensure the collection exists."""
        self.vector_store.ensure_collection()

    def _process_articles(
        self,
        articles: List[Dict[str, Any]],
        dry_run: bool
    ) -> None:
        """
        Process all articles.

        Args:
            articles: List of articles to process
            dry_run: Whether to skip actual indexing
        """
        total = len(articles)

        for idx, article in enumerate(articles, 1):
            title = article.get("title", "Sem título")

            try:
                logger.info(f"[{idx}/{total}] Processing: {title[:60]}...")

                success, num_chunks, chunk_sizes = self.article_processor.process_article(
                    article=article,
                    dry_run=dry_run
                )

                if success:
                    self.stats_tracker.record_article_processed(num_chunks, chunk_sizes)

                    if not dry_run:
                        self.stats_tracker.record_article_indexed(num_chunks)
                        logger.info(f"  ✓ Indexed {num_chunks} chunks successfully")
                    else:
                        avg_size = sum(chunk_sizes) / len(chunk_sizes) if chunk_sizes else 0
                        logger.info(
                            f"  ✓ Would create {num_chunks} chunks "
                            f"(avg size: {avg_size:.0f} chars)"
                        )
                else:
                    self.stats_tracker.record_article_failed()
                    logger.warning(f"  ✗ Failed to process article")

            except Exception as e:
                self.stats_tracker.record_article_failed()
                logger.error(f"  ✗ Error processing article: {e}")
                continue

    def _finalize_and_report(self, dry_run: bool) -> IngestionStatistics:
        """
        Finalize statistics and print report.

        Args:
            dry_run: Whether this was a dry run

        Returns:
            Final statistics
        """
        # Verify results if not dry run
        if not dry_run:
            try:
                collection_info = self.vector_store.get_collection_info()
                logger.info(f"\nCollection Status:")
                logger.info(f"  - Vectors in Qdrant: {collection_info.get('vectors_count', 0)}")
                logger.info(f"  - Collection exists: {collection_info.get('exists', False)}")
            except Exception as e:
                logger.error(f"Failed to get collection info: {e}")

        # Finalize statistics first
        final_stats = self.stats_tracker.finalize(is_dry_run=dry_run)

        # Then print summary
        self.stats_tracker.print_summary()

        # Return finalized statistics
        return final_stats


def create_ingestion_orchestrator(
    glpi_client: GLPIClient,
    article_processor: ArticleProcessor,
    statistics_tracker: StatisticsTracker,
    vector_store: QdrantAdapter,
    collection_name: str
) -> IngestionOrchestrator:
    """
    Factory function to create an IngestionOrchestrator.

    Args:
        glpi_client: GLPI client
        article_processor: Article processor
        statistics_tracker: Statistics tracker
        vector_store: Vector store adapter
        collection_name: Collection name

    Returns:
        Configured IngestionOrchestrator instance
    """
    return IngestionOrchestrator(
        glpi_client=glpi_client,
        article_processor=article_processor,
        statistics_tracker=statistics_tracker,
        vector_store=vector_store,
        collection_name=collection_name
    )
