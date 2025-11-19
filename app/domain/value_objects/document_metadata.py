from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

@dataclass(frozen=True)
class DocumentMetadata:
    department: Optional[str] = None
    doc_type: Optional[str] = None
    tags: tuple = ()
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    author: Optional[str] = None
    language: str = "pt-BR"
    
    def __post_init__(self):
        if isinstance(self.tags, list):
            object.__setattr__(self, 'tags', tuple(self.tags))
        
        valid_departments = ["TI", "RH", "Financeiro", "Geral", None]
        if self.department and self.department not in valid_departments:
            raise ValueError(f"Departamento inválido: {self.department}")
        
        valid_types = ["manual", "policy", "faq", "tutorial", "qa_memory", None]
        if self.doc_type and self.doc_type not in valid_types:
            raise ValueError(f"Tipo de documento inválido: {self.doc_type}")
    
    def to_dict(self) -> dict:
        return {
            "department": self.department,
            "doc_type": self.doc_type,
            "tags": list(self.tags),
            "source_id": self.source_id,
            "source_url": self.source_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "author": self.author,
            "language": self.language,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DocumentMetadata":
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        
        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        
        return cls(
            department=data.get("department"),
            doc_type=data.get("doc_type"),
            tags=tuple(data.get("tags", [])),
            source_id=data.get("source_id"),
            source_url=data.get("source_url"),
            created_at=created_at,
            updated_at=updated_at,
            author=data.get("author"),
            language=data.get("language", "pt-BR"),
        )