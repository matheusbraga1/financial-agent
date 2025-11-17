"""
Statistics Tracking Module

Responsible for tracking and reporting ingestion statistics.
Follows Single Responsibility Principle.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


@dataclass
class IngestionStatistics:
    """
    Immutable statistics container for ingestion process.
    """
    started_at: str
    finished_at: Optional[str] = None
    total_articles_glpi: int = 0
    articles_processed: int = 0
    articles_indexed: int = 0
    articles_failed: int = 0
    total_chunks_created: int = 0
    total_chunks_indexed: int = 0
    avg_chunk_size: float = 0.0
    avg_chunks_per_doc: float = 0.0
    embedding_model: str = ""
    embedding_dimension: int = 0
    chunking_strategy: str = ""

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.articles_processed == 0:
            return 0.0
        return (self.articles_indexed / self.articles_processed) * 100

    @property
    def is_successful(self) -> bool:
        """Check if ingestion was successful (>= 70% success rate)."""
        return self.success_rate >= 70.0


class StatisticsTracker:
    """
    Tracks statistics during the ingestion process.

    This class is responsible for:
    - Accumulating statistics during processing
    - Calculating aggregates
    - Providing reports
    """

    def __init__(
        self,
        embedding_model: str,
        embedding_dimension: int,
        chunking_strategy: str
    ):
        """
        Initialize statistics tracker.

        Args:
            embedding_model: Name of the embedding model
            embedding_dimension: Dimension of embeddings
            chunking_strategy: Strategy used for chunking
        """
        self._stats = IngestionStatistics(
            started_at=datetime.now().isoformat(),
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
            chunking_strategy=chunking_strategy
        )
        self._chunk_sizes: List[int] = []
        self._chunks_per_doc: List[int] = []

    def set_total_articles(self, count: int) -> None:
        """Set total number of articles from GLPI."""
        self._stats.total_articles_glpi = count

    def record_article_processed(self, num_chunks: int, chunk_sizes: List[int]) -> None:
        """
        Record a successfully processed article.

        Args:
            num_chunks: Number of chunks created
            chunk_sizes: List of chunk sizes
        """
        self._stats.articles_processed += 1
        self._stats.total_chunks_created += num_chunks
        self._chunks_per_doc.append(num_chunks)
        self._chunk_sizes.extend(chunk_sizes)

    def record_article_indexed(self, num_chunks_indexed: int) -> None:
        """
        Record a successfully indexed article.

        Args:
            num_chunks_indexed: Number of chunks successfully indexed
        """
        self._stats.articles_indexed += 1
        self._stats.total_chunks_indexed += num_chunks_indexed

    def record_article_failed(self) -> None:
        """Record a failed article."""
        self._stats.articles_failed += 1

    def finalize(self, is_dry_run: bool = False) -> IngestionStatistics:
        """
        Finalize statistics and return immutable snapshot.

        Args:
            is_dry_run: Whether this was a dry run

        Returns:
            Immutable IngestionStatistics object
        """
        self._stats.finished_at = datetime.now().isoformat()

        # Calculate averages
        if self._chunk_sizes:
            self._stats.avg_chunk_size = sum(self._chunk_sizes) / len(self._chunk_sizes)

        if self._chunks_per_doc:
            self._stats.avg_chunks_per_doc = sum(self._chunks_per_doc) / len(self._chunks_per_doc)

        # In dry run, articles are processed but not indexed
        # So we should treat processed as indexed for success rate calculation
        if is_dry_run and self._stats.articles_processed > 0:
            self._stats.articles_indexed = self._stats.articles_processed

        return self._stats

    def print_summary(self) -> None:
        """Print a formatted summary of statistics."""
        stats = self._stats

        logger.info("\n" + "=" * 80)
        logger.info("INGESTION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Articles in GLPI:        {stats.total_articles_glpi}")
        logger.info(f"Articles Processed:      {stats.articles_processed}")
        logger.info(f"Articles Indexed:        {stats.articles_indexed}")
        logger.info(f"Articles Failed:         {stats.articles_failed}")
        logger.info(f"Total Chunks Created:    {stats.total_chunks_created}")
        logger.info(f"Total Chunks Indexed:    {stats.total_chunks_indexed}")
        logger.info(f"Avg Chunk Size:          {stats.avg_chunk_size:.0f} chars")
        logger.info(f"Avg Chunks per Doc:      {stats.avg_chunks_per_doc:.1f}")
        logger.info(f"Embedding Model:         {stats.embedding_model}")
        logger.info(f"Embedding Dimension:     {stats.embedding_dimension}")
        logger.info(f"Chunking Strategy:       {stats.chunking_strategy}")

        # Success rate
        if stats.articles_processed > 0:
            success_rate = stats.success_rate
            logger.info(f"Success Rate:            {success_rate:.1f}%")

            if success_rate >= 90:
                logger.info("✅ Synchronization completed successfully!")
            elif success_rate >= 70:
                logger.warning("⚠️ Synchronization completed with warnings")
            else:
                logger.error("❌ Synchronization had significant failures")


def create_statistics_tracker(
    embedding_model: str,
    embedding_dimension: int,
    chunking_strategy: str
) -> StatisticsTracker:
    """
    Factory function to create a StatisticsTracker.

    Args:
        embedding_model: Name of the embedding model
        embedding_dimension: Dimension of embeddings
        chunking_strategy: Strategy used for chunking

    Returns:
        Configured StatisticsTracker instance
    """
    return StatisticsTracker(
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        chunking_strategy=chunking_strategy
    )
