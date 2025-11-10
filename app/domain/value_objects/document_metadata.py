"""Schema de metadados para documentos multi-domínio."""

from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class Department(str, Enum):
    """Departamentos/Setores da empresa."""
    TI = "TI"
    RH = "RH"
    FINANCEIRO = "Financeiro"
    LOTEAMENTO = "Loteamento"
    ALUGUEL = "Aluguel"
    JURIDICO = "Jurídico"
    GERAL = "Geral"


class DocType(str, Enum):
    """Tipos de documento."""
    ARTICLE = "article"  # Artigos GLPI
    CONTRACT = "contract"  # Contratos
    POLICY = "policy"  # Políticas corporativas
    PROCEDURE = "procedure"  # Procedimentos operacionais
    FORM = "form"  # Formulários
    MANUAL = "manual"  # Manuais técnicos
    FAQ = "faq"  # Perguntas frequentes
    GUIDE = "guide"  # Guias e tutoriais


class DocumentMetadata(BaseModel):
    """Metadados completos de um documento."""

    # Identificação
    source_id: str = Field(..., description="ID único do documento")
    title: str = Field(..., description="Título do documento")

    # Classificação
    department: Department = Field(..., description="Departamento responsável")
    doc_type: DocType = Field(..., description="Tipo de documento")
    category: Optional[str] = Field(None, description="Subcategoria dentro do departamento")

    # Metadata adicional
    tags: List[str] = Field(default_factory=list, description="Tags para busca")
    file_format: str = Field(default="html", description="Formato do arquivo original")

    # Controle
    created_at: Optional[str] = Field(None, description="Data de criação ISO format")
    updated_at: Optional[str] = Field(None, description="Data de última atualização")
    author: Optional[str] = Field(None, description="Autor do documento")

    # Versionamento
    version: str = Field(default="1.0", description="Versão do documento")

    # Para artigos GLPI (compatibilidade com sistema atual)
    glpi_id: Optional[int] = Field(None, description="ID no GLPI (se aplicável)")
    is_public: bool = Field(default=True, description="Se o artigo é público no GLPI")

    class Config:
        use_enum_values = True


class ChunkMetadata(BaseModel):
    """Metadados de um chunk de documento (para Qdrant)."""

    # Herda todos os campos do documento pai
    source_id: str
    title: str
    department: str  # Usar string para facilitar serialização JSON
    doc_type: str
    category: Optional[str] = None
    tags: List[str] = []
    file_format: str = "html"
    created_at: Optional[str] = None
    author: Optional[str] = None

    # Específico do chunk
    chunk_index: int = Field(..., description="Índice do chunk no documento")
    total_chunks: int = Field(..., description="Total de chunks do documento")
    text: str = Field(..., description="Texto do chunk")

    # GLPI compatibility
    glpi_id: Optional[int] = None
    is_public: bool = True

    @classmethod
    def from_document_metadata(
        cls,
        doc_metadata: DocumentMetadata,
        chunk_index: int,
        total_chunks: int,
        text: str
    ) -> "ChunkMetadata":
        """Cria ChunkMetadata a partir de DocumentMetadata."""
        return cls(
            source_id=doc_metadata.source_id,
            title=doc_metadata.title,
            department=doc_metadata.department,
            doc_type=doc_metadata.doc_type,
            category=doc_metadata.category,
            tags=doc_metadata.tags,
            file_format=doc_metadata.file_format,
            created_at=doc_metadata.created_at,
            author=doc_metadata.author,
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            text=text,
            glpi_id=doc_metadata.glpi_id,
            is_public=doc_metadata.is_public
        )
