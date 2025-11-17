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
from app.infrastructure.repositories.user_repository import SQLiteUserRepository

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
async def register(
    request: RegisterRequest,
    user_repo: SQLiteUserRepository = Depends(get_user_repository),
) -> ApiResponse[UserResponse]:
    """Registra um novo usuário no sistema."""
    try:
        structured_logger = get_structured_logger()
        structured_logger.info(
            "Tentativa de registro",
            username=request.username,
            email=request.email
        )
        
        # Validar se usuário já existe
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
        
        # Hash da senha (agora valida comprimento dentro da função)
        try:
            hashed_password = hash_password(request.password)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        
        # Criar usuário
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
        
        structured_logger.info(
            "Usuário registrado com sucesso",
            user_id=user_id,
            username=request.username
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
    },
)
async def login(
    request: LoginRequest,
    user_repo: SQLiteUserRepository = Depends(get_user_repository),
) -> TokenResponse:
    """Autentica usuário e retorna tokens JWT."""
    try:
        structured_logger = get_structured_logger()
        structured_logger.info("Tentativa de login", username=request.username)
        
        # Buscar usuário
        user = user_repo.get_user_by_username(request.username)
        
        if not user:
            structured_logger.warning(
                "Login falhou - usuário não encontrado",
                username=request.username
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Username ou senha incorretos",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verificar senha
        if not verify_password(request.password, user["hashed_password"]):
            structured_logger.warning(
                "Login falhou - senha incorreta",
                username=request.username
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Username ou senha incorretos",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verificar se usuário está ativo
        if not user["is_active"]:
            structured_logger.warning(
                "Login falhou - usuário inativo",
                username=request.username
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário inativo. Contate o administrador.",
            )
        
        # Gerar tokens
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
        
        # Armazenar refresh token no banco (legado - novo handler já armazena no Redis)
        from datetime import datetime
        expires_at = datetime.utcnow() + refresh_token_expires
        
        try:
            user_repo.store_refresh_token(
                user_id=user["id"],
                token=refresh_token,
                expires_at=expires_at,
            )
        except Exception as e:
            logger.warning(f"Falha ao armazenar refresh token no SQLite: {e}")
        
        structured_logger.info(
            "Login bem-sucedido",
            user_id=user["id"],
            username=request.username
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
    },
)
async def refresh_token(
    request: RefreshTokenRequest,
    user_repo: SQLiteUserRepository = Depends(get_user_repository),
) -> TokenResponse:
    """Renova access token usando refresh token válido."""
    try:
        structured_logger = get_structured_logger()
        structured_logger.info("Tentativa de refresh token")
        
        # Decodificar refresh token
        payload = decode_refresh_token(request.refresh_token)

        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token inválido ou expirado",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = int(payload["sub"])

        # Verificar se refresh token está no banco (validação adicional)
        stored_token = user_repo.get_refresh_token(request.refresh_token)

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

        # Buscar usuário
        user = user_repo.get_user_by_id(user_id)
        
        if not user or not user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário inválido ou inativo",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Gerar novos tokens
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
        
        # Rotação de refresh token
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
        
        structured_logger.info("Token renovado com sucesso", user_id=user["id"])
        
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
    """Retorna informações do usuário autenticado."""
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
    },
)
async def logout(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    user_repo: SQLiteUserRepository = Depends(get_user_repository),
) -> ApiResponse[Dict[str, str]]:
    """
    Logout do usuário.
    
    NOVO: Agora revoga o access token via blacklist Redis!
    """
    try:
        structured_logger = get_structured_logger()
        structured_logger.info("Logout iniciado", user_id=current_user["id"])

        # Extrair token do header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            
            # NOVO: Revogar token via blacklist
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
        
        structured_logger.info("Logout processado", user_id=current_user["id"])

        return ApiResponse(
            success=True,
            data={"message": "Logout realizado com sucesso"},
            message="Logout realizado com sucesso"
        )

    except Exception as e:
        logger.error(f"Erro ao fazer logout: {e}", exc_info=True)
        # Mesmo com erro, retorna sucesso (idempotente)
        return ApiResponse(
            success=True,
            data={"message": "Logout realizado"},
            message="Logout realizado"
        )