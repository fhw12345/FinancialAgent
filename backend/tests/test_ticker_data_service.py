"""Tests for cached local ticker prices."""

from unittest.mock import AsyncMock

import pytest

from src.core.data.ticker_data_service import TickerDataService


@pytest.mark.asyncio
async def test_current_price_uses_cache():
    redis = AsyncMock()
    redis.get.return_value = 123.45
    market = AsyncMock()
    service = TickerDataService(redis, market)

    assert await service.get_current_price("aapl") == 123.45
    market.get_quote.assert_not_awaited()


@pytest.mark.asyncio
async def test_current_price_fetches_and_caches():
    redis = AsyncMock()
    redis.get.return_value = None
    market = AsyncMock()
    market.get_quote.return_value = {"price": 210.5}
    service = TickerDataService(redis, market)

    assert await service.get_current_price("aapl") == 210.5
    market.get_quote.assert_awaited_once_with("AAPL")
    redis.set.assert_awaited_once_with(
        "current_price:AAPL",
        210.5,
        ttl_seconds=30,
    )


@pytest.mark.asyncio
async def test_current_price_returns_none_for_invalid_quote():
    redis = AsyncMock()
    redis.get.return_value = None
    market = AsyncMock()
    market.get_quote.return_value = {"price": 0}
    service = TickerDataService(redis, market)

    assert await service.get_current_price("AAPL") is None
