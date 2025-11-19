import json
import hashlib
import asyncio
from typing import Optional, Any, Callable
from functools import wraps
import redis.asyncio as redis
from datetime import timedelta
import pickle

class CacheService:
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
        return f"{self.prefix}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        full_key = self._make_key(key)
        value = await self.redis.get(full_key)

        if value:
            try:
                return pickle.loads(value)
            except:
                return json.loads(value)
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        full_key = self._make_key(key)
        ttl = ttl or self.default_ttl

        try:
            serialized = pickle.dumps(value)
        except:
            serialized = json.dumps(value)

        return await self.redis.setex(full_key, ttl, serialized)

    async def delete(self, key: str) -> bool:
        full_key = self._make_key(key)
        return bool(await self.redis.delete(full_key))

    async def clear_pattern(self, pattern: str) -> int:
        full_pattern = self._make_key(pattern)
        keys = await self.redis.keys(full_pattern)
        if keys:
            return await self.redis.delete(*keys)
        return 0

    async def get_or_set(
        self,
        key: str,
        func: Callable,
        ttl: Optional[int] = None
    ) -> Any:
        value = await self.get(key)
        if value is None:
            if asyncio.iscoroutinefunction(func):
                value = await func()
            else:
                value = func()
            await self.set(key, value, ttl)
        return value

def cache(
    ttl: int = 3600,
    key_prefix: Optional[str] = None,
    key_builder: Optional[Callable] = None
):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
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

            result = await func(*args, **kwargs)

            if cache_service:
                cache_service.set(cache_key, result, ttl)
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
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

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator