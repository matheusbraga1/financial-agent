from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, field_validator

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Senha com mínimo 8 caracteres"
    )

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Senha deve conter pelo menos uma letra maiúscula")
        if not any(c.islower() for c in v):
            raise ValueError("Senha deve conter pelo menos uma letra minúscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("Senha deve conter pelo menos um número")
        return v

class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Refresh token JWT")

class TokenResponse(BaseModel):
    access_token: str = Field(..., description="Access token JWT")
    refresh_token: str = Field(..., description="Refresh token JWT")
    token_type: str = Field(default="bearer")
    expires_in: int = Field(..., description="Segundos até expiração")


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    is_active: bool
    is_admin: bool
    created_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class MeResponse(BaseModel):
    user: UserResponse
    message: str = "Autenticado com sucesso"