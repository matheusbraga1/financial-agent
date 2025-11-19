import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from passlib.context import CryptContext

from app.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError(
            "Senha muito curta. Mínimo de 8 caracteres necessário."
        )
    
    if len(password) > 72:
        raise ValueError(
            "Senha muito longa. Máximo de 72 caracteres permitido."
        )

    rounds = 10 if settings.debug else 12

    return pwd_context.using(bcrypt__rounds=rounds).hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Erro ao verificar senha: {e}")
        return False

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    from app.presentation.api.dependencies import get_jwt_handler

    jwt_handler = get_jwt_handler()

    user_id = data.get("sub")
    email = data.get("email", "")
    username = data.get("username", "")

    token, jti = jwt_handler.create_access_token(
        user_id=user_id,
        email=email,
        roles=[],
        permissions=[],
        additional_claims={"username": username}
    )

    return token

def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    from app.presentation.api.dependencies import get_jwt_handler

    jwt_handler = get_jwt_handler()

    user_id = data.get("sub")

    token, jti = jwt_handler.create_refresh_token(user_id=user_id)

    return token

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    from app.presentation.api.dependencies import get_jwt_handler

    jwt_handler = get_jwt_handler()
    token_data = jwt_handler.decode_token(token)

    if not token_data:
        return None

    if token_data.type != "access":
        logger.warning("Token não é do tipo 'access'")
        return None

    return {
        "sub": token_data.sub,
        "email": token_data.email,
        "username": token_data.sub,
        "type": token_data.type,
    }

def decode_refresh_token(token: str) -> Optional[Dict[str, Any]]:
    from app.presentation.api.dependencies import get_jwt_handler

    jwt_handler = get_jwt_handler()
    token_data = jwt_handler.decode_token(token)

    if not token_data:
        return None

    if token_data.type != "refresh":
        logger.warning("Token não é do tipo 'refresh'")
        return None

    return {
        "sub": token_data.sub,
        "type": token_data.type,
    }

def revoke_token(token: str) -> bool:
    from app.presentation.api.dependencies import get_jwt_handler

    jwt_handler = get_jwt_handler()

    token_data = jwt_handler.decode_token(token)

    if not token_data or not token_data.jti or not token_data.exp:
        logger.warning("Token inválido ou sem JTI/exp para revogação")
        return False

    success = jwt_handler.revoke_token(token_data.jti, token_data.exp)

    if success:
        logger.info(f"Token revogado com sucesso: jti={token_data.jti}")
    else:
        logger.warning(f"Falha ao revogar token: jti={token_data.jti}")

    return success