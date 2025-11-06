from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict
from datetime import datetime

from app.models.auth import RegisterRequest, LoginRequest, TokenResponse, UserPublic
from app.models.error import ErrorResponse
from app.api.deps import get_user_service
from app.services.user_service import UserService
from app.utils.security import hash_password, verify_password, create_access_token
from app.api.security import get_current_user


router = APIRouter()


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar novo usuário",
    responses={
        201: {"description": "Usuário criado"},
        400: {"description": "Dados inválidos", "model": ErrorResponse},
        409: {"description": "Email já cadastrado", "model": ErrorResponse},
        500: {"description": "Erro interno", "model": ErrorResponse},
    },
)
def register(req: RegisterRequest, user_service: UserService = Depends(get_user_service)) -> UserPublic:
    existing = user_service.get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email já cadastrado")
    pwd_hash = hash_password(req.password)
    user = user_service.create_user(req.email, pwd_hash, req.name)
    return UserPublic(
        id=user['id'],
        email=user['email'],
        name=user.get('name'),
        is_active=bool(user.get('is_active')),
        is_admin=bool(user.get('is_admin')),
        created_at=datetime.fromisoformat(user['created_at'])
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login com credenciais",
    responses={
        200: {"description": "Token gerado"},
        400: {"description": "Dados inválidos", "model": ErrorResponse},
        401: {"description": "Credenciais inválidas", "model": ErrorResponse},
        500: {"description": "Erro interno", "model": ErrorResponse},
    }
)
def login(req: LoginRequest, user_service: UserService = Depends(get_user_service)) -> TokenResponse:
    user = user_service.get_user_by_email(req.email)
    if not user or not verify_password(req.password, user['password_hash']):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    extra = {
        'email': user['email'],
        'name': user.get('name'),
        'is_admin': bool(user.get('is_admin')),
    }
    tok = create_access_token(subject=str(user['id']), claims=extra)
    return TokenResponse(access_token=tok['token'], expires_in=int((tok['exp'] - datetime.now(tok['exp'].tzinfo)).total_seconds()))


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout (revoga token atual)",
    responses={
        204: {"description": "Desconectado"},
        401: {"description": "Não autorizado", "model": ErrorResponse},
        500: {"description": "Erro interno", "model": ErrorResponse},
    }
)
def logout(request: 'Request', current_user=Depends(get_current_user), user_service: UserService = Depends(get_user_service)):
    # Revoga o token atual usando o payload anexado pelo dependency
    payload = getattr(request.state, 'jwt_payload', None)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    jti = payload.get('jti')
    exp = payload.get('exp')
    if not jti or not exp:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    from datetime import datetime, timezone
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    user_service.revoke_token(jti, expires_at)
    return None


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Dados do usuário logado",
    responses={
        200: {"description": "Usuário atual"},
        401: {"description": "Não autorizado", "model": ErrorResponse},
    }
)
def me(current_user=Depends(get_current_user)) -> UserPublic:
    return UserPublic(
        id=current_user['id'],
        email=current_user['email'],
        name=current_user.get('name'),
        is_active=bool(current_user.get('is_active')),
        is_admin=bool(current_user.get('is_admin')),
        created_at=datetime.fromisoformat(current_user['created_at'])
    )
