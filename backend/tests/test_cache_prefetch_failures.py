"""Cache degradation must not retry provider failures or erase successful fetches."""

from unittest.mock import AsyncMock

import pytest

from src.database.redis import RedisCache
from src.services.data_manager.cache import CacheOperations


class DedupTransport:
    def __init__(self, behavior):
        self.behavior = behavior

    async def get(self, key):
        return None

    async def set(self, *args):
        return True

    async def get_with_dedup(self, key, fetch, ttl):
        if self.behavior == "before":
            raise ConnectionError("cache offline")
        if self.behavior == "programming":
            raise TypeError("wrong cache contract")
        try:
            result = await fetch()
        except RuntimeError:
            if self.behavior == "swallow":
                return None
            raise
        if self.behavior == "after":
            raise ConnectionError("unlock offline")
        return result


@pytest.mark.asyncio
@pytest.mark.parametrize("behavior", ["raise", "swallow"])
async def test_provider_failure_is_not_fetched_again(behavior):
    fetch = AsyncMock(side_effect=RuntimeError("provider offline"))
    with pytest.raises(RuntimeError, match="provider offline"):
        await CacheOperations(DedupTransport(behavior)).get_with_fetch("key", fetch, 60)
    fetch.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("behavior", ["before", "after"])
async def test_cache_transport_fallback_never_duplicates_a_success(behavior):
    fetch = AsyncMock(return_value={"ok": True})
    result = await CacheOperations(DedupTransport(behavior)).get_with_fetch(
        "key", fetch, 60
    )
    assert result == {"ok": True}
    fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_unconfigured_optional_redis_still_fetches_once():
    fetch = AsyncMock(return_value={"ok": True})
    assert await CacheOperations(RedisCache()).get_with_fetch("key", fetch, 60) == {
        "ok": True
    }
    fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_programming_failure_is_not_classified_as_cache_degradation():
    fetch = AsyncMock(return_value={"ok": True})
    with pytest.raises(TypeError, match="wrong cache contract"):
        await CacheOperations(DedupTransport("programming")).get_with_fetch(
            "key", fetch, 60
        )
    fetch.assert_not_awaited()
