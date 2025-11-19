from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import hashlib
import json


class Department(str, Enum):
    TI = "TI"
    RH = "RH"
    FINANCEIRO = "Financeiro"
    LOTEAMENTO = "Loteamento"
    ALUGUEL = "Aluguel"
    JURIDICO = "Juridico"
    GERAL = "Geral"


class DocType(str, Enum):
    ARTICLE = "article"
    FAQ = "faq"
    POLICY = "policy"
    PROCEDURE = "procedure"
    MANUAL = "manual"
    GUIDE = "guide"
    CONTRACT = "contract"
    FORM = "form"
    REPORT = "report"
    QA_MEMORY = "qa_memory"
    

@dataclass(frozen=True)
class DocumentMetadata:
    source_id: str
    title: str

    department: Department
    doc_type: DocType
    category: Optional[str] = None

    tags: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    summary: Optional[str] = None
    language: str = "pt-BR"

    file_format: str = "html"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    author: Optional[str] = None
    version: str = "1.0"

    glpi_id: Optional[int] = None
    glpi_category_id: Optional[int] = None
    is_faq: bool = False
    is_public: bool = True

    departments: Optional[List[Department]] = None
    related_docs: List[str] = field(default_factory=list)

    quality_score: float = 1.0
    helpful_votes: int = 0
    complaints: int = 0
    usage_count: int = 0
    last_used_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
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
        return self.to_dict()


@dataclass(frozen=True)
class ChunkMetadata:
    chunk_id: str
    source_doc_id: str
    chunk_index: int
    total_chunks: int

    start_char: int
    end_char: int
    chunk_size: int
    text_hash: str

    doc_title: str
    doc_department: Department
    doc_type: DocType
    doc_category: Optional[str] = None
    doc_tags: List[str] = field(default_factory=list)

    semantic_type: Optional[str] = None
    parent_section: Optional[str] = None
    quality_score: float = 1.0
    has_code: bool = False
    has_list: bool = False
    has_table: bool = False

    prev_chunk_id: Optional[str] = None
    next_chunk_id: Optional[str] = None
    
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
        import uuid

        chunk_id = str(uuid.uuid4())

        text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

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
        return self.to_dict()


@dataclass(frozen=True)
class SearchContext:
    query: str
    departments: List[Department]
    doc_types: Optional[List[DocType]] = None
    tags: Optional[List[str]] = None
    language: str = "pt-BR"
    user_role: Optional[str] = None
    min_quality: float = 0.0
    max_age_days: Optional[int] = None
    include_qa_memory: bool = True
    boost_recent: bool = True
    boost_popular: bool = True
    
    def to_filter_dict(self) -> Dict[str, Any]:
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
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(days=self.max_age_days)
            filters["updated_after"] = cutoff.isoformat()

        return filters


import re