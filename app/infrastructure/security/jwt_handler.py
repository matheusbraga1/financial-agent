import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel
import secrets
import redis
from functools import lru_cache

class TokenData(BaseModel):
    sub: str  # user_id
    email: str
    roles: list[str] = []
    permissions: list[str] = []
    exp: Optional[datetime] = None
    iat: Optional[datetime] = None
    jti: Optional[str] = None  # JWT ID for revocation
    type: str = "access"  # access or refresh

class JWTHandler:
    """Handler robusto para JWT com suporte a refresh tokens e revogação"""
    
    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7,
        redis_client: Optional[redis.Redis] = None
    ):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_expire = timedelta(minutes=access_token_expire_minutes)
        self.refresh_expire = timedelta(days=refresh_token_expire_days)
        self.redis_client = redis_client  # Para blacklist de tokens
        
    def create_access_token(
        self,
        user_id: str,
        email: str,
        roles: list[str] = None,
        permissions: list[str] = None,
        additional_claims: Dict[str, Any] = None
    ) -> tuple[str, str]:
        """Cria access token com JTI para revogação"""
        jti = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        
        payload = {
            "sub": user_id,
            "email": email,
            "roles": roles or [],
            "permissions": permissions or [],
            "type": "access",
            "iat": now,
            "exp": now + self.access_expire,
            "jti": jti,
            **(additional_claims or {})
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token, jti
    
    def create_refresh_token(self, user_id: str) -> tuple[str, str]:
        """Cria refresh token"""
        jti = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        
        payload = {
            "sub": user_id,
            "type": "refresh",
            "iat": now,
            "exp": now + self.refresh_expire,
            "jti": jti
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        
        # Armazena refresh token no Redis para controle
        if self.redis_client:
            self.redis_client.setex(
                f"refresh_token:{jti}",
                self.refresh_expire,
                user_id
            )
        
        return token, jti
    
    def decode_token(self, token: str) -> Optional[TokenData]:
        """Decodifica e valida token"""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            
            # Verifica se token está na blacklist
            if self.redis_client:
                jti = payload.get("jti")
                if jti and self.redis_client.exists(f"blacklist:{jti}"):
                    return None
            
            return TokenData(**payload)
            
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    def revoke_token(self, jti: str, exp: datetime) -> bool:
        """Revoga token adicionando à blacklist"""
        if not self.redis_client:
            return False
        
        ttl = int((exp - datetime.now(timezone.utc)).total_seconds())
        if ttl > 0:
            self.redis_client.setex(f"blacklist:{jti}", ttl, "1")
            return True
        return False
    
    def refresh_access_token(self, refresh_token: str) -> Optional[tuple[str, str]]:
        """Gera novo access token a partir do refresh token"""
        token_data = self.decode_token(refresh_token)
        
        if not token_data or token_data.type != "refresh":
            return None
        
        # Verifica se refresh token está válido no Redis
        if self.redis_client:
            if not self.redis_client.exists(f"refresh_token:{token_data.jti}"):
                return None
        
        # Busca dados atualizados do usuário (implementar conforme necessário)
        # user = get_user_by_id(token_data.sub)
        
        # Cria novo access token
        return self.create_access_token(
            user_id=token_data.sub,
            email="",  # Buscar do banco
            roles=[],  # Buscar do banco
            permissions=[]  # Buscar do banco
        )

# app/presentation/api/middleware/auth.py
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, List

class JWTBearer(HTTPBearer):
    """Middleware de autenticação JWT melhorado"""
    
    def __init__(
        self,
        jwt_handler: JWTHandler,
        required_roles: List[str] = None,
        required_permissions: List[str] = None,
        auto_error: bool = True
    ):
        super().__init__(auto_error=auto_error)
        self.jwt_handler = jwt_handler
        self.required_roles = required_roles or []
        self.required_permissions = required_permissions or []
    
    async def __call__(self, request: Request) -> Optional[TokenData]:
        credentials: HTTPAuthorizationCredentials = await super().__call__(request)
        
        if not credentials:
            if self.auto_error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Autenticação necessária",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            return None
        
        # Decodifica token
        token_data = self.jwt_handler.decode_token(credentials.credentials)
        
        if not token_data:
            if self.auto_error:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token inválido ou expirado",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            return None
        
        # Verifica roles
        if self.required_roles:
            if not any(role in token_data.roles for role in self.required_roles):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permissão insuficiente - role necessária"
                )
        
        # Verifica permissions
        if self.required_permissions:
            if not any(perm in token_data.permissions for perm in self.required_permissions):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permissão insuficiente"
                )
        
        # Adiciona dados do usuário ao request state
        request.state.user = token_data
        return token_data