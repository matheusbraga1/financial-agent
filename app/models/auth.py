from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from datetime import datetime


class RegisterRequest(BaseModel):
    """Modelo para registro de novo usuário"""
    email: EmailStr = Field(
        ...,
        description="Email válido do usuário",
        examples=["joao.silva@empresa.com.br"]
    )
    password: str = Field(
        ...,
        min_length=8,
        description="Senha com no mínimo 8 caracteres (recomendado: letras, números e caracteres especiais)",
        examples=["Senha@123"]
    )
    name: Optional[str] = Field(
        None,
        max_length=100,
        description="Nome completo do usuário",
        examples=["João Silva"]
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "email": "joao.silva@empresa.com.br",
            "password": "Senha@123",
            "name": "João Silva"
        }
    })


class LoginRequest(BaseModel):
    """Modelo para autenticação de usuário"""
    email: EmailStr = Field(
        ...,
        description="Email cadastrado no sistema",
        examples=["joao.silva@empresa.com.br"]
    )
    password: str = Field(
        ...,
        min_length=8,
        description="Senha do usuário",
        examples=["Senha@123"]
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "email": "joao.silva@empresa.com.br",
            "password": "Senha@123"
        }
    })


class UserPublic(BaseModel):
    """Dados públicos do usuário (sem informações sensíveis)"""
    id: int = Field(..., description="ID único do usuário", examples=[1])
    email: EmailStr = Field(..., description="Email do usuário", examples=["joao.silva@empresa.com.br"])
    name: Optional[str] = Field(None, description="Nome completo do usuário", examples=["João Silva"])
    is_active: bool = Field(..., description="Indica se o usuário está ativo no sistema", examples=[True])
    is_admin: bool = Field(..., description="Indica se o usuário possui privilégios de administrador", examples=[False])
    created_at: datetime = Field(..., description="Data e hora de criação da conta", examples=["2025-11-07T14:30:00"])

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": 1,
            "email": "joao.silva@empresa.com.br",
            "name": "João Silva",
            "is_active": True,
            "is_admin": False,
            "created_at": "2025-11-07T14:30:00",
        }
    })


class TokenResponse(BaseModel):
    """Token JWT para autenticação"""
    access_token: str = Field(
        ...,
        description="Token JWT Bearer para ser usado no header Authorization",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiaXNzIjoiQ2hhdCBJQSBHTFBJIiwiaWF0IjoxNjk5OTk5OTk5LCJleHAiOjE3MDAwMDM1OTl9.xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"]
    )
    token_type: str = Field(
        default="bearer",
        description="Tipo do token (sempre 'bearer')",
        examples=["bearer"]
    )
    expires_in: int = Field(
        ...,
        description="Tempo de validade do token em segundos (padrão: 3600 = 1 hora)",
        examples=[3600]
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiaXNzIjoiQ2hhdCBJQSBHTFBJIiwiaWF0IjoxNjk5OTk5OTk5LCJleHAiOjE3MDAwMDM1OTl9.xxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "token_type": "bearer",
            "expires_in": 3600
        }
    })
