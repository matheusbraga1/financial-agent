from fastapi import Depends, HTTPException, status, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any, Optional

from app.api.deps import get_user_service
from app.services.user_service import UserService
from app.utils.security import decode_token


_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
    user_service: UserService = Depends(get_user_service),
) -> Dict[str, Any]:
    import asyncio

    if (
        credentials is None
        or credentials.scheme is None
        or credentials.scheme.lower() != "bearer"
        or not credentials.credentials
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais ausentes"
        )
    token = credentials.credentials.strip()
    try:
        payload = decode_token(token)
        jti = payload.get("jti")
        loop = asyncio.get_running_loop()

        # Verificar token revogado em thread pool (SQLite)
        is_revoked = await loop.run_in_executor(None, user_service.is_token_revoked, jti)
        if not jti or is_revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido"
            )

        sub = payload.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido"
            )

        # Buscar usuário em thread pool (SQLite)
        user = await loop.run_in_executor(None, user_service.get_user_by_id, int(sub))
        if not user or not user.get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário inativo ou inexistente",
            )

        # Anexar payload no request state para reutilização (ex.: logout)
        request.state.jwt_payload = payload
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido"
        )


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
    user_service: UserService = Depends(get_user_service),
) -> Optional[Dict[str, Any]]:
    import asyncio

    if (
        credentials is None
        or credentials.scheme is None
        or credentials.scheme.lower() != "bearer"
        or not credentials.credentials
    ):
        return None
    token = credentials.credentials.strip()
    try:
        payload = decode_token(token)
        jti = payload.get("jti")
        loop = asyncio.get_running_loop()

        # Verificar token revogado em thread pool
        is_revoked = await loop.run_in_executor(None, user_service.is_token_revoked, jti)
        if not jti or is_revoked:
            return None

        sub = payload.get("sub")
        if not sub:
            return None

        # Buscar usuário em thread pool
        user = await loop.run_in_executor(None, user_service.get_user_by_id, int(sub))
        if not user or not user.get("is_active"):
            return None

        request.state.jwt_payload = payload
        return user
    except Exception:
        return None
