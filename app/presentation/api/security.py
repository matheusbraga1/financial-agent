import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import jwt
from passlib.context import CryptContext

from app.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password = password_bytes[:72].decode('utf-8', errors='ignore')

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
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.access_token_expire_minutes
        )
    
    jti = secrets.token_urlsafe(32)

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "jti": jti,
        "type": "access",
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    
    return encoded_jwt

def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            days=settings.refresh_token_expire_days
        )

    jti = secrets.token_urlsafe(32)

    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "jti": jti,
        "type": "refresh",
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    
    return encoded_jwt

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        
        if payload.get("type") != "access":
            logger.warning("Token não é do tipo 'access'")
            return None

        if "sub" not in payload:
            logger.warning("Token sem 'sub' (user_id)")
            return None

        return payload

    except jwt.ExpiredSignatureError:
        logger.debug("Token expirado")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Token inválido: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro ao decodificar token: {e}")
        return None

def decode_refresh_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )

        if payload.get("type") != "refresh":
            logger.warning("Token não é do tipo 'refresh'")
            return None

        if "sub" not in payload:
            logger.warning("Token sem 'sub' (user_id)")
            return None

        return payload

    except jwt.ExpiredSignatureError:
        logger.debug("Refresh token expirado")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Refresh token inválido: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro ao decodificar refresh token: {e}")
        return None

def revoke_token(token: str) -> bool:
    try:
        from app.presentation.api.dependencies import get_jwt_handler

        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False}
        )

        jti = payload.get("jti")
        exp = payload.get("exp")

        if not jti or not exp:
            logger.warning("Token sem jti ou exp - não pode ser revogado")
            return False

        exp_datetime = datetime.fromtimestamp(exp)

        jwt_handler = get_jwt_handler()
        return jwt_handler.revoke_token(jti, exp_datetime)

    except Exception as e:
        logger.error(f"Erro ao revogar token: {e}")
        return False