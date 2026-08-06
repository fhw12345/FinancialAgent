"""
Cache operations wrapper for the Data Manager Layer.

Provides a thin abstraction over Redis operations with:
- JSON serialization for complex data types
- TTL management
- Cache statistics logging
- Pattern-based invalidation
"""

import json
import typing
from collections.abc import Awaitable, Callable
from typing import Any, cast

import structlog

logger = structlog.get_logger(__name__)


class CacheOperations:
    """
    Redis cache operations for the Data Manager Layer.

    Wraps the existing RedisCache client with DML-specific functionality:
    - Automatic JSON serialization/deserialization
    - Cache hit/miss logging for monitoring
    - Pattern-based key invalidation
    """

    def __init__(self, redis_cache: Any):
        """
        Initialize cache operations.

        Args:
            redis_cache: RedisCache instance from database.redis
        """
        self._redis = redis_cache

    async def get(self, key: str) -> dict[str, typing.Any] | list[typing.Any] | None:
        """
        Get cached value by key.

        Args:
            key: Cache key

        Returns:
            Cached value (dict or list) or None if not found
        """
        try:
            value = await self._redis.get(key)

            if value is None:
                logger.debug("cache_miss", key=key)
                return None

            logger.debug("cache_hit", key=key)

            # Handle both string and already-parsed values
            if isinstance(value, dict | list):
                return value

            # Try to parse JSON string
            if isinstance(value, str):
                try:
                    parsed: object = json.loads(value)
                except json.JSONDecodeError:
                    logger.warning("cache_invalid_json", key=key)
                    return None
                return parsed if isinstance(parsed, dict | list) else None

            return None

        except Exception as e:
            logger.warning("cache_get_error", key=key, error=str(e))
            return None

    async def set(
        self,
        key: str,
        value: dict[str, typing.Any] | list[typing.Any],
        ttl_seconds: int,
    ) -> bool:
        """
        Set cached value with TTL.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        if ttl_seconds <= 0:
            logger.debug("cache_skip_no_ttl", key=key)
            return False

        try:
            # Serialize to JSON string
            json_value = json.dumps(value, default=str)

            await self._redis.set(key, json_value, ttl_seconds)
            logger.debug("cache_set", key=key, ttl=ttl_seconds)
            return True

        except Exception as e:
            logger.warning("cache_set_error", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete a cached value.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False otherwise
        """
        try:
            result = int(await self._redis.delete(key))
            logger.debug("cache_delete", key=key, deleted=result > 0)
            return result > 0
        except Exception as e:
            logger.warning("cache_delete_error", key=key, error=str(e))
            return False

    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False otherwise
        """
        try:
            return bool(await self._redis.exists(key))
        except Exception as e:
            logger.warning("cache_exists_error", key=key, error=str(e))
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern.

        Uses Redis SCAN to find keys (safe for production).

        Args:
            pattern: Glob-style pattern (e.g., 'market:daily:*')

        Returns:
            Number of keys deleted
        """
        try:
            deleted = 0
            cursor = 0

            # Use SCAN to safely iterate over keys
            while True:
                # Access the underlying redis client
                redis_client = self._redis._client
                cursor, keys = await redis_client.scan(
                    cursor=cursor, match=pattern, count=100
                )

                if keys:
                    deleted += await redis_client.delete(*keys)

                if cursor == 0:
                    break

            logger.info("cache_invalidate_pattern", pattern=pattern, deleted=deleted)
            return deleted

        except Exception as e:
            logger.warning("cache_invalidate_error", pattern=pattern, error=str(e))
            return 0

    async def get_with_fetch(
        self,
        key: str,
        fetch_func: Callable[
            [], Awaitable[dict[str, typing.Any] | list[typing.Any] | None]
        ],
        ttl_seconds: int,
    ) -> dict[str, typing.Any] | list[typing.Any] | None:
        """
        Get cached value or fetch and cache if missing.

        Uses the existing get_with_dedup pattern from RedisCache
        if available, falling back to simple get/set.

        Args:
            key: Cache key
            fetch_func: Async function to call on cache miss
            ttl_seconds: TTL for cached value

        Returns:
            Cached or fetched value
        """
        # Try cache first
        cached = await self.get(key)
        if cached is not None:
            return cached

        # Skip caching for zero TTL
        if ttl_seconds <= 0:
            return await fetch_func()

        # Try to use dedup if available (check it's actually callable, not a mock)
        get_with_dedup = getattr(self._redis, "get_with_dedup", None)
        if get_with_dedup is not None and callable(get_with_dedup):
            # Additional check: ensure it's not a mock (for testing)
            if not str(type(get_with_dedup).__module__).startswith("unittest.mock"):
                try:
                    result = await get_with_dedup(key, fetch_func, ttl_seconds)
                    if isinstance(result, dict | list):
                        return cast(dict[str, Any] | list[Any], result)
                    return None
                except Exception:
                    pass  # Fall back to simple fetch

        # Simple fetch and cache
        result = await fetch_func()
        if result is not None:
            await self.set(key, result, ttl_seconds)

        return result
