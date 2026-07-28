"""Regression tests for explicit market-data date range contracts."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.api.analysis.shared import validate_date_range as validate_analysis_range
from src.core.analysis.fibonacci.analyzer import FibonacciAnalyzer
from src.core.analysis.stochastic_analyzer import StochasticAnalyzer
from src.core.utils.market_calendar import market_timezone, market_today
from src.services.data_manager.keys import CacheKeys
from src.services.data_manager.manager import DataManager
from src.services.data_manager.types import Granularity, OHLCVData
from src.services.market_data.bars_extended import BarsExtendedMixin
from src.services.market_data.yfinance_bars import _fetch_sync


def test_market_cache_keys_isolate_output_size_and_range() -> None:
    compact = CacheKeys.market("daily", "AAPL", outputsize="compact")
    full = CacheKeys.market("daily", "AAPL", outputsize="full")
    june = CacheKeys.market(
        "daily",
        "AAPL",
        outputsize="full",
        start_date="2026-06-01",
        end_date="2026-06-30",
    )

    assert compact != full
    assert full != june
    assert june.endswith(":full:2026-06-01:2026-06-30")


def test_market_calendar_uses_symbol_exchange_timezone() -> None:
    now = datetime(2026, 7, 29, 1, tzinfo=UTC)

    assert market_timezone("0700.HK") == "Asia/Hong_Kong"
    assert market_today("0700.HK", now).isoformat() == "2026-07-29"
    assert market_today("AAPL", now).isoformat() == "2026-07-28"


def test_analysis_range_rejects_one_sided_dates() -> None:
    with pytest.raises(ValueError, match="required together"):
        validate_analysis_range("2026-06-01", None, "AAPL")


@pytest.mark.asyncio
async def test_data_manager_normalizes_monthly_alias_and_range() -> None:
    manager = DataManager.__new__(DataManager)

    async def get_with_fetch(key, fetch, ttl):
        return await fetch()

    manager._cache = SimpleNamespace(
        get_with_fetch=AsyncMock(side_effect=get_with_fetch)
    )
    manager._fetch_ohlcv = AsyncMock(return_value=[])

    await manager.get_ohlcv(
        "AAPL",
        "1mo",
        outputsize="full",
        start_date="2021-01-01",
        end_date="2026-01-01",
    )

    manager._fetch_ohlcv.assert_awaited_once_with(
        "AAPL",
        Granularity.MONTHLY,
        "full",
        "2021-01-01",
        "2026-01-01",
    )
    cache_key = manager._cache.get_with_fetch.await_args.args[0]
    assert cache_key == "market:monthly:AAPL:full:2021-01-01:2026-01-01"


@pytest.mark.asyncio
async def test_market_invalidation_clears_legacy_and_suffixed_keys() -> None:
    manager = DataManager.__new__(DataManager)
    manager._cache = SimpleNamespace(
        delete=AsyncMock(return_value=True),
        invalidate_pattern=AsyncMock(return_value=2),
    )

    deleted = await manager.invalidate_market("AAPL", "daily")

    assert deleted == 3
    manager._cache.delete.assert_awaited_once_with("market:daily:AAPL")
    manager._cache.invalidate_pattern.assert_awaited_once_with("market:daily:AAPL:*")


@pytest.mark.asyncio
async def test_symbol_invalidation_clears_all_range_variants() -> None:
    manager = DataManager.__new__(DataManager)
    manager._cache = SimpleNamespace(invalidate_pattern=AsyncMock(side_effect=[1, 2]))

    deleted = await manager.invalidate_market("AAPL")

    assert deleted == 3
    assert manager._cache.invalidate_pattern.await_args_list[0].args == (
        "market:*:AAPL",
    )
    assert manager._cache.invalidate_pattern.await_args_list[1].args == (
        "market:*:AAPL:*",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("analyzer_type", "timeframe"),
    [(FibonacciAnalyzer, "1mo"), (StochasticAnalyzer, "1mo")],
)
async def test_analyzers_request_full_monthly_range(analyzer_type, timeframe) -> None:
    data_manager = SimpleNamespace(get_ohlcv=AsyncMock(return_value=[]))
    analyzer = analyzer_type(data_manager)
    analyzer.symbol = "AAPL"
    analyzer.timeframe = timeframe

    result = await analyzer._fetch_stock_data("2021-01-01", "2026-01-01")

    assert result.empty
    data_manager.get_ohlcv.assert_awaited_once_with(
        symbol="AAPL",
        granularity="monthly",
        outputsize="full",
        start_date="2021-01-01",
        end_date="2026-01-01",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("analyzer_type", [FibonacciAnalyzer, StochasticAnalyzer])
async def test_analyzers_include_bars_on_the_end_date(analyzer_type) -> None:
    data_manager = SimpleNamespace(
        get_ohlcv=AsyncMock(
            return_value=[
                OHLCVData(
                    date=datetime(2026, 6, 30, 4, tzinfo=UTC),
                    open=100,
                    high=101,
                    low=99,
                    close=100,
                    volume=1,
                )
            ]
        )
    )
    analyzer = analyzer_type(data_manager)
    analyzer.symbol = "AAPL"
    analyzer.timeframe = "1d"

    result = await analyzer._fetch_stock_data("2026-06-01", "2026-06-30")

    assert len(result) == 1


def test_explicit_daily_range_bypasses_default_two_year_cap() -> None:
    mixin = BarsExtendedMixin.__new__(BarsExtendedMixin)
    frame = pd.DataFrame(
        {"Open": [100, 200], "High": [101, 201], "Low": [99, 199], "Close": [100, 200]},
        index=pd.to_datetime(["2021-06-01", "2026-06-01"]),
    )

    result = mixin._postprocess_price_bars(
        frame,
        "AAPL",
        "1d",
        "2021-01-01",
        "2026-06-30",
    )

    assert list(result.index) == list(frame.index)


def test_empty_explicit_intraday_range_does_not_return_recent_bars() -> None:
    mixin = BarsExtendedMixin.__new__(BarsExtendedMixin)
    frame = pd.DataFrame(
        {"Open": [100], "High": [101], "Low": [99], "Close": [100]},
        index=pd.to_datetime(["2026-07-28T10:00:00"]),
    )

    result = mixin._postprocess_price_bars(
        frame,
        "AAPL",
        "1m",
        "2026-06-01",
        "2026-06-02",
    )

    assert result.empty


def test_explicit_range_uses_exchange_local_calendar_dates() -> None:
    mixin = BarsExtendedMixin.__new__(BarsExtendedMixin)
    frame = pd.DataFrame(
        {"Open": [100, 101], "High": [101, 102], "Low": [99, 100], "Close": [100, 101]},
        index=pd.DatetimeIndex(
            ["2026-06-01T00:00:00+08:00", "2026-06-02T00:00:00+08:00"]
        ),
    )

    result = mixin._postprocess_price_bars(
        frame,
        "0700.HK",
        "1d",
        "2026-06-01",
        "2026-06-02",
    )

    assert len(result) == 2


def test_yfinance_one_minute_range_is_fetched_in_seven_day_chunks() -> None:
    ticker = MagicMock()
    ticker.history.side_effect = [
        pd.DataFrame(
            {"Open": [100], "High": [101], "Low": [99], "Close": [100], "Volume": [1]},
            index=pd.DatetimeIndex([datetime(2026, 6, 1, tzinfo=UTC)]),
        ),
        pd.DataFrame(
            {"Open": [101], "High": [102], "Low": [100], "Close": [101], "Volume": [2]},
            index=pd.DatetimeIndex([datetime(2026, 6, 8, tzinfo=UTC)]),
        ),
        pd.DataFrame(
            {"Open": [102], "High": [103], "Low": [101], "Close": [102], "Volume": [3]},
            index=pd.DatetimeIndex([datetime(2026, 6, 15, tzinfo=UTC)]),
        ),
    ]

    with patch(
        "src.services.market_data.yfinance_bars.yf.Ticker",
        return_value=ticker,
    ):
        result = _fetch_sync(
            "AAPL",
            "1min",
            "full",
            start_date="2026-06-01",
            end_date="2026-06-20",
        )

    assert len(result) == 3
    assert ticker.history.call_count == 3
    assert ticker.history.call_args_list[0].kwargs["start"] == "2026-06-01"
    assert ticker.history.call_args_list[-1].kwargs["end"] == "2026-06-21"
