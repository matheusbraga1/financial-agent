import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
import logging
import argparse
from dataclasses import dataclass, asdict
import json
import unicodedata

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

# Import domain services
from app.domain.document_chunking.intelligent_chunker import (
    IntelligentChunker,
    ChunkConfig,
    ChunkingStrategy,
    DocumentChunk
)
from app.domain.documents.metadata_schema import (
    DocumentMetadata,
    ChunkMetadata,
    Department,
    DocType,
)
from app.domain.services.rag.classification.domain_classifier import DomainClassifier

# Import infrastructure services
from app.infrastructure.adapters.external.glpi_client import GLPIService
from app.infrastructure.adapters.vector_store.qdrant_adapter import QdrantAdapter
from app.infrastructure.adapters.embeddings.sentence_transformer_adapter import EmbeddingService
from app.models.document import DocumentCreate
from app.infrastructure.config.settings import get_settings
from app.core.logging import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Get settings
settings = get_settings()


@dataclass
class IngestionStats:
    """Statistics for ingestion process."""
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


class EnhancedGLPIIngestion:
    """Enhanced GLPI ingestion with intelligent chunking and proper embeddings."""

    @staticmethod
    def _sanitize_payload_value(value: Any) -> Any:
        """
        Recursively sanitize payload values to ensure they are JSON-safe.

        This handles:
        - Unicode normalization for strings
        - Encoding validation
        - Nested dictionaries and lists
        - Special characters that might cause issues

        Args:
            value: Any value to sanitize

        Returns:
            Sanitized value safe for JSON serialization and Qdrant storage
        """
        if value is None:
            return None

        if isinstance(value, str):
            # Normalize Unicode to NFC
            value = unicodedata.normalize('NFC', value)

            # Ensure valid UTF-8 encoding
            try:
                value = value.encode('utf-8', errors='ignore').decode('utf-8')
            except (UnicodeEncodeError, UnicodeDecodeError):
                logger.warning(f"Failed to encode string, using ASCII: {value[:50]}...")
                value = value.encode('ascii', errors='ignore').decode('ascii')

            return value

        elif isinstance(value, dict):
            # Recursively sanitize dictionary values
            return {key: EnhancedGLPIIngestion._sanitize_payload_value(val)
                    for key, val in value.items()}

        elif isinstance(value, (list, tuple)):
            # Recursively sanitize list items
            return [EnhancedGLPIIngestion._sanitize_payload_value(item)
                    for item in value]

        elif isinstance(value, (int, float, bool)):
            # These types are safe as-is
            return value

        else:
            # Convert other types to string and sanitize
            str_value = str(value)
            return EnhancedGLPIIngestion._sanitize_payload_value(str_value)

    def __init__(self,
                 embedding_model: Optional[str] = None,
                 chunk_strategy: ChunkingStrategy = ChunkingStrategy.SEMANTIC):
        """
        Initialize enhanced ingestion service.
        
        Args:
            embedding_model: Override embedding model (uses config if None)
            chunk_strategy: Chunking strategy to use
        """
        # Use configured embedding model and dimensions
        self.embedding_model = embedding_model or settings.embedding_model
        self.embedding_dimension = settings.embedding_dimension
        
        logger.info(f"Initializing Enhanced GLPI Ingestion")
        logger.info(f"Embedding Model: {self.embedding_model}")
        logger.info(f"Embedding Dimension: {self.embedding_dimension}")
        logger.info(f"Chunking Strategy: {chunk_strategy.value}")
        
        # Initialize services with dependency injection
        self.glpi_service = GLPIService()
        self.embedding_service = EmbeddingService(model_name=self.embedding_model)
        
        # Initialize Qdrant with correct dimensions
        self.qdrant = QdrantAdapter(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            collection_name=settings.qdrant_collection,
            vector_size=self.embedding_dimension  # Use configured dimension!
        )
        
        # Initialize domain services
        self.domain_classifier = DomainClassifier()
        
        # Configure intelligent chunking
        self.chunk_config = ChunkConfig(
            strategy=chunk_strategy,
            min_chunk_size=500,     # Minimum 500 chars
            max_chunk_size=2000,    # Maximum 2000 chars (much larger!)
            overlap_size=200,       # 200 char overlap
            preserve_sentences=True,
            preserve_paragraphs=True,
            include_title_context=True,
            quality_threshold=0.5   # Higher quality threshold
        )
        self.chunker = IntelligentChunker(self.chunk_config)
        
        # Statistics
        self.stats = IngestionStats(
            started_at=datetime.now().isoformat(),
            embedding_model=self.embedding_model,
            embedding_dimension=self.embedding_dimension,
            chunking_strategy=chunk_strategy.value
        )
    
    def _classify_article(self, article: Dict[str, Any]) -> DocumentMetadata:
        """
        Classify article and build rich metadata.
        
        Args:
            article: GLPI article dict
            
        Returns:
            DocumentMetadata with classification and enrichment
        """
        title = article.get("title", "")
        content = article.get("content", "")[:1000]  # Sample for classification
        category = article.get("category", "Geral")
        glpi_meta = article.get("metadata", {})
        
        # Classify department using domain classifier
        sample_text = f"{title} {category} {content}"
        departments = self.domain_classifier.classify(sample_text, top_n=2)
        primary_dept = departments[0] if departments else Department.GERAL
        
        # Determine document type
        doc_type = DocType.FAQ if glpi_meta.get("is_faq") else DocType.ARTICLE
        
        # Extract intelligent tags
        tags = self._extract_tags(title, content, category)
        
        # Build comprehensive metadata
        metadata = DocumentMetadata(
            source_id=f"glpi_{article['id']}",
            title=title,
            department=primary_dept,
            doc_type=doc_type,
            category=category,
            tags=tags,
            file_format="html",
            created_at=glpi_meta.get("date_creation"),
            updated_at=glpi_meta.get("date_mod"),
            author=glpi_meta.get("author") or "GLPI",
            version="1.0",
            glpi_id=int(article['id']),
            is_public=glpi_meta.get("visibility") == "public",
            language="pt-BR",  # Assuming Portuguese
            keywords=self._extract_keywords(title, content),
            summary=self._generate_summary(content),
            departments=departments  # Store all relevant departments
        )
        
        logger.debug(
            f"Classified: {title[:50]}... -> "
            f"Dept={primary_dept.value}, Type={doc_type.value}, "
            f"Tags={len(tags)}"
        )
        
        return metadata
    
    def _extract_tags(self, title: str, content: str, category: str) -> List[str]:
        """Extract relevant tags from document."""
        tags = set()
        
        # Category hierarchy
        if category:
            parts = [p.strip() for p in category.split(">")]
            tags.update(p for p in parts if p and p != "Geral")
        
        # Title keywords (4+ chars, no stopwords)
        stopwords = {"para", "como", "fazer", "sobre", "quando", "onde"}
        title_words = [
            w.lower() for w in title.split() 
            if len(w) >= 4 and w.lower() not in stopwords
        ]
        tags.update(title_words[:5])
        
        # Technical terms from content
        tech_terms = self._extract_technical_terms(content)
        tags.update(tech_terms[:5])
        
        return list(tags)[:15]  # Max 15 tags
    
    def _extract_keywords(self, title: str, content: str) -> List[str]:
        """Extract SEO keywords from document."""
        # Simple keyword extraction (can be enhanced with NLP)
        words = (title + " " + content[:500]).lower().split()
        
        # Count frequency
        freq = {}
        for word in words:
            if len(word) >= 4 and word.isalpha():
                freq[word] = freq.get(word, 0) + 1
        
        # Return top keywords
        keywords = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [kw[0] for kw in keywords[:10]]
    
    def _extract_technical_terms(self, content: str) -> List[str]:
        """Extract technical terms from content."""
        import re
        
        # Pattern for technical terms (CamelCase, acronyms, etc.)
        patterns = [
            r'\b[A-Z]{2,}\b',  # Acronyms (VPN, SSH, etc.)
            r'\b[A-Z][a-z]+[A-Z][a-z]+\b',  # CamelCase
            r'\b\w+[@.]\w+\b',  # Emails, domains
        ]
        
        terms = set()
        for pattern in patterns:
            matches = re.findall(pattern, content)
            terms.update(m.lower() for m in matches[:5])
        
        return list(terms)
    
    def _generate_summary(self, content: str, max_length: int = 200) -> str:
        """Generate a brief summary of the content."""
        if not content:
            return ""
        
        # Take first paragraph or first N characters
        paragraphs = content.split('\n\n')
        if paragraphs:
            summary = paragraphs[0][:max_length]
            if len(summary) == max_length:
                # Cut at last complete word
                summary = summary.rsplit(' ', 1)[0] + "..."
            return summary
        
        return content[:max_length]
    
    def _process_article(self, article: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Process a single article into indexed chunks.
        
        Args:
            article: GLPI article dict
            
        Returns:
            List of successfully indexed chunk IDs
        """
        title = article.get("title", "Sem título")
        content = article.get("content", "")
        
        if not content or len(content.strip()) < settings.glpi_min_content_length:
            logger.warning(f"Article '{title}' too short, skipping")
            return []
        
        # Classify and build metadata
        doc_metadata = self._classify_article(article)
        
        # Intelligent chunking
        chunks = self.chunker.chunk_document(
            text=content,
            title=title,
            metadata=asdict(doc_metadata)
        )
        
        if not chunks:
            logger.warning(f"No valid chunks created for '{title}'")
            return []
        
        self.stats.total_chunks_created += len(chunks)
        indexed_chunks = []
        
        # Process each chunk
        for chunk in chunks:
            try:
                # Create chunk-specific metadata
                chunk_metadata = ChunkMetadata.from_document_metadata(
                    doc_metadata=doc_metadata,
                    chunk_index=chunk.chunk_index,
                    total_chunks=chunk.total_chunks,
                    text=chunk.text
                )
                
                # Add chunk-specific fields
                metadata_dict = chunk_metadata.model_dump()
                metadata_dict.update({
                    "quality_score": chunk.quality_score,
                    "semantic_type": chunk.semantic_type,
                    "parent_section": chunk.parent_section,
                    "chunk_size": len(chunk.text),
                })
                
                # Generate embedding for chunk
                # Use encode_text since title is already in chunk.text
                embedding = self.embedding_service.encode_text(chunk.text)
                
                if len(embedding) != self.embedding_dimension:
                    logger.error(
                        f"Embedding dimension mismatch: got {len(embedding)}, "
                        f"expected {self.embedding_dimension}"
                    )
                    continue
                
                # Create document for indexing
                document = DocumentCreate(
                    title=title,
                    category=doc_metadata.category or "Geral",
                    content=chunk.text,
                    metadata=metadata_dict
                )
                
                # Index in Qdrant
                import uuid
                doc_id = str(uuid.uuid4())
                
                # Build search text for BM25
                search_text = f"{title} {title} {title} {chunk.text}"

                # Build payload with all relevant data
                payload = {
                    "title": document.title,
                    "category": document.category,
                    "content": document.content,
                    "search_text": search_text,
                    "metadata": metadata_dict,
                    "department": doc_metadata.department.value,
                    "departments": [d.value for d in (doc_metadata.departments or [])],
                    "doc_type": doc_metadata.doc_type.value,
                    "tags": doc_metadata.tags,
                }

                # Sanitize payload to ensure all strings are properly encoded
                # This prevents issues with special characters in Qdrant/JSON
                payload = self._sanitize_payload_value(payload)

                # Store in Qdrant
                self.qdrant.upsert_point(
                    point_id=doc_id,
                    vector=embedding,
                    payload=payload
                )
                
                indexed_chunks.append(doc_id)
                self.stats.total_chunks_indexed += 1
                
                logger.debug(
                    f"Chunk {chunk.chunk_index + 1}/{chunk.total_chunks} indexed: "
                    f"size={len(chunk.text)}, quality={chunk.quality_score:.2f}, "
                    f"type={chunk.semantic_type}"
                )
                
            except Exception as e:
                logger.error(f"Failed to index chunk {chunk.chunk_index}: {e}")
                continue
        
        return indexed_chunks
    
    def run_sync(
        self,
        include_private: bool = False,
        clear_existing: bool = False,
        max_articles: Optional[int] = None,
        dry_run: bool = False
    ) -> IngestionStats:
        """
        Run full synchronization from GLPI to Qdrant.
        
        Args:
            include_private: Include private articles
            clear_existing: Clear existing collection before sync
            max_articles: Limit number of articles (for testing)
            dry_run: Process but don't actually index (for testing)
            
        Returns:
            IngestionStats with results
        """
        logger.info("=" * 80)
        logger.info("ENHANCED GLPI → QDRANT SYNCHRONIZATION")
        logger.info("=" * 80)
        logger.info(f"Configuration:")
        logger.info(f"  - Embedding Model: {self.embedding_model}")
        logger.info(f"  - Embedding Dimensions: {self.embedding_dimension}")
        logger.info(f"  - Chunking Strategy: {self.chunk_config.strategy.value}")
        logger.info(f"  - Max Chunk Size: {self.chunk_config.max_chunk_size}")
        logger.info(f"  - Include Private: {include_private}")
        logger.info(f"  - Clear Existing: {clear_existing}")
        logger.info(f"  - Dry Run: {dry_run}")
        logger.info("=" * 80)
        
        # Get articles from GLPI
        logger.info("Fetching articles from GLPI...")
        articles = self.glpi_service.get_all_articles(
            include_private=include_private,
            min_content_length=settings.glpi_min_content_length
        )
        
        if max_articles:
            articles = articles[:max_articles]
        
        self.stats.total_articles_glpi = len(articles)
        logger.info(f"Found {len(articles)} articles to process")
        
        # Clear existing collection if requested
        if clear_existing and not dry_run:
            try:
                logger.info("Clearing existing collection...")
                self.qdrant.client.delete_collection(settings.qdrant_collection)
                self.qdrant.ensure_collection()
                logger.info("Collection cleared and recreated")
            except Exception as e:
                logger.warning(f"Failed to clear collection: {e}")
        
        # Ensure collection exists
        if not dry_run:
            self.qdrant.ensure_collection()
        
        # Process articles
        total_chunk_sizes = []
        chunks_per_doc = []
        
        for idx, article in enumerate(articles, 1):
            title = article.get("title", "Sem título")
            
            try:
                logger.info(f"[{idx}/{len(articles)}] Processing: {title[:60]}...")
                
                if dry_run:
                    # Just process without indexing
                    doc_metadata = self._classify_article(article)
                    chunks = self.chunker.chunk_document(
                        text=article.get("content", ""),
                        title=title,
                        metadata=asdict(doc_metadata)
                    )
                    
                    if chunks:
                        self.stats.articles_processed += 1
                        self.stats.total_chunks_created += len(chunks)
                        chunks_per_doc.append(len(chunks))
                        total_chunk_sizes.extend([len(c.text) for c in chunks])
                        
                        logger.info(
                            f"  ✓ Would create {len(chunks)} chunks "
                            f"(avg size: {sum(len(c.text) for c in chunks) / len(chunks):.0f} chars)"
                        )
                else:
                    # Actually index
                    indexed_ids = self._process_article(article)
                    
                    if indexed_ids:
                        self.stats.articles_processed += 1
                        self.stats.articles_indexed += 1
                        chunks_per_doc.append(len(indexed_ids))
                        
                        logger.info(
                            f"  ✓ Indexed {len(indexed_ids)} chunks successfully"
                        )
                    else:
                        self.stats.articles_failed += 1
                        logger.warning(f"  ✗ Failed to index any chunks")
                
            except Exception as e:
                self.stats.articles_failed += 1
                logger.error(f"  ✗ Error processing article: {e}")
                continue
        
        # Calculate statistics
        if total_chunk_sizes:
            self.stats.avg_chunk_size = sum(total_chunk_sizes) / len(total_chunk_sizes)
        if chunks_per_doc:
            self.stats.avg_chunks_per_doc = sum(chunks_per_doc) / len(chunks_per_doc)
        
        self.stats.finished_at = datetime.now().isoformat()
        
        # Verify results
        if not dry_run:
            try:
                collection_info = self.qdrant.get_collection_info()
                logger.info(f"\nCollection Status:")
                logger.info(f"  - Vectors in Qdrant: {collection_info.get('vectors_count', 0)}")
                logger.info(f"  - Collection exists: {collection_info.get('exists', False)}")
            except Exception as e:
                logger.error(f"Failed to get collection info: {e}")
        
        # Print summary
        self._print_summary()
        
        return self.stats
    
    def _print_summary(self):
        """Print ingestion summary."""
        logger.info("\n" + "=" * 80)
        logger.info("INGESTION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Articles in GLPI:        {self.stats.total_articles_glpi}")
        logger.info(f"Articles Processed:      {self.stats.articles_processed}")
        logger.info(f"Articles Indexed:        {self.stats.articles_indexed}")
        logger.info(f"Articles Failed:         {self.stats.articles_failed}")
        logger.info(f"Total Chunks Created:    {self.stats.total_chunks_created}")
        logger.info(f"Total Chunks Indexed:    {self.stats.total_chunks_indexed}")
        logger.info(f"Avg Chunk Size:          {self.stats.avg_chunk_size:.0f} chars")
        logger.info(f"Avg Chunks per Doc:      {self.stats.avg_chunks_per_doc:.1f}")
        logger.info(f"Embedding Model:         {self.stats.embedding_model}")
        logger.info(f"Embedding Dimension:     {self.stats.embedding_dimension}")
        logger.info(f"Chunking Strategy:       {self.stats.chunking_strategy}")
        
        # Success rate
        if self.stats.articles_processed > 0:
            success_rate = (self.stats.articles_indexed / self.stats.articles_processed) * 100
            logger.info(f"Success Rate:            {success_rate:.1f}%")
            
            if success_rate >= 90:
                logger.info("✅ Synchronization completed successfully!")
            elif success_rate >= 70:
                logger.warning("⚠️ Synchronization completed with warnings")
            else:
                logger.error("❌ Synchronization had significant failures")
    
    def sync_single_article(self, article_id: int) -> bool:
        """
        Sync a single article from GLPI.
        
        Args:
            article_id: GLPI article ID
            
        Returns:
            True if successful
        """
        logger.info(f"Syncing single article: {article_id}")
        
        try:
            # Fetch article from GLPI
            article = self.glpi_service.get_article_by_id(article_id)
            if not article:
                logger.error(f"Article {article_id} not found in GLPI")
                return False
            
            # Process and index
            indexed_ids = self._process_article(article)
            
            if indexed_ids:
                logger.info(
                    f"✅ Article {article_id} synced successfully "
                    f"({len(indexed_ids)} chunks indexed)"
                )
                return True
            else:
                logger.error(f"❌ Failed to index article {article_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error syncing article {article_id}: {e}", exc_info=True)
            return False


def main():
    """Main entry point for script."""
    parser = argparse.ArgumentParser(
        description="Enhanced GLPI to Qdrant ingestion with intelligent chunking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full sync with semantic chunking (recommended)
  python scripts/ingest_glpi_enhanced.py
  
  # Use hierarchical chunking for structured docs
  python scripts/ingest_glpi_enhanced.py --strategy hierarchical
  
  # Clear and reimport everything
  python scripts/ingest_glpi_enhanced.py --clear
  
  # Test run without indexing
  python scripts/ingest_glpi_enhanced.py --dry-run --max-articles 10
  
  # Sync specific article
  python scripts/ingest_glpi_enhanced.py --article-id 123
  
  # Use specific embedding model
  python scripts/ingest_glpi_enhanced.py --embedding-model BGE-M3
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
    
    args = parser.parse_args()
    
    # Map strategy string to enum
    strategy_map = {
        "semantic": ChunkingStrategy.SEMANTIC,
        "hierarchical": ChunkingStrategy.HIERARCHICAL,
        "sliding_window": ChunkingStrategy.SLIDING_WINDOW,
    }
    strategy = strategy_map[args.strategy]
    
    try:
        # Initialize ingestion service
        ingestion = EnhancedGLPIIngestion(
            embedding_model=args.embedding_model,
            chunk_strategy=strategy
        )
        
        # Run appropriate operation
        if args.article_id:
            # Single article sync
            success = ingestion.sync_single_article(args.article_id)
            sys.exit(0 if success else 1)
        else:
            # Full sync
            stats = ingestion.run_sync(
                include_private=args.include_private,
                clear_existing=args.clear,
                max_articles=args.max_articles,
                dry_run=args.dry_run
            )
            
            # Exit with appropriate code
            if stats.articles_processed > 0:
                success_rate = (stats.articles_indexed / stats.articles_processed) * 100
                sys.exit(0 if success_rate >= 70 else 1)
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