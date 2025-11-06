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

class ChatResponse(BaseModel):
    answer: str = Field(..., description="Resposta da IA")
    sources: List[SourceDocument] = Field(
        default_factory=list,
        description="Documentos fonte"
    )
    model_used: str = Field(..., description="Modelo LLM usado")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Momento da resposta"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "answer": "Para resetar sua senha...",
                "sources": [
                    {
                        "id": "1",
                        "title": "Resetar Senha",
                        "category": "Email",
                        "score": 0.89
                    }
                ],
                "model_used": "llama3.1:8b",
                "timestamp": "2025-10-30T10:30:00"
            }
        }