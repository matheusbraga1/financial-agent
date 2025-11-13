import os
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

import jwt

from app.core.config import get_settings

settings = get_settings()

def create_tokens(user_id: int, is_admin: bool = False) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    
    access_exp = now + timedelta(minutes=settings.access_token_expire_minutes)
    access_jti = secrets.token_hex(16)
    access_payload = {
        'sub': str(user_id),
        'iss': settings.app_name,
        'iat': int(now.timestamp()),
        'exp': int(access_exp.timestamp()),
        'jti': access_jti,
        'type': 'access',
        'is_admin': is_admin,
    }
    access_token = jwt.encode(
        access_payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm
    )
    
    refresh_exp = now + timedelta(days=7)
    refresh_jti = secrets.token_hex(16)
    refresh_payload = {
        'sub': str(user_id),
        'iss': settings.app_name,
        'iat': int(now.timestamp()),
        'exp': int(refresh_exp.timestamp()),
        'jti': refresh_jti,
        'type': 'refresh',
    }
    refresh_token = jwt.encode(
        refresh_payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm
    )
    
    return {
        'access_token': access_token,
        'access_jti': access_jti,
        'access_expires_at': access_exp,
        'refresh_token': refresh_token,
        'refresh_jti': refresh_jti,
        'refresh_expires_at': refresh_exp,
    }


def create_access_token(user_id: int, is_admin: bool = False) -> str:
    tokens = create_tokens(user_id, is_admin)
    return tokens['access_token']


def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"verify_exp": True}
    )

def _pbkdf2_hash(password: str, salt: bytes, iterations: int = 200_000) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)


def hash_password(password: str, iterations: int | None = None) -> str:
    if not password or len(password) < 8:
        raise ValueError("Senha muito curta")
    settings = get_settings()
    ci = os.getenv("CI", "").lower() in ("1", "true", "yes")
    iters = (
        iterations
        if iterations is not None
        else (settings.password_hash_iterations_dev if (settings.debug or ci) else settings.password_hash_iterations)
    )
    salt = secrets.token_bytes(16)
    digest = _pbkdf2_hash(password, salt, iters)
    return f"pbkdf2${iters}${salt.hex()}${digest.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    try:
        scheme, iters_s, salt_hex, digest_hex = hashed.split('$', 3)
        if scheme != 'pbkdf2':
            return False
        iterations = int(iters_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        computed = _pbkdf2_hash(password, salt, iterations)
        return hmac.compare_digest(computed, expected)
    except Exception:
        return False


def create_access_token(subject: str, claims: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.access_token_expire_minutes)
    jti = secrets.token_hex(16)
    payload = {
        'sub': subject,
        'iss': settings.app_name,
        'iat': int(now.timestamp()),
        'exp': int(exp.timestamp()),
        'jti': jti,
    }
    if claims:
        payload.update(claims)
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {
        'token': token,
        'jti': jti,
        'exp': exp,
    }


def decode_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
