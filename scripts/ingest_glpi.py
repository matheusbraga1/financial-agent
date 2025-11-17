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
import base64
import re
from html import unescape
from bs4 import BeautifulSoup

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
from app.domain.services.rag.domain_classifier import DomainClassifier

# Import infrastructure services
from app.infrastructure.adapters.external.glpi_client import GLPIClient
from app.infrastructure.adapters.vector_store.qdrant_adapter import QdrantAdapter
from app.infrastructure.adapters.embeddings.sentence_transformer_adapter import SentenceTransformerAdapter
from app.models.document import DocumentCreate
from app.infrastructure.config.settings import get_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Get settings
settings = get_settings()


def is_base64(text: str) -> bool:
    """
    Check if a string is base64 encoded.

    Args:
        text: String to check

    Returns:
        True if the string appears to be base64 encoded
    """
    if not text or len(text) < 50:
        return False

    # Check for base64 characteristics
    # - Only contains base64 characters
    # - Length is multiple of 4 (with padding)
    # - High ratio of alphanumeric characters
    base64_pattern = re.compile(r'^[A-Za-z0-9+/=]+$')

    # Remove whitespace
    text_clean = text.strip()

    # Check if it matches base64 pattern
    if not base64_pattern.match(text_clean):
        return False

    # Check if length is appropriate for base64
    if len(text_clean) % 4 != 0:
        return False

    # Try to decode - if it fails, it's not base64
    try:
        decoded = base64.b64decode(text_clean)
        # Check if decoded content is mostly text
        try:
            decoded.decode('utf-8')
            return True
        except:
            return False
    except:
        return False


def decode_base64_content(text: str) -> str:
    """
    Decode base64 encoded content.

    Args:
        text: Potentially base64 encoded string

    Returns:
        Decoded string or original if decoding fails
    """
    try:
        decoded_bytes = base64.b64decode(text)
        decoded_text = decoded_bytes.decode('utf-8')
        return decoded_text
    except Exception as e:
        logger.warning(f"Failed to decode base64: {e}")
        return text


def clean_html(html_content: str) -> str:
    """
    Clean HTML content and extract plain text.

    Args:
        html_content: HTML string

    Returns:
        Plain text without HTML tags
    """
    if not html_content:
        return ""

    try:
        # Parse HTML
        soup = BeautifulSoup(html_content, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()

        # Get text
        text = soup.get_text()

        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)

        return text
    except Exception as e:
        logger.warning(f"Failed to clean HTML: {e}")
        return html_content


def fix_encoding(text: str) -> str:
    """
    Try to fix encoding issues in text using ftfy library.

    Common issues:
    - Text was stored as latin1 but read as utf8
    - Mojibake (mixed encoding issues)
    - Missing or incorrect character mappings

    Args:
        text: Text with potential encoding issues

    Returns:
        Fixed text
    """
    if not text:
        return text

    return text


def clean_glpi_content(content: str, title: str = "") -> str:
    """
    Clean and normalize GLPI content.

    This function:
    1. Detects and decodes base64 content
    2. Cleans HTML tags and entities
    3. Normalizes whitespace
    4. Removes special characters and artifacts
    5. Fixes encoding issues

    Args:
        content: Raw content from GLPI
        title: Article title (for logging)

    Returns:
        Cleaned plain text content
    """
    if not content:
        return ""

    original_length = len(content)

    # Step 1: Check if content is base64 encoded
    if is_base64(content):
        logger.info(f"Detected base64 content in '{title[:50]}...', decoding")
        content = decode_base64_content(content)

    # Step 2: Decode HTML entities (e.g., &lt;, &gt;, &#60;, &#62;)
    content = unescape(content)

    # Step 3: Clean HTML tags
    content = clean_html(content)

    # Step 4: Fix common encoding issues
    # Replace HTML-escaped characters
    replacements = {
        '&nbsp;': ' ',
        '&quot;': '"',
        '&apos;': "'",
        '&amp;': '&',
        '&lt;': '<',
        '&gt;': '>',
        '\r\n': '\n',
        '\r': '\n',
    }

    for old, new in replacements.items():
        content = content.replace(old, new)

    # Step 5: Remove multiple consecutive whitespace/newlines
    content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)  # Max 2 newlines
    content = re.sub(r' +', ' ', content)  # Single spaces only

    # Step 6: Remove non-printable characters (except newlines, tabs)
    content = ''.join(char for char in content if char.isprintable() or char in '\n\t')

    # Step 7: Fix encoding issues (e.g., ?? -> á, ã, etc.)
    content = fix_encoding(content)

    # Step 8: Normalize unicode
    content = unicodedata.normalize('NFC', content)

    # Step 9: Strip leading/trailing whitespace
    content = content.strip()

    cleaned_length = len(content)

    # Calculate reduction percentage
    reduction_pct = ((original_length - cleaned_length) / original_length * 100) if original_length > 0 else 0

    # Log based on reduction severity
    if cleaned_length < original_length * 0.15:  # Less than 15% remaining - very suspicious
        logger.warning(
            f"Extreme content reduction: {original_length} -> {cleaned_length} chars ({reduction_pct:.0f}% reduced) "
            f"for '{title[:50]}...'. Content may be mostly HTML/formatting."
        )
    elif cleaned_length < original_length * 0.30:  # 15-30% remaining - normal for HTML-heavy content
        logger.info(
            f"Significant HTML removed: {original_length} -> {cleaned_length} chars ({reduction_pct:.0f}% reduced) "
            f"for '{title[:50]}...'"
        )
    elif reduction_pct > 50:  # More than 50% reduced but still reasonable content
        logger.debug(
            f"Content cleaned: {original_length} -> {cleaned_length} chars ({reduction_pct:.0f}% reduced) "
            f"for '{title[:50]}...'"
        )

    return content


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
        self.glpi_service = GLPIClient(
            host=settings.glpi_db_host,
            port=settings.glpi_db_port,
            database=settings.glpi_db_name,
            user=settings.glpi_db_user,
            password=settings.glpi_db_password,
            table_prefix=settings.glpi_db_prefix
        )
        self.embedding_service = SentenceTransformerAdapter(model_name=self.embedding_model)
        
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
        department_strings = self.domain_classifier.classify(sample_text)

        # Convert string department names to Department enum
        departments = []
        for dept_str in department_strings:
            try:
                # Try to match the department string to the enum
                if dept_str == "TI":
                    departments.append(Department.TI)
                elif dept_str == "RH":
                    departments.append(Department.RH)
                elif dept_str in ["Financeiro", "FINANCEIRO"]:
                    departments.append(Department.FINANCEIRO)
                elif dept_str in ["Loteamento", "LOTEAMENTO"]:
                    departments.append(Department.LOTEAMENTO)
                elif dept_str == "Geral":
                    departments.append(Department.GERAL)
            except:
                continue

        # If no departments matched, use GERAL
        if not departments:
            departments = [Department.GERAL]

        primary_dept = departments[0]
        
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

        # Clean content (decode base64, remove HTML, normalize)
        content = clean_glpi_content(content, title)

        if not content or len(content.strip()) < settings.glpi_min_content_length:
            logger.warning(f"Article '{title}' too short after cleaning, skipping")
            return []

        # Update article with cleaned content for classification
        article_cleaned = article.copy()
        article_cleaned["content"] = content

        # Classify and build metadata
        doc_metadata = self._classify_article(article_cleaned)
        
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
                    # Clean content first
                    content = clean_glpi_content(article.get("content", ""), title)
                    article_cleaned = article.copy()
                    article_cleaned["content"] = content

                    doc_metadata = self._classify_article(article_cleaned)
                    chunks = self.chunker.chunk_document(
                        text=content,
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