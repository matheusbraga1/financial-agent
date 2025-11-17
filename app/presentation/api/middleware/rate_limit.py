from fastapi import Request, HTTPException, status
from typing import Optional, Callable
import time
import redis
from dataclasses import dataclass

@dataclass
class RateLimitConfig:
    """Configuração de rate limit"""
    requests: int  # Número de requisições
    window: int    # Janela de tempo em segundos
    strategy: str = "sliding_window"  # ou "fixed_window"

class AdvancedRateLimiter:
    """Rate limiter avançado com diferentes estratégias"""
    
    def __init__(
        self,
        redis_client: redis.Redis,
        config: RateLimitConfig,
        key_func: Optional[Callable] = None
    ):
        self.redis = redis_client
        self.config = config
        self.key_func = key_func or self._default_key_func
    
    def _default_key_func(self, request: Request) -> str:
        """Gera chave padrão baseada em IP"""
        client_ip = request.client.host
        return f"rate_limit:{client_ip}:{request.url.path}"
    
    async def check_rate_limit(self, request: Request) -> tuple[bool, dict]:
        """Verifica rate limit e retorna status com metadados"""
        key = self.key_func(request)
        
        if self.config.strategy == "sliding_window":
            return await self._sliding_window_check(key)
        else:
            return await self._fixed_window_check(key)
    
    async def _sliding_window_check(self, key: str) -> tuple[bool, dict]:
        """Implementa sliding window rate limiting"""
        now = time.time()
        window_start = now - self.config.window
        
        # Remove registros antigos
        self.redis.zremrangebyscore(key, 0, window_start)
        
        # Conta requisições na janela
        request_count = self.redis.zcard(key)
        
        # Verifica limite
        if request_count >= self.config.requests:
            # Calcula tempo até próxima requisição disponível
            oldest = self.redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                reset_time = oldest[0][1] + self.config.window
                retry_after = int(reset_time - now)
            else:
                retry_after = self.config.window
            
            return False, {
                "limit": self.config.requests,
                "remaining": 0,
                "reset": int(now + retry_after),
                "retry_after": retry_after
            }
        
        # Adiciona requisição atual
        self.redis.zadd(key, {str(now): now})
        self.redis.expire(key, self.config.window)
        
        return True, {
            "limit": self.config.requests,
            "remaining": self.config.requests - request_count - 1,
            "reset": int(now + self.config.window)
        }
    
    async def _fixed_window_check(self, key: str) -> tuple[bool, dict]:
        """Implementa fixed window rate limiting"""
        try:
            current = self.redis.incr(key)
            if current == 1:
                self.redis.expire(key, self.config.window)
            
            if current > self.config.requests:
                ttl = self.redis.ttl(key)
                return False, {
                    "limit": self.config.requests,
                    "remaining": 0,
                    "reset": int(time.time() + ttl),
                    "retry_after": ttl
                }
            
            return True, {
                "limit": self.config.requests,
                "remaining": self.config.requests - current,
                "reset": int(time.time() + self.redis.ttl(key))
            }
        except redis.RedisError:
            # Em caso de erro, permite a requisição
            return True, {}

class RateLimitMiddleware:
    """Middleware de rate limiting para FastAPI"""
    
    def __init__(
        self,
        redis_client: redis.Redis,
        default_config: RateLimitConfig,
        custom_limits: dict = None
    ):
        self.redis = redis_client
        self.default_config = default_config
        self.custom_limits = custom_limits or {}
    
    async def __call__(self, request: Request, call_next):
        # Determina configuração para o endpoint
        path = request.url.path
        config = self.custom_limits.get(path, self.default_config)
        
        # Cria rate limiter
        limiter = AdvancedRateLimiter(self.redis, config)
        
        # Verifica limite
        allowed, metadata = await limiter.check_rate_limit(request)
        
        # Adiciona headers de rate limit
        response = await call_next(request) if allowed else None
        
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "RATE_LIMIT_EXCEEDED",
                    "message": "Muitas requisições. Tente novamente mais tarde.",
                    **metadata
                },
                headers={
                    "X-RateLimit-Limit": str(metadata.get("limit", 0)),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(metadata.get("reset", 0)),
                    "Retry-After": str(metadata.get("retry_after", 0))
                }
            )
        
        # Adiciona headers à resposta
        if response:
            response.headers["X-RateLimit-Limit"] = str(metadata.get("limit", 0))
            response.headers["X-RateLimit-Remaining"] = str(metadata.get("remaining", 0))
            response.headers["X-RateLimit-Reset"] = str(metadata.get("reset", 0))
        
        return response