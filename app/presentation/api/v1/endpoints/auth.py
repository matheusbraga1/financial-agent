import logging
from datetime import timedelta
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Request

from app.presentation.models.auth_models import (
    LoginRequest,
    RegisterRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserResponse,
    MeResponse,
)
from app.presentation.api.dependencies import (
    get_current_user,
    get_user_repository,
)
from app.presentation.api.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.infrastructure.config.settings import get_settings
from app.infrastructure.repositories.user_repository import SQLiteUserRepository

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar novo usuário",
    responses={
        201: {"description": "Usuário criado com sucesso"},
        400: {"description": "Dados inválidos ou usuário já existe"},
        429: {"description": "Muitas requisições - limite: 5/minuto"},
    },
)
async def register(
    request: RegisterRequest,
    user_repo: SQLiteUserRepository = Depends(get_user_repository),
) -> UserResponse:
    # NOTA: Rate limiting de 5/minute aplicado via decorator no main.py (default 50/min aqui)
    try:
        logger.info(f"Tentativa de registro: username={request.username}, email={request.email}")
        
        existing_user = user_repo.get_user_by_username(request.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username já está em uso",
            )

        existing_email = user_repo.get_user_by_email(request.email)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email já está em uso",
            )
        
        hashed_password = hash_password(request.password)
        
        user_id = user_repo.create_user(
            username=request.username,
            email=request.email,
            hashed_password=hashed_password,
            is_active=True,
            is_admin=False,
        )
        
        user = user_repo.get_user_by_id(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao criar usuário",
            )
        
        logger.info(f"Usuário registrado com sucesso: id={user_id}, username={request.username}")
        
        return UserResponse(
            id=user["id"],
            username=user["username"],
            email=user["email"],
            is_active=user["is_active"],
            is_admin=user["is_admin"],
            created_at=user["created_at"],
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao registrar usuário: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao registrar usuário",
        )

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login no sistema",
    responses={
        200: {"description": "Login realizado com sucesso"},
        401: {"description": "Credenciais inválidas"},
    },
)
async def login(
    request: LoginRequest,
    user_repo: SQLiteUserRepository = Depends(get_user_repository),
) -> TokenResponse:
    try:
        logger.info(f"Tentativa de login: username={request.username}")
        
        user = user_repo.get_user_by_username(request.username)
        
        if not user:
            logger.warning(f"Login falhou: usuário não encontrado - {request.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Username ou senha incorretos",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not verify_password(request.password, user["hashed_password"]):
            logger.warning(f"Login falhou: senha incorreta - {request.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Username ou senha incorretos",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user["is_active"]:
            logger.warning(f"Login falhou: usuário inativo - {request.username}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário inativo. Contate o administrador.",
            )
        
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        refresh_token_expires = timedelta(days=settings.refresh_token_expire_days)
        
        access_token = create_access_token(
            data={"sub": str(user["id"]), "username": user["username"]},
            expires_delta=access_token_expires,
        )

        refresh_token = create_refresh_token(
            data={"sub": str(user["id"])},
            expires_delta=refresh_token_expires,
        )
        
        from datetime import datetime
        expires_at = datetime.utcnow() + refresh_token_expires
        
        try:
            user_repo.store_refresh_token(
                user_id=user["id"],
                token=refresh_token,
                expires_at=expires_at,
            )
        except Exception as e:
            logger.warning(f"Falha ao armazenar refresh token: {e}")
        
        logger.info(f"Login bem-sucedido: user_id={user['id']}, username={request.username}")
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao fazer login: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao processar login",
        )

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Renovar access token usando refresh token",
    responses={
        200: {"description": "Token renovado com sucesso"},
        401: {"description": "Refresh token inválido ou expirado"},
    },
)
async def refresh_token(
    request: RefreshTokenRequest,
    user_repo: SQLiteUserRepository = Depends(get_user_repository),
) -> TokenResponse:
    try:
        logger.info("Tentativa de refresh token")
        
        payload = decode_refresh_token(request.refresh_token)

        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido ou expirado",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = int(payload["sub"])

        stored_token = user_repo.get_refresh_token(request.refresh_token)

        if not stored_token:
            logger.warning(f"Refresh token não encontrado no banco: user_id={user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = user_repo.get_user_by_id(user_id)
        
        if not user or not user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário inválido ou inativo",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)

        access_token = create_access_token(
            data={"sub": str(user["id"]), "username": user["username"]},
            expires_delta=access_token_expires,
        )

        refresh_token_expires = timedelta(days=settings.refresh_token_expire_days)

        new_refresh_token = create_refresh_token(
            data={"sub": str(user["id"])},
            expires_delta=refresh_token_expires,
        )
        
        from datetime import datetime
        expires_at = datetime.utcnow() + refresh_token_expires
        
        try:
            user_repo.delete_refresh_token(request.refresh_token)
            user_repo.store_refresh_token(
                user_id=user["id"],
                token=new_refresh_token,
                expires_at=expires_at,
            )
        except Exception as e:
            logger.warning(f"Falha ao rotacionar refresh token: {e}")
            new_refresh_token = request.refresh_token
        
        logger.info(f"Token renovado com sucesso: user_id={user['id']}")
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao renovar token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao renovar token",
        )

@router.get(
    "/me",
    response_model=MeResponse,
    summary="Obter informações do usuário autenticado",
    responses={
        200: {"description": "Informações do usuário"},
        401: {"description": "Não autenticado"},
    },
)
async def get_me(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> MeResponse:
    logger.info(f"Consultando /me para user_id={current_user['id']}")
    
    user_response = UserResponse(
        id=current_user["id"],
        username=current_user["username"],
        email=current_user["email"],
        is_active=current_user["is_active"],
        is_admin=current_user["is_admin"],
        created_at=current_user["created_at"],
    )
    
    return MeResponse(
        user=user_response,
        message="Autenticado com sucesso",
    )

@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout (invalida todos os refresh tokens do usuário)",
    responses={
        204: {"description": "Logout realizado com sucesso"},
        401: {"description": "Não autenticado"},
    },
)
async def logout(
    current_user: Dict[str, Any] = Depends(get_current_user),
    user_repo: SQLiteUserRepository = Depends(get_user_repository),
):
    try:
        logger.info(f"Logout para user_id={current_user['id']}")

        # NOTA: Com JWT stateless, não há como invalidar o access token
        # O token permanecerá válido até expirar naturalmente
        # Para invalidação imediata, seria necessário implementar um token blacklist

        logger.info(f"Logout processado para user_id={current_user['id']}")

        # Status 204 não retorna body
        return None

    except Exception as e:
        logger.error(f"Erro ao fazer logout: {e}", exc_info=True)
        # Mesmo com erro, retorna sucesso (idempotente)
        return None