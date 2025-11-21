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
from app.presentation.api.responses import ApiResponse, ErrorResponse
from app.presentation.api.dependencies import (
    get_current_user,
    get_user_repository,
    get_structured_logger,
)
from app.presentation.api.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    revoke_token,
)
from app.infrastructure.config.settings import get_settings
from app.presentation.api.rate_limiter import limiter

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()

@router.post(
    "/register",
    response_model=ApiResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Registrar novo usuário",
    responses={
        201: {"description": "Usuário criado com sucesso"},
        400: {"description": "Dados inválidos"},
        409: {"description": "Usuário já existe"},
        429: {"description": "Muitas requisições - limite: 5/minuto"},
    },
)
@limiter.limit("5/minute")
async def register(
    request: Request,
    request_data: RegisterRequest,
    user_repo = Depends(get_user_repository),
) -> ApiResponse[UserResponse]:
    """
    Registra novo usuário no sistema.

    Rate limit: 5 requisições por minuto por IP para prevenir spam de registros.
    """
    try:
        structured_logger = get_structured_logger()
        structured_logger.log_auth_attempt(
            operation="REGISTER",
            username=request_data.username,
            email=request_data.email
        )

        existing_user = user_repo.get_user_by_username(request_data.username)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username já está em uso",
            )

        existing_email = user_repo.get_user_by_email(request_data.email)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email já está em uso",
            )

        try:
            hashed_password = hash_password(request_data.password)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

        user_id = user_repo.create_user(
            username=request_data.username,
            email=request_data.email,
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

        structured_logger.log_auth_success(
            operation="REGISTER",
            user_id=user_id,
            username=request_data.username,
            email=request_data.email
        )

        user_response = UserResponse(
            id=user["id"],
            username=user["username"],
            email=user["email"],
            is_active=user["is_active"],
            is_admin=user["is_admin"],
            created_at=user["created_at"],
        )

        return ApiResponse(
            success=True,
            data=user_response,
            message="Usuário criado com sucesso"
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
        403: {"description": "Usuário inativo"},
        429: {"description": "Muitas requisições - limite: 5/minuto"},
    },
)
@limiter.limit("5/minute")
async def login(
    request: Request,
    login_data: LoginRequest,
    user_repo = Depends(get_user_repository),
) -> TokenResponse:
    """
    Realiza login no sistema.

    Rate limit: 5 requisições por minuto por IP para proteção contra ataques de força bruta.
    """
    try:
        structured_logger = get_structured_logger()
        structured_logger.log_auth_attempt(operation="LOGIN", username=login_data.username)

        user = user_repo.get_user_by_username(login_data.username)

        if not user:
            structured_logger.log_auth_failure(
                operation="LOGIN",
                username=login_data.username,
                reason="user_not_found"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Username ou senha incorretos",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not verify_password(login_data.password, user["hashed_password"]):
            structured_logger.log_auth_failure(
                operation="LOGIN",
                username=login_data.username,
                reason="invalid_password"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Username ou senha incorretos",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user["is_active"]:
            structured_logger.log_auth_failure(
                operation="LOGIN",
                username=login_data.username,
                reason="user_inactive"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário inativo. Contate o administrador.",
            )

        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        refresh_token_expires = timedelta(days=settings.refresh_token_expire_days)
        
        access_token = create_access_token(
            data={"sub": str(user["id"]), "username": user["username"], "email": user["email"]},
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

        structured_logger.log_auth_success(
            operation="LOGIN",
            user_id=user["id"],
            username=login_data.username
        )

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
        429: {"description": "Muitas requisições - limite: 10/minuto"},
    },
)
@limiter.limit("10/minute")
async def refresh_token(
    request: Request,
    refresh_data: RefreshTokenRequest,
    user_repo = Depends(get_user_repository),
) -> TokenResponse:
    """
    Renova o access token usando o refresh token.

    Rate limit: 10 requisições por minuto por IP.
    """
    try:
        structured_logger = get_structured_logger()
        structured_logger.log_auth_attempt(operation="REFRESH_TOKEN", username="token_holder")

        payload = decode_refresh_token(refresh_data.refresh_token)

        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido ou expirado",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = int(payload["sub"])

        stored_token = user_repo.get_refresh_token(refresh_data.refresh_token)

        if not stored_token:
            structured_logger.warning(
                "Refresh token não encontrado no banco",
                user_id=user_id
            )
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
            data={"sub": str(user["id"]), "username": user["username"], "email": user["email"]},
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
            user_repo.delete_refresh_token(refresh_data.refresh_token)
            user_repo.store_refresh_token(
                user_id=user["id"],
                token=new_refresh_token,
                expires_at=expires_at,
            )
        except Exception as e:
            logger.warning(f"Falha ao rotacionar refresh token: {e}")
            new_refresh_token = refresh_data.refresh_token

        structured_logger.log_auth_success(
            operation="REFRESH_TOKEN",
            user_id=user["id"],
            username=user["username"]
        )

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
    response_model=ApiResponse[MeResponse],
    summary="Obter informações do usuário autenticado",
    responses={
        200: {"description": "Informações do usuário"},
        401: {"description": "Não autenticado"},
    },
)
async def get_me(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ApiResponse[MeResponse]:
    structured_logger = get_structured_logger()
    structured_logger.info("Consultando /me", user_id=current_user["id"])

    user_response = UserResponse(
        id=current_user["id"],
        username=current_user["username"],
        email=current_user["email"],
        is_active=current_user["is_active"],
        is_admin=current_user["is_admin"],
        created_at=current_user["created_at"],
    )

    me_response = MeResponse(
        user=user_response,
        message="Autenticado com sucesso",
    )

    return ApiResponse(
        success=True,
        data=me_response,
        message="Informações do usuário recuperadas com sucesso"
    )

@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[Dict[str, str]],
    summary="Logout (revoga access token via blacklist)",
    responses={
        200: {"description": "Logout realizado com sucesso"},
        401: {"description": "Não autenticado"},
        429: {"description": "Muitas requisições - limite: 20/minuto"},
    },
)
@limiter.limit("20/minute")
async def logout(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    user_repo = Depends(get_user_repository),
) -> ApiResponse[Dict[str, str]]:
    """
    Realiza logout do usuário, revogando o access token.

    Rate limit: 20 requisições por minuto por IP.
    """
    try:
        structured_logger = get_structured_logger()
        structured_logger.log_auth_attempt(
            operation="LOGOUT",
            username=current_user["username"]
        )

        # Revoke access token via blacklist
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

            revoked = revoke_token(token)
            if revoked:
                structured_logger.info(
                    "Access token revogado via blacklist",
                    user_id=current_user["id"]
                )
            else:
                structured_logger.warning(
                    "Falha ao revogar access token",
                    user_id=current_user["id"]
                )

        # Delete all refresh tokens for the user (invalidate all sessions)
        try:
            deleted_count = user_repo.delete_all_user_refresh_tokens(
                user_id=current_user["id"]
            )
            structured_logger.info(
                "Refresh tokens deletados",
                user_id=current_user["id"],
                count=deleted_count
            )
        except Exception as e:
            logger.warning(
                f"Falha ao deletar refresh tokens do usuário {current_user['id']}: {e}"
            )

        structured_logger.log_auth_success(
            operation="LOGOUT",
            user_id=current_user["id"],
            username=current_user["username"]
        )

        return ApiResponse(
            success=True,
            data={"message": "Logout realizado com sucesso"},
            message="Logout realizado com sucesso"
        )

    except Exception as e:
        logger.error(f"Erro ao fazer logout: {e}", exc_info=True)
        return ApiResponse(
            success=True,
            data={"message": "Logout realizado"},
            message="Logout realizado"
        )