from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import hashlib
import json


class Department(str, Enum):
    """Departments in the organization."""
    TI = "TI"
    RH = "RH"
    FINANCEIRO = "Financeiro"
    LOTEAMENTO = "Loteamento"
    ALUGUEL = "Aluguel"
    JURIDICO = "Juridico"
    GERAL = "Geral"


class DocType(str, Enum):
    """Types of documents in the knowledge base."""
    ARTICLE = "article"          # Knowledge base article
    FAQ = "faq"                  # Frequently asked question
    POLICY = "policy"            # Company policy
    PROCEDURE = "procedure"       # Step-by-step procedure
    MANUAL = "manual"            # User manual
    GUIDE = "guide"              # How-to guide
    CONTRACT = "contract"        # Contract template
    FORM = "form"                # Form template
    REPORT = "report"            # Report template
    QA_MEMORY = "qa_memory"      # Question-Answer pair from chat history
    

@dataclass(frozen=True)
class DocumentMetadata:
    """
    Complete metadata for a document.
    
    This is a Value Object that contains all metadata about a document
    in the knowledge base. It's immutable (frozen=True) to maintain
    consistency.
    """
    # Core identifiers
    source_id: str                           # Unique ID from source system (e.g., glpi_123)
    title: str                               # Document title
    
    # Classification
    department: Department                    # Primary department
    doc_type: DocType                        # Document type
    category: Optional[str] = None          # Hierarchical category (e.g., "TI > Email > Config")
    
    # Content metadata
    tags: List[str] = field(default_factory=list)           # Searchable tags
    keywords: List[str] = field(default_factory=list)        # SEO keywords
    summary: Optional[str] = None                            # Brief summary
    language: str = "pt-BR"                                  # Content language
    
    # Source information
    file_format: str = "html"                # Original format
    created_at: Optional[str] = None         # Creation timestamp
    updated_at: Optional[str] = None         # Last update timestamp
    author: Optional[str] = None             # Author/creator
    version: str = "1.0"                     # Document version
    
    # GLPI specific (when source is GLPI)
    glpi_id: Optional[int] = None            # GLPI article ID
    glpi_category_id: Optional[int] = None   # GLPI category ID
    is_faq: bool = False                     # Is FAQ article
    is_public: bool = True                   # Public visibility
    
    # Multi-domain support
    departments: Optional[List[Department]] = None  # All relevant departments
    related_docs: List[str] = field(default_factory=list)  # Related document IDs
    
    # Quality and usage metrics
    quality_score: float = 1.0               # Document quality (0-1)
    helpful_votes: int = 0                   # Positive feedback count
    complaints: int = 0                      # Negative feedback count
    usage_count: int = 0                     # Times used in answers
    last_used_at: Optional[str] = None       # Last usage timestamp
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_id": self.source_id,
            "title": self.title,
            "department": self.department.value if self.department else None,
            "doc_type": self.doc_type.value if self.doc_type else None,
            "category": self.category,
            "tags": self.tags,
            "keywords": self.keywords,
            "summary": self.summary,
            "language": self.language,
            "file_format": self.file_format,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "author": self.author,
            "version": self.version,
            "glpi_id": self.glpi_id,
            "glpi_category_id": self.glpi_category_id,
            "is_faq": self.is_faq,
            "is_public": self.is_public,
            "departments": [d.value for d in self.departments] if self.departments else [],
            "related_docs": self.related_docs,
            "quality_score": self.quality_score,
            "helpful_votes": self.helpful_votes,
            "complaints": self.complaints,
            "usage_count": self.usage_count,
            "last_used_at": self.last_used_at,
        }
    
    def model_dump(self) -> Dict[str, Any]:
        """Pydantic-compatible method name."""
        return self.to_dict()


@dataclass(frozen=True)
class ChunkMetadata:
    """
    Metadata for a document chunk.
    
    When documents are split into chunks for indexing, each chunk
    carries this metadata to maintain context and relationships.
    """
    # Chunk identifiers
    chunk_id: str                           # Unique chunk ID
    source_doc_id: str                      # Parent document ID
    chunk_index: int                        # Index within document (0-based)
    total_chunks: int                       # Total chunks in document
    
    # Chunk content info
    start_char: int                         # Start position in original
    end_char: int                           # End position in original
    chunk_size: int                         # Size in characters
    text_hash: str                          # Hash of chunk text for dedup
    
    # Inherited from document
    doc_title: str                          # Document title
    doc_department: Department              # Document department
    doc_type: DocType                       # Document type
    doc_category: Optional[str] = None      # Document category
    doc_tags: List[str] = field(default_factory=list)
    
    # Chunk-specific metadata
    semantic_type: Optional[str] = None     # Type: paragraph, list, procedure, etc.
    parent_section: Optional[str] = None    # Parent section title
    quality_score: float = 1.0              # Chunk quality (0-1)
    has_code: bool = False                  # Contains code snippets
    has_list: bool = False                  # Contains lists
    has_table: bool = False                 # Contains tables
    
    # Navigation
    prev_chunk_id: Optional[str] = None     # Previous chunk ID
    next_chunk_id: Optional[str] = None     # Next chunk ID
    
    @classmethod
    def from_document_metadata(
        cls,
        doc_metadata: DocumentMetadata,
        chunk_index: int,
        total_chunks: int,
        text: str,
        start_char: int = 0,
        end_char: int = 0,
    ) -> "ChunkMetadata":
        """
        Create ChunkMetadata from DocumentMetadata.
        
        Factory method to create chunk metadata inheriting from document.
        """
        import uuid
        
        # Generate chunk ID
        chunk_id = str(uuid.uuid4())
        
        # Hash text for deduplication
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        
        # Detect content types
        has_code = "```" in text or "def " in text or "class " in text
        has_list = bool(re.search(r'^\s*[-*•]\s+', text, re.MULTILINE))
        has_table = "|" in text and "-|-" in text
        
        return cls(
            chunk_id=chunk_id,
            source_doc_id=doc_metadata.source_id,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            start_char=start_char,
            end_char=end_char,
            chunk_size=len(text),
            text_hash=text_hash,
            doc_title=doc_metadata.title,
            doc_department=doc_metadata.department,
            doc_type=doc_metadata.doc_type,
            doc_category=doc_metadata.category,
            doc_tags=doc_metadata.tags,
            has_code=has_code,
            has_list=has_list,
            has_table=has_table,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "chunk_id": self.chunk_id,
            "source_doc_id": self.source_doc_id,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "chunk_size": self.chunk_size,
            "text_hash": self.text_hash,
            "doc_title": self.doc_title,
            "doc_department": self.doc_department.value if self.doc_department else None,
            "doc_type": self.doc_type.value if self.doc_type else None,
            "doc_category": self.doc_category,
            "doc_tags": self.doc_tags,
            "semantic_type": self.semantic_type,
            "parent_section": self.parent_section,
            "quality_score": self.quality_score,
            "has_code": self.has_code,
            "has_list": self.has_list,
            "has_table": self.has_table,
            "prev_chunk_id": self.prev_chunk_id,
            "next_chunk_id": self.next_chunk_id,
        }
    
    def model_dump(self) -> Dict[str, Any]:
        """Pydantic-compatible method name."""
        return self.to_dict()


@dataclass(frozen=True)
class SearchContext:
    """
    Context for search operations.
    
    Value object that encapsulates all context needed for
    intelligent search and retrieval.
    """
    query: str                              # User query
    departments: List[Department]           # Relevant departments
    doc_types: Optional[List[DocType]] = None  # Filter by doc types
    tags: Optional[List[str]] = None        # Filter by tags
    language: str = "pt-BR"                 # Query language
    user_role: Optional[str] = None         # User role for access control
    min_quality: float = 0.0                # Minimum quality threshold
    max_age_days: Optional[int] = None      # Maximum document age
    include_qa_memory: bool = True          # Include QA memories
    boost_recent: bool = True               # Boost recent documents
    boost_popular: bool = True              # Boost popular documents
    
    def to_filter_dict(self) -> Dict[str, Any]:
        """Convert to filter dictionary for vector store."""
        filters = {}
        
        if self.departments:
            filters["departments"] = [d.value for d in self.departments]
        
        if self.doc_types:
            filters["doc_types"] = [dt.value for dt in self.doc_types]
        
        if self.tags:
            filters["tags"] = self.tags
        
        if self.min_quality > 0:
            filters["min_quality"] = self.min_quality
        
        if self.max_age_days:
            # Calculate cutoff date
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(days=self.max_age_days)
            filters["updated_after"] = cutoff.isoformat()
        
        return filters


# Import for missing re module
import re