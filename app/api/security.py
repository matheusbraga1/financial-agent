from fastapi import Depends, HTTPException, status, Request
from typing import Dict, Any

from app.api.deps import get_user_service
from app.services.user_service import UserService
from app.utils.security import decode_token


def get_current_user(
    request: Request,
    user_service: UserService = Depends(get_user_service)
) -> Dict[str, Any]:
    auth = request.headers.get('Authorization')
    if not auth or not auth.lower().startswith('bearer '):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais ausentes")
    token = auth.split(' ', 1)[1].strip()
    try:
        payload = decode_token(token)
        jti = payload.get('jti')
        if not jti or user_service.is_token_revoked(jti):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        sub = payload.get('sub')
        if not sub:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
        user = user_service.get_user_by_id(int(sub))
        if not user or not user.get('is_active'):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário inativo ou inexistente")
        # Anexar payload no request state para reutilização (ex.: logout)
        request.state.jwt_payload = payload
        return user
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")


def get_optional_user(
    request: Request,
    user_service: UserService = Depends(get_user_service)
) -> Dict[str, Any] | None:
    auth = request.headers.get('Authorization')
    if not auth or not auth.lower().startswith('bearer '):
        return None
    token = auth.split(' ', 1)[1].strip()
    try:
        payload = decode_token(token)
        jti = payload.get('jti')
        if not jti or user_service.is_token_revoked(jti):
            return None
        sub = payload.get('sub')
        if not sub:
            return None
        user = user_service.get_user_by_id(int(sub))
        if not user or not user.get('is_active'):
            return None
        request.state.jwt_payload = payload
        return user
    except Exception:
        return None
