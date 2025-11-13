from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Dict, Any
import logging

import jwt
from datetime import datetime, timezone

from app.models.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse, TokenRefreshRequest
from app.models.error import ErrorResponse
from app.services.user_service import UserService
from app.api.deps import get_user_service
from app.api.security import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar novo usuário",
    responses={
        201: {"description": "Usuário criado com sucesso"},
        400: {"description": "Email já existe ou dados inválidos", "model": ErrorResponse},
        429: {"description": "Rate limit exceeded", "model": ErrorResponse},
    },
)
async def register(
    request: Request,
    req: RegisterRequest,
    user_service: UserService = Depends(get_user_service),
) -> TokenResponse:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    
    limiter = Limiter(key_func=get_remote_address)
    
    try:
        await limiter.check_limit("3/hour", key_func=get_remote_address)(request)
    except Exception:
        pass
    
    import asyncio
    loop = asyncio.get_running_loop()

    try:
        user = await loop.run_in_executor(
            None,
            user_service.create_user,
            req.email,
            req.password,
            req.full_name,
        )

        from app.utils.security import create_tokens
        from datetime import datetime, timezone
    
        tokens = create_tokens(user["id"], is_admin=user.get("is_admin", False))

        logger.info(f"Novo usuário registrado: {req.email}")
    
        return TokenResponse(
            access_token=tokens['access_token'],
            refresh_token=tokens['refresh_token'],
            expires_in=int(
                (tokens['access_expires_at'] - datetime.now(timezone.utc)).total_seconds()
            ),
            expires_at=tokens['access_expires_at'].isoformat(),
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                full_name=user["full_name"],
                is_admin=user.get("is_admin", False),
            ),
        )

    except ValueError as e:
        logger.warning(f"Erro ao registrar usuário {req.email}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login de usuário",
    responses={
        200: {"description": "Login bem-sucedido"},
        401: {"description": "Credenciais inválidas", "model": ErrorResponse},
        429: {"description": "Rate limit exceeded", "model": ErrorResponse},
    },
)
async def login(
    request: Request,
    req: LoginRequest,
    user_service: UserService = Depends(get_user_service),
) -> TokenResponse:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    
    limiter = Limiter(key_func=get_remote_address)
    
    try:
        await limiter.check_limit("5/minute", key_func=get_remote_address)(request)
    except Exception:
        pass
    
    import asyncio
    loop = asyncio.get_running_loop()

    try:
        user = await loop.run_in_executor(
            None, user_service.authenticate_user, req.email, req.password
        )

        if not user:
            logger.warning(f"Tentativa de login falhou para: {req.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email ou senha incorretos",
            )

        from app.utils.security import create_tokens
        from datetime import datetime, timezone
        
        tokens = create_tokens(user["id"], is_admin=user.get("is_admin", False))

        logger.info(f"Login bem-sucedido: {req.email}")
        
        return TokenResponse(
            access_token=tokens['access_token'],
            refresh_token=tokens['refresh_token'],
            expires_in=int(
                (tokens['access_expires_at'] - datetime.now(timezone.utc)).total_seconds()
            ),
            expires_at=tokens['access_expires_at'].isoformat(),
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                full_name=user["full_name"],
                is_admin=user.get("is_admin", False),
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao fazer login: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao processar login",
        )

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Obter usuário atual",
    responses={
        200: {"description": "Dados do usuário"},
        401: {"description": "Não autenticado", "model": ErrorResponse},
    },
)
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        full_name=current_user.get("full_name", ""),
        is_admin=current_user.get("is_admin", False),
    )

@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout de usuário",
    responses={
        204: {"description": "Logout bem-sucedido"},
        401: {"description": "Não autenticado", "model": ErrorResponse},
    },
)
async def logout(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    
    limiter = Limiter(key_func=get_remote_address)
    
    try:
        await limiter.check_limit("10/minute", key_func=get_remote_address)(request)
    except Exception:
        pass
    
    import asyncio
    loop = asyncio.get_running_loop()

    try:
        jti = current_user.get("jti")
        if jti:
            await loop.run_in_executor(None, user_service.revoke_token, jti)
            logger.info(f"Token revogado para usuário: {current_user['email']}")
    except Exception as e:
        logger.error(f"Erro ao revogar token: {e}")

    return None

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Renovar access token",
    responses={
    200: {"description": "Novo access token gerado"},
    401: {"description": "Refresh token inválido ou expirado", "model": ErrorResponse},
    400: {"description": "Dados inválidos", "model": ErrorResponse},
    429: {"description": "Rate limit exceeded", "model": ErrorResponse},
    },
)
async def refresh_token(
    request: Request,
    req: TokenRefreshRequest,
    user_service: UserService = Depends(get_user_service),
) -> TokenResponse:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    
    limiter = Limiter(key_func=get_remote_address)
    
    try:
        await limiter.check_limit("10/minute", key_func=get_remote_address)(request)
    except Exception:
        pass
    
    import asyncio
    loop = asyncio.get_running_loop()

    try:
        from app.utils.security import decode_token, create_tokens
        
        payload = decode_token(req.refresh_token)
        
        if payload.get('type') != 'refresh':
            logger.warning(f"Tentativa de refresh com token inválido: type={payload.get('type')}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token type inválido. Use refresh token, não access token."
            )
    
        jti = payload.get('jti')
        user_id = payload.get('sub')
    
        if not jti or not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token malformado"
            )
            
        is_revoked = await loop.run_in_executor(None, user_service.is_token_revoked, jti)
        if is_revoked:
            logger.warning(f"Tentativa de uso de refresh token revogado: jti={jti}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token foi revogado. Faça login novamente."
            )
        
        user = await loop.run_in_executor(None, user_service.get_user_by_id, int(user_id))
        if not user:
            logger.warning(f"Refresh token para usuário inexistente: user_id={user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário não encontrado"
            )
    
        if not user.get('is_active', True):
            logger.warning(f"Refresh token para usuário inativo: user_id={user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário inativo"
            )
            
        await loop.run_in_executor(None, user_service.revoke_token, jti)
        
        tokens = create_tokens(user['id'], is_admin=user.get('is_admin', False))
        
        logger.info(f"Access token renovado com sucesso para user_id={user_id}")
        
        return TokenResponse(
            access_token=tokens['access_token'],
            refresh_token=tokens['refresh_token'],
            expires_in=int(
                (tokens['access_expires_at'] - datetime.now(timezone.utc)).total_seconds()
            ),
            expires_at=tokens['access_expires_at'].isoformat(),
            user=UserResponse(
                id=user["id"],
                email=user["email"],
                full_name=user["full_name"],
                is_admin=user.get("is_admin", False),
            ),
        )
    
    except jwt.ExpiredSignatureError:
        logger.warning("Tentativa de refresh com token expirado")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expirado. Faça login novamente."
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Refresh token inválido: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao processar refresh token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao renovar token"
        )