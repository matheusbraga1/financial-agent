from typing import Generic, TypeVar, Optional, Any, List
from pydantic import BaseModel, Field
from datetime import datetime

T = TypeVar('T')

class PaginationMeta(BaseModel):
    page: int = Field(..., description="Página atual")
    per_page: int = Field(..., description="Items por página")
    total: int = Field(..., description="Total de items")
    total_pages: int = Field(..., description="Total de páginas")
    has_next: bool = Field(..., description="Tem próxima página")
    has_prev: bool = Field(..., description="Tem página anterior")

class ApiResponse(BaseModel, Generic[T]):
    success: bool = Field(..., description="Indica se a operação foi bem-sucedida")
    data: Optional[T] = Field(None, description="Dados da resposta")
    message: Optional[str] = Field(None, description="Mensagem informativa")
    errors: Optional[List[str]] = Field(None, description="Lista de erros, se houver")
    meta: Optional[dict] = Field(None, description="Metadados adicionais")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp da resposta")
    request_id: Optional[str] = Field(None, description="ID único da requisição")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "data": {"id": 1, "name": "Example"},
                "message": "Operação realizada com sucesso",
                "errors": None,
                "meta": {"version": "1.0.0"},
                "timestamp": "2024-01-01T00:00:00Z",
                "request_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }

class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = Field(True)
    data: List[T] = Field(..., description="Lista de items")
    pagination: PaginationMeta = Field(..., description="Metadados de paginação")
    message: Optional[str] = Field(None)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = Field(None)

class ErrorResponse(BaseModel):
    success: bool = Field(False)
    error: str = Field(..., description="Código do erro")
    message: str = Field(..., description="Mensagem de erro")
    details: Optional[Any] = Field(None, description="Detalhes adicionais do erro")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = Field(None)
    path: Optional[str] = Field(None, description="Path da requisição que gerou o erro")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "VALIDATION_ERROR",
                "message": "Dados inválidos fornecidos",
                "details": {"field": "email", "error": "Email inválido"},
                "timestamp": "2024-01-01T00:00:00Z",
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
                "path": "/api/v1/users"
            }
        }