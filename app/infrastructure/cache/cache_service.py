import json
import hashlib
from typing import Optional, Any, Callable
from functools import wraps
import redis
from datetime import timedelta
import pickle

class CacheService:
    """Serviço de cache robusto com Redis"""
    
    def __init__(
        self,
        redis_client: redis.Redis,
        default_ttl: int = 3600,
        prefix: str = "cache"
    ):
        self.redis = redis_client
        self.default_ttl = default_ttl
        self.prefix = prefix
    
    def _make_key(self, key: str) -> str:
        """Gera chave com namespace"""
        return f"{self.prefix}:{key}"
    
    def get(self, key: str) -> Optional[Any]:
        """Recupera valor do cache"""
        full_key = self._make_key(key)
        value = self.redis.get(full_key)
        
        if value:
            try:
                return pickle.loads(value)
            except:
                return json.loads(value)
        return None
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """Armazena valor no cache"""
        full_key = self._make_key(key)
        ttl = ttl or self.default_ttl
        
        try:
            serialized = pickle.dumps(value)
        except:
            serialized = json.dumps(value)
        
        return self.redis.setex(full_key, ttl, serialized)
    
    def delete(self, key: str) -> bool:
        """Remove valor do cache"""
        full_key = self._make_key(key)
        return bool(self.redis.delete(full_key))
    
    def clear_pattern(self, pattern: str) -> int:
        """Limpa cache por padrão"""
        full_pattern = self._make_key(pattern)
        keys = self.redis.keys(full_pattern)
        if keys:
            return self.redis.delete(*keys)
        return 0
    
    def get_or_set(
        self,
        key: str,
        func: Callable,
        ttl: Optional[int] = None
    ) -> Any:
        """Get com fallback para função"""
        value = self.get(key)
        if value is None:
            value = func()
            self.set(key, value, ttl)
        return value

def cache(
    ttl: int = 3600,
    key_prefix: Optional[str] = None,
    key_builder: Optional[Callable] = None
):
    """Decorator para cache automático"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Constrói chave do cache
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Chave automática baseada em função e argumentos
                key_parts = [
                    key_prefix or func.__name__,
                    str(args),
                    str(sorted(kwargs.items()))
                ]
                cache_key = hashlib.md5(
                    ":".join(key_parts).encode()
                ).hexdigest()
            
            # Tenta recuperar do cache
            cache_service = kwargs.get('cache_service')
            if cache_service:
                cached = cache_service.get(cache_key)
                if cached is not None:
                    return cached
            
            # Executa função
            result = await func(*args, **kwargs)
            
            # Armazena no cache
            if cache_service:
                cache_service.set(cache_key, result, ttl)
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Versão síncrona
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                key_parts = [
                    key_prefix or func.__name__,
                    str(args),
                    str(sorted(kwargs.items()))
                ]
                cache_key = hashlib.md5(
                    ":".join(key_parts).encode()
                ).hexdigest()
            
            cache_service = kwargs.get('cache_service')
            if cache_service:
                cached = cache_service.get(cache_key)
                if cached is not None:
                    return cached
            
            result = func(*args, **kwargs)
            
            if cache_service:
                cache_service.set(cache_key, result, ttl)
            
            return result
        
        # Retorna wrapper apropriado
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator