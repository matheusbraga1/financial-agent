from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class ChatRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Pergunta do usuário",
        example="Como resetar minha senha do email?"
    )
    session_id: Optional[str] = Field(
        None,
        description="ID da sessão para manter contexto",
        example="550e8400-e29b-41d4-a716-446655440000"
    )

class SourceDocument(BaseModel):
    id: str
    title: str
    category: str
    score: float = Field(..., ge=0, le=1)
    snippet: Optional[str] = Field(
        default=None,
        description="Pequeno trecho do conteúdo do documento para contexto"
    )

class ChatResponse(BaseModel):
    answer: str = Field(..., description="Resposta da IA em markdown")
    answer_html: Optional[str] = Field(None, description="Resposta convertida para HTML")
    answer_plain: Optional[str] = Field(None, description="Resposta em texto puro (sem markdown)")
    session_id: Optional[str] = Field(None, description="ID da sessão de conversa")
    persisted: bool = Field(
        default=False,
        description="Indica se a conversa foi persistida (usuário autenticado)"
    )
    sources: List[SourceDocument] = Field(
        default_factory=list,
        description="Documentos fonte"
    )
    model_used: str = Field(..., description="Modelo LLM usado")
    confidence: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Confiança agregada na resposta (0 a 1)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Momento da resposta"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "answer": "## Como Resetar Senha\n\nPara resetar...",
                "answer_html": "<h2>Como Resetar Senha</h2><p>Para resetar...</p>",
                "answer_plain": "Como Resetar Senha\n\nPara resetar...",
                "sources": [
                    {
                        "id": "1",
                        "title": "Resetar Senha",
                        "category": "Email",
                        "score": 0.89,
                        "snippet": "Para resetar sua senha, acesse o portal ..."
                    }
                ],
                "model_used": "llama3.1:8b",
                "confidence": 0.82,
                "persisted": false,
                "timestamp": "2025-10-30T10:30:00"
            }
        }


class ChatHistoryMessage(BaseModel):
    role: str = Field(..., description="'user' ou 'assistant'")
    content: Optional[str] = Field(None, description="Mensagem do usuário (quando role=user)")
    answer: Optional[str] = Field(None, description="Resposta do assistente (quando role=assistant)")
    sources: Optional[List[SourceDocument]] = Field(None, description="Fontes (assistant)")
    model_used: Optional[str] = Field(None, description="Modelo usado (assistant)")
    confidence: Optional[float] = Field(None, ge=0, le=1, description="Confiança (assistant)")
    timestamp: Optional[datetime] = Field(None, description="Momento da mensagem")


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: List[ChatHistoryMessage] = Field(default_factory=list)

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "messages": [
                    {"role": "user", "content": "Como resetar senha?", "timestamp": "2025-10-30T10:00:00"},
                    {
                        "role": "assistant",
                        "answer": "Para resetar sua senha...",
                        "sources": [{"id":"1","title":"Resetar Senha","category":"Email","score":0.89}],
                        "model_used": "llama3.1:8b",
                        "confidence": 0.82,
                        "timestamp": "2025-10-30T10:00:02"
                    }
                ]
            }
        }
