"""PH-002 real Snapshot -> DataManager -> cache/provider contract (not UI wiring)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from src.services.data_manager.manager import DataManager
from src.services.insights.snapshot_service import InsightsSnapshotService


class MemoryRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ttl_seconds):
        self.values[key] = value
        return True


@pytest.mark.asyncio
@pytest.mark.parametrize("news_failed", [False, True])
async def test_real_prefetch_contract_and_partial_provider_failure(news_failed):
    cache = MemoryRedis()
    provider = SimpleNamespace(
        get_treasury_yield=AsyncMock(
            return_value=pd.DataFrame(
                {"value": [4.2]},
                index=[pd.Timestamp("2026-08-05")],
            )
        ),
        get_ipo_calendar=AsyncMock(return_value=pd.DataFrame()),
        get_news_sentiment=AsyncMock(return_value={"feed": []}),
    )
    if news_failed:
        provider.get_news_sentiment.side_effect = RuntimeError("news transport offline")
    manager = DataManager(cache, provider)
    service = InsightsSnapshotService(None, cache, manager, None)
    bars = pd.DataFrame(
        {"Open": [1], "High": [2], "Low": [1], "Close": [2], "Volume": [100]},
        index=[pd.Timestamp("2026-08-05")],
    )
    with (
        patch(
            "src.services.market_data.yfinance_bars.get_bars",
            AsyncMock(return_value=bars),
        ) as market,
        patch(
            "src.core.config.get_settings",
            return_value=SimpleNamespace(fred_api_key=""),
        ),
    ):
        result = await service._prefetch_shared_data()
        assert set(result["ohlcv"]) == {"NVDA", "MSFT", "AMD", "PLTR"}
        assert set(result["treasury"]) == {"2y", "10y"}
        assert market.await_count == 4
        assert {call.args[0] for call in market.await_args_list} == set(result["ohlcv"])
        assert provider.get_treasury_yield.await_count == 2
        assert {
            call.kwargs["maturity"]
            for call in provider.get_treasury_yield.await_args_list
        } == {"2year", "10year"}
        provider.get_ipo_calendar.assert_awaited_once()
        provider.get_news_sentiment.assert_awaited_once()
        if news_failed:
            assert "news transport offline" in result["errors"]["news:technology"]
        else:
            assert result["errors"] == {}
            assert result["news"] == {"technology": []}
        # Real cache serialization prevents a second underlying OHLCV/Treasury fetch.
        await service._prefetch_shared_data()
        assert market.await_count == 4
        assert provider.get_treasury_yield.await_count == 2


@pytest.mark.asyncio
async def test_real_signature_rejects_the_original_wrong_keyword():
    manager = DataManager(MemoryRedis(), object())
    with pytest.raises(TypeError, match="indicators"):
        await manager.prefetch_shared(indicators=["2y"])
