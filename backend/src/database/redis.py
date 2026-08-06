"""
Redis cache connection and operations.
Following Factor 3: External Dependencies as Services.
"""

import json
import typing
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as redis
import structlog

logger = structlog.get_logger()


class RedisCache:
    """Redis connection manager with async support."""

    def __init__(self) -> None:
        self.client: redis.Redis | None = None

    async def connect(self, redis_url: str) -> None:
        """Establish connection to Redis."""
        try:
            self.client = redis.from_url(redis_url, decode_responses=True)

            # Test connection
            await self.client.ping()

            logger.info("Redis connection established", url=redis_url)

        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self.client:
            await self.client.close()
            logger.info("Redis connection closed")

    async def health_check(self) -> dict[str, bool | str]:
        """Check Redis connection health."""
        try:
            if not self.client:
                return {"connected": False, "error": "No client connection"}

            # Ping Redis
            await self.client.ping()

            # Get server info
            info = await self.client.info()

            return {
                "connected": True,
                "version": info.get("redis_version", "unknown"),
                "memory_usage": info.get("used_memory_human", "unknown"),
            }

        except Exception as e:
            logger.error("Redis health check failed", error=str(e))
            return {"connected": False, "error": str(e)}

    async def get_cache_stats(self) -> dict[str, typing.Any]:
        """
        Get comprehensive Redis cache statistics for monitoring.

        Returns memory usage, hit/miss ratio, key count, and other metrics
        useful for cache optimization decisions.

        Returns:
            dict with cache statistics
        """
        if not self.client:
            raise RuntimeError("Redis connection not established")

        try:
            # Get server info
            info = await self.client.info()

            # Get key count
            db_info = info.get("db0", {})
            if isinstance(db_info, str):
                # Parse "keys=N,expires=M" format
                parts = dict(item.split("=") for item in db_info.split(","))
                key_count = int(parts.get("keys", 0))
                expires_count = int(parts.get("expires", 0))
            else:
                key_count = db_info.get("keys", 0)
                expires_count = db_info.get("expires", 0)

            # Calculate hit ratio
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total_requests = hits + misses
            hit_ratio = (hits / total_requests * 100) if total_requests > 0 else 0

            return {
                "connected": True,
                "version": info.get("redis_version", "unknown"),
                # Memory metrics
                "memory": {
                    "used_human": info.get("used_memory_human", "unknown"),
                    "used_bytes": info.get("used_memory", 0),
                    "peak_human": info.get("used_memory_peak_human", "unknown"),
                    "peak_bytes": info.get("used_memory_peak", 0),
                    "fragmentation_ratio": info.get("mem_fragmentation_ratio", 0),
                },
                # Key metrics
                "keys": {
                    "total": key_count,
                    "with_expiry": expires_count,
                    "expired_keys": info.get("expired_keys", 0),
                    "evicted_keys": info.get("evicted_keys", 0),
                },
                # Cache efficiency
                "cache_efficiency": {
                    "hits": hits,
                    "misses": misses,
                    "hit_ratio_percent": round(hit_ratio, 2),
                    "total_requests": total_requests,
                },
                # Connection info
                "connections": {
                    "connected_clients": info.get("connected_clients", 0),
                    "blocked_clients": info.get("blocked_clients", 0),
                },
                # Performance
                "performance": {
                    "instantaneous_ops_per_sec": info.get(
                        "instantaneous_ops_per_sec", 0
                    ),
                    "total_commands_processed": info.get("total_commands_processed", 0),
                },
            }

        except Exception as e:
            logger.error("Failed to get cache stats", error=str(e))
            return {"connected": False, "error": str(e)}

    async def get(self, key: str) -> Any | None:
        """Get value from Redis cache.

        Logs cache hit/miss for monitoring cache efficiency.
        Hit/miss ratio is a key metric for cache optimization.
        """
        if not self.client:
            raise RuntimeError("Redis connection not established")

        try:
            value = await self.client.get(key)
            if value:
                # Cache HIT - log for monitoring
                logger.debug("Cache HIT", cache_key=key)
                # Try JSON decode, fallback to plain string
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value  # Return as plain string
            else:
                # Cache MISS - log for monitoring
                logger.debug("Cache MISS", cache_key=key)
            return None
        except Exception as e:
            logger.error("Redis get operation failed", key=key, error=str(e))
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Set value in Redis cache with optional TTL."""
        if not self.client:
            raise RuntimeError("Redis connection not established")

        try:
            json_value = json.dumps(value, default=str)
            await self.client.set(key, json_value, ex=ttl_seconds)
            return True
        except Exception as e:
            logger.error("Redis set operation failed", key=key, error=str(e))
            return False

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """
        Set key with TTL (Redis SETEX command).
        For simple string values without JSON encoding.
        """
        if not self.client:
            raise RuntimeError("Redis connection not established")

        try:
            await self.client.setex(key, ttl_seconds, value)
            return True
        except Exception as e:
            logger.error("Redis setex operation failed", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from Redis cache."""
        if not self.client:
            raise RuntimeError("Redis connection not established")

        try:
            result: int = await self.client.delete(key)
            return result > 0
        except Exception as e:
            logger.error("Redis delete operation failed", key=key, error=str(e))
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis cache."""
        if not self.client:
            raise RuntimeError("Redis connection not established")

        try:
            result: int = await self.client.exists(key)
            return result > 0
        except Exception as e:
            logger.error("Redis exists operation failed", key=key, error=str(e))
            return False

    # =========================================================================
    # Request Deduplication (Thundering Herd Prevention)
    # =========================================================================

    async def acquire_lock(
        self,
        lock_key: str,
        lock_ttl_seconds: int = 30,
    ) -> bool:
        """
        Acquire a distributed lock using Redis SET NX EX pattern.

        Used to prevent multiple concurrent requests from fetching the same
        data when cache expires (thundering herd problem).

        Args:
            lock_key: Unique key for the lock
            lock_ttl_seconds: Lock expiry time (prevents deadlocks)

        Returns:
            True if lock acquired, False if already held by another process
        """
        if not self.client:
            raise RuntimeError("Redis connection not established")

        try:
            # SET key value NX EX seconds - atomic operation
            # NX = only set if not exists, EX = expiry in seconds
            result = await self.client.set(
                lock_key,
                "locked",
                nx=True,  # Only set if not exists
                ex=lock_ttl_seconds,  # Auto-expire to prevent deadlocks
            )
            acquired = result is True
            if acquired:
                logger.debug("Lock acquired", lock_key=lock_key, ttl=lock_ttl_seconds)
            return acquired
        except Exception as e:
            logger.error("Failed to acquire lock", lock_key=lock_key, error=str(e))
            return False

    async def release_lock(self, lock_key: str) -> bool:
        """
        Release a distributed lock.

        Args:
            lock_key: The lock key to release

        Returns:
            True if lock released, False otherwise
        """
        if not self.client:
            raise RuntimeError("Redis connection not established")

        try:
            result = await self.client.delete(lock_key)
            released = result > 0
            if released:
                logger.debug("Lock released", lock_key=lock_key)
            return released
        except Exception as e:
            logger.error("Failed to release lock", lock_key=lock_key, error=str(e))
            return False

    async def get_with_dedup(
        self,
        cache_key: str,
        fetch_func: Callable[[], Awaitable[Any]],
        ttl_seconds: int = 3600,
        lock_ttl_seconds: int = 30,
        wait_timeout_seconds: float = 5.0,
        wait_interval_seconds: float = 0.1,
    ) -> Any | None:
        """
        Get value from cache with request deduplication.

        If cache miss, acquires lock and fetches data. Other concurrent
        requests wait for the first request to populate the cache.

        Args:
            cache_key: Cache key to get/set
            fetch_func: Async function to call on cache miss (returns data)
            ttl_seconds: Cache TTL for the fetched data
            lock_ttl_seconds: Lock TTL (prevents deadlocks)
            wait_timeout_seconds: How long waiting requests will poll
            wait_interval_seconds: Polling interval for waiting requests

        Returns:
            Cached or freshly fetched data, or None on error
        """
        import asyncio

        # 1. Try cache first
        cached = await self.get(cache_key)
        if cached is not None:
            return cached

        # 2. Cache miss - try to acquire lock
        lock_key = f"lock:{cache_key}"
        if await self.acquire_lock(lock_key, lock_ttl_seconds):
            try:
                # Double-check cache (another request may have populated it)
                cached = await self.get(cache_key)
                if cached is not None:
                    return cached

                # 3. We have the lock - fetch fresh data
                logger.info(
                    "Cache miss with lock - fetching data",
                    cache_key=cache_key,
                )
                data = await fetch_func()

                if data is not None:
                    await self.set(cache_key, data, ttl_seconds=ttl_seconds)
                    logger.info(
                        "Cache populated after fetch",
                        cache_key=cache_key,
                        ttl=ttl_seconds,
                    )

                return data

            finally:
                # Always release lock
                await self.release_lock(lock_key)
        else:
            # 4. Another request has the lock - wait for cache to be populated
            logger.debug(
                "Waiting for cache population",
                cache_key=cache_key,
                timeout=wait_timeout_seconds,
            )

            elapsed = 0.0
            while elapsed < wait_timeout_seconds:
                await asyncio.sleep(wait_interval_seconds)
                elapsed += wait_interval_seconds

                cached = await self.get(cache_key)
                if cached is not None:
                    logger.debug(
                        "Cache populated by another request",
                        cache_key=cache_key,
                        wait_time=elapsed,
                    )
                    return cached

            # 5. Timeout - fetch ourselves (rare fallback)
            logger.warning(
                "Wait timeout - fetching data directly",
                cache_key=cache_key,
                timeout=wait_timeout_seconds,
            )
            try:
                data = await fetch_func()
                if data is not None:
                    await self.set(cache_key, data, ttl_seconds=ttl_seconds)
                return data
            except Exception as e:
                logger.error(
                    "Fallback fetch failed",
                    cache_key=cache_key,
                    error=str(e),
                )
                return None
