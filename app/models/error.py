from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Optional


class ErrorResponse(BaseModel):
    code: str = Field(..., description="Código de erro estável para contratos de API")
    message: str = Field(..., description="Mensagem resumida para exibição ao usuário")
    trace_id: Optional[str] = Field(
        None, description="ID de rastreamento da requisição (X-Request-ID)"
    )
    details: Optional[Any] = Field(
        None, description="Detalhes adicionais do erro (quando aplicável)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "internal_error",
                "message": "Erro interno do servidor",
                "trace_id": "a3f1a2c8-2d3e-4b78-9b3d-5a6f7e8d9c0a",
                "details": None,
            }
        }
    )

