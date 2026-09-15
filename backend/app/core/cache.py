import json
import pickle
import hashlib
from typing import Any, Optional, Callable
from functools import wraps
import redis.asyncio as redis
from redis.asyncio import Redis

from app.config import settings

# Redis connection settings
REDIS_HOST = settings.redis_host
REDIS_PORT = settings.redis_port
REDIS_DB = settings.redis_db
REDIS_PASSWORD = settings.redis_password

# Default TTL values (in seconds)
DEFAULT_TTL = 300  # 5 minutes
AGENT_RESULT_TTL = 300  # 5 minutes
USER_PROFILE_TTL = 3600  # 1 hour
RAG_RESULT_TTL = 600  # 10 minutes

class CacheManager:
    """Redis cache manager with async support."""

    def __init__(self):
        self._redis: Optional[redis.Redis] = None

    async def connect(self) -> redis.Redis:
        """Connect to Redis server."""
        if self._redis is None:
            self._redis = await redis.from_url(
                f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
                password=REDIS_PASSWORD,
                decode_responses=False  # We'll handle decoding manually
            )
        return self._redis

    async def disconnect(self):
        """Disconnect from Redis server."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        r = await self.connect()
        data = await r.get(key)
        if data is None:
            return None
        try:
            return pickle.loads(data)
        except Exception:
            # Fallback to JSON for backward compatibility
            try:
                return json.loads(data.decode('utf-8'))
            except Exception:
                return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = DEFAULT_TTL
    ) -> bool:
        """Set value in cache with TTL."""
        r = await self.connect()
        try:
            data = pickle.dumps(value)
            return await r.setex(key, ttl, data)
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        r = await self.connect()
        return await r.delete(key) > 0

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        r = await self.connect()
        return await r.exists(key) > 0

    async def clear_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        r = await self.connect()
        keys = await r.keys(pattern)
        if keys:
            return await r.delete(*keys)
        return 0


# Global cache manager instance
cache_manager = CacheManager()

def cached(
    ttl: int = DEFAULT_TTL,
    key_prefix: str = "",
    key_builder: Optional[Callable[..., str]] = None
):
    """
    Decorator to cache function results.

    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache key
        key_builder: Custom function to build cache key
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            # Build cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Default key: prefix:function_name:arg_hash
                arg_payload = {
                    "args": args[1:],
                    "kwargs": kwargs,
                }
                arg_str = json.dumps(arg_payload, ensure_ascii=False, sort_keys=True, default=str)
                arg_hash = hashlib.sha256(arg_str.encode("utf-8")).hexdigest()[:16]
                cache_key = f"{key_prefix}:{func.__name__}:{arg_hash}"

            # Try to get from cache
            try:
                cached_result = await cache_manager.get(cache_key)
                if cached_result is not None:
                    return cached_result
            except Exception:
                pass  # Cache miss or error, continue to function

            # Call function
            result = await func(*args, **kwargs)

            # Store in cache
            try:
                await cache_manager.set(cache_key, result, ttl)
            except Exception:
                pass  # Cache error, ignore

            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            # For sync functions, just call directly (no caching)
            return func(*args, **kwargs)

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Convenience decorators for common TTL values
def cached_agent_result(ttl: int = AGENT_RESULT_TTL):
    """Cache agent results (5 minutes)."""
    return cached(ttl=ttl, key_prefix="agent")


def cached_user_profile(ttl: int = USER_PROFILE_TTL):
    """Cache user profiles (1 hour)."""
    return cached(ttl=ttl, key_prefix="user:profile")


def cached_rag_result(ttl: int = RAG_RESULT_TTL):
    """Cache RAG retrieval results (10 minutes)."""
    return cached(ttl=ttl, key_prefix="rag")
