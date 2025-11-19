from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

class ChatRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Pergunta do usuário"
    )
    session_id: Optional[str] = Field(
        None,
        description="ID da sessão (gerado se omitido)"
    )
    
    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Pergunta não pode estar vazia")
        return v.strip()

class SourceDocument(BaseModel):
    id: str = Field(..., description="ID do documento")
    title: str = Field(..., description="Título do documento")
    category: str = Field("", description="Categoria do documento")
    score: float = Field(..., ge=0.0, le=1.0, description="Score de relevância")
    snippet: Optional[str] = Field(None, description="Trecho do documento")


class ChatResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    answer: str = Field(..., description="Resposta gerada")
    sources: List[SourceDocument] = Field(
        default_factory=list,
        description="Fontes usadas"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confiança da resposta"
    )
    model_used: str = Field(..., description="Modelo LLM usado")
    session_id: Optional[str] = Field(None, description="ID da sessão")
    message_id: Optional[int] = Field(None, description="ID da mensagem")
    persisted: bool = Field(False, description="Se foi salvo no histórico")


class ChatHistoryMessage(BaseModel):
    model_config = {"protected_namespaces": ()}

    role: str = Field(..., description="user ou assistant")
    message_id: Optional[int] = Field(None, description="ID da mensagem")
    content: Optional[str] = Field(None, description="Conteúdo (user)")
    answer: Optional[str] = Field(None, description="Resposta (assistant)")
    sources: Optional[List[SourceDocument]] = Field(
        None,
        description="Fontes (assistant)"
    )
    model_used: Optional[str] = Field(None, description="Modelo usado")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    timestamp: Optional[datetime] = Field(None, description="Data/hora")


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: List[ChatHistoryMessage]


class SessionInfo(BaseModel):
    session_id: str
    created_at: datetime
    message_count: int = 0
    last_message: str = "Nova conversa"


class SessionsResponse(BaseModel):
    sessions: List[SessionInfo]
    total: int = Field(..., description="Total de sessões do usuário")
    limit: int = Field(..., description="Limite de sessões por página")
    offset: int = Field(..., description="Offset atual da paginação")
    has_more: bool = Field(..., description="Indica se há mais sessões")