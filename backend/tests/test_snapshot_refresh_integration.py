"""Real snapshot/category/DataManager composition; fake only external transports."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import Settings
from src.database.redis import RedisCache
from src.services.data_manager import DataManager
from src.services.insights.categories.ai_sector_risk import AISectorRiskCategory
from src.services.insights.models import InsightCategory
from src.services.insights.registry import InsightsCategoryRegistry
from src.services.insights.snapshot_inputs import PreparedAICategory
from src.services.insights.snapshot_service import InsightsSnapshotService
from tests.e2e.insights_provider_fixture import (
    SYMBOLS,
    RecordedFred,
    RecordedMarket,
    seed_pcr,
)


class MemoryCache:
    # Real Redis dedup orchestration with only storage/lock transports faked.
    get_with_dedup = RedisCache.get_with_dedup

    async def acquire_lock(self, *args):
        return True

    async def release_lock(self, *args):
        return True

    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ttl_seconds):
        self.values[key] = value
        return True


@pytest.mark.asyncio
@pytest.mark.parametrize("news_failed", [False, True])
@pytest.mark.parametrize("storage_failed", [False, True])
async def test_snapshot_consumes_prefetch_and_persists_partial_failures(
    news_failed, storage_failed
):
    cache = MemoryCache()
    await seed_pcr(cache)
    market = RecordedMarket()
    market.fail_news = news_failed
    settings = Settings(_env_file=None, environment="test", fred_api_key="")
    registry = InsightsCategoryRegistry(settings, cache, market, RecordedFred())
    manager = DataManager(cache, market)
    collection = SimpleNamespace(
        update_one=AsyncMock(
            side_effect=RuntimeError("storage offline") if storage_failed else None,
        )
    )
    mongo = SimpleNamespace(get_collection=lambda _: collection)
    service = InsightsSnapshotService(mongo, cache, manager, settings, registry)
    original = registry.get_category_instance("ai_sector_risk")
    with patch("src.services.market_data.yfinance_bars.get_bars", market.bars):
        with patch("src.core.config.get_settings", return_value=settings):
            result = await service.create_snapshot()
    if storage_failed:
        assert result["status"] == "error"
        assert "storage offline" in result["error"]
        return
    assert result["status"] == "success"
    assert original.market_service is market
    assert market.calls["basket"] == 1
    assert all(market.calls[f"ohlcv:{symbol}"] == 1 for symbol in SYMBOLS)
    assert market.outputs == ["full"] * 4
    assert market.calls["treasury:2year"] == market.calls["treasury:10year"] == 1
    assert market.calls["news"] == market.calls["ipo"] == 1
    data = InsightCategory.model_validate(cache.values["insights:ai_sector_risk:full"])
    metrics = {metric.id: metric for metric in data.metrics}
    assert not metrics["ai_price_anomaly"].raw_data.get("placeholder")
    assert metrics["fed_expectations"].raw_data["yield_2y_current"] == 4.26
    assert metrics["ipo_heat"].raw_data["ipo_count_90d"] == 1
    assert len(data.metrics) == result["metric_count"] == 7
    persisted = collection.update_one.call_args.args[1]["$set"]
    assert persisted["prefetch_errors"] == result["prefetch_errors"]
    assert persisted["composite_score"] == data.composite.score
    if news_failed:
        assert (
            result["prefetch_errors"]["news:technology"] == "Provider data unavailable"
        )
        assert "fixture news unavailable" not in str(persisted)
        assert "fixture news unavailable" not in str(metrics["news_sentiment"].raw_data)
        assert metrics["news_sentiment"].raw_data["placeholder"]
    else:
        assert result["prefetch_errors"] == {}
        assert metrics["news_sentiment"].score == 70


@pytest.mark.asyncio
async def test_request_local_provider_views_do_not_cross_contaminate():
    from datetime import UTC, datetime

    from src.services.data_manager.types import NewsData

    source = RecordedMarket()
    original = AISectorRiskCategory(Settings(_env_file=None), market_service=source)

    def prepared(score):
        data = {
            "errors": {},
            "news": {"technology": [NewsData(datetime.now(UTC), score, 1.0)]},
        }
        return PreparedAICategory(original, data, (SYMBOLS, "fixture"))

    positive, negative = await asyncio.gather(
        prepared(0.14)._calculate_news_sentiment(),
        prepared(-0.14)._calculate_news_sentiment(),
    )
    assert (positive.score, negative.score) == (70, 30)
    assert original.market_service is source
    assert source.calls["news"] == 0
