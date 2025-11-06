import os
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

import jwt

from app.core.config import get_settings


def _pbkdf2_hash(password: str, salt: bytes, iterations: int = 200_000) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)


def hash_password(password: str, iterations: int = 200_000) -> str:
    if not password or len(password) < 8:
        raise ValueError("Senha muito curta")
    salt = secrets.token_bytes(16)
    digest = _pbkdf2_hash(password, salt, iterations)
    return f"pbkdf2${iterations}${salt.hex()}${digest.hex()}"


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

