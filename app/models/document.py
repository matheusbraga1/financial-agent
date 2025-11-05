from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=10, max_length=10000)
    metadata: Optional[dict] = Field(default=None)

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Como resetar senha",
                "category": "Email",
                "content": "Para resetar sua senha...",
                "metadata": {"author": "TI", "version": "1.0"}
            }
        }


class DocumentResponse(BaseModel):
    id: str
    title: str
    category: str
    created_at: datetime
    indexed: bool = True


class DocumentList(BaseModel):
    total: int
    documents: list[DocumentResponse]
    page: int = 1
    page_size: int = 10