from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum
from .validators import AdvancedValidators

class UserRole(str, Enum):
    """Roles do sistema"""
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    GUEST = "guest"

class UserStatus(str, Enum):
    """Status do usuário"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"

class UserCreateRequest(BaseModel):
    """Request para criar usuário"""
    email: str = Field(..., description="Email do usuário")
    password: str = Field(..., min_length=8, description="Senha forte")
    name: str = Field(..., min_length=2, max_length=100, description="Nome completo")
    phone: Optional[str] = Field(None, description="Telefone com DDD")
    cpf: Optional[str] = Field(None, description="CPF do usuário")
    role: UserRole = Field(UserRole.USER, description="Role do usuário")
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        return AdvancedValidators.validate_email(v)
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        return AdvancedValidators.validate_password(v)
    
    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        if v:
            return AdvancedValidators.validate_phone(v)
        return v
    
    @field_validator('cpf')
    @classmethod
    def validate_cpf(cls, v):
        if v:
            return AdvancedValidators.validate_cpf(v)
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "usuario@example.com",
                "password": "SenhaForte@123",
                "name": "João da Silva",
                "phone": "11987654321",
                "cpf": "12345678901",
                "role": "user"
            }
        }

class UserResponse(BaseModel):
    """Response com dados do usuário"""
    id: str = Field(..., description="ID único do usuário")
    email: str = Field(..., description="Email do usuário")
    name: str = Field(..., description="Nome completo")
    phone: Optional[str] = Field(None, description="Telefone")
    cpf: Optional[str] = Field(None, description="CPF mascarado")
    role: UserRole = Field(..., description="Role do usuário")
    status: UserStatus = Field(..., description="Status da conta")
    email_verified: bool = Field(..., description="Email verificado")
    created_at: datetime = Field(..., description="Data de criação")
    updated_at: datetime = Field(..., description="Última atualização")
    last_login: Optional[datetime] = Field(None, description="Último login")
    permissions: List[str] = Field(default_factory=list, description="Permissões do usuário")
    
    @field_validator('cpf')
    @classmethod
    def mask_cpf(cls, v):
        """Mascara CPF para resposta"""
        if v and len(v) == 11:
            return f"{v[:3]}.***.**{v[-2:]}"
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "usuario@example.com",
                "name": "João da Silva",
                "phone": "11987654321",
                "cpf": "123.***.**-01",
                "role": "user",
                "status": "active",
                "email_verified": True,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "last_login": "2024-01-01T10:00:00Z",
                "permissions": ["read:profile", "write:profile"]
            }
        }