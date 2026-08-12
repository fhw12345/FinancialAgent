"""Provider-boundary composition tests for DataManager normalization.

The DataManager parsing/fallback code is real; only external provider responses
are deterministic fakes. Tests cover malformed rows, timezone normalization,
empty capabilities, and provider failures.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from src.services.data_manager.manager import DataManager
from src.services.data_manager.types import DataFetchError, OHLCVData


class _Redis:
    pass


class _Av:
    def __init__(self) -> None:
        self.get_treasury_yield = AsyncMock()
        self.get_ipo_calendar = AsyncMock()
        self.get_news_sentiment = AsyncMock()
        self.get_insider_transactions = AsyncMock()


def _manager(av: object) -> DataManager:
    return DataManager(_Redis(), av)


@pytest.mark.asyncio
async def test_treasury_falls_back_to_av_and_normalizes_dates() -> None:
    av = _Av()
    av.get_treasury_yield.return_value = pd.DataFrame(
        {"value": [4.25, 4.1]},
        index=[pd.Timestamp("2026-08-05"), pd.Timestamp("2026-08-04")],
    )
    manager = _manager(av)

    with patch(
        "src.core.config.get_settings",
        return_value=SimpleNamespace(fred_api_key=""),
    ):
        rows = await manager._fetch_treasury("10y", "daily")

    assert [row.yield_value for row in rows] == [4.25, 4.1]
    assert all(row.date.tzinfo is not None for row in rows)
    av.get_treasury_yield.assert_awaited_once_with(maturity="10year", interval="daily")


@pytest.mark.asyncio
async def test_treasury_empty_and_provider_error_have_distinct_contracts() -> None:
    av = _Av()
    manager = _manager(av)
    av.get_treasury_yield.return_value = pd.DataFrame()
    assert await manager._fetch_treasury("2y", "daily") == []

    av.get_treasury_yield.side_effect = RuntimeError("provider down")
    with pytest.raises(DataFetchError, match="provider down"):
        await manager._fetch_treasury("2y", "daily")


@pytest.mark.asyncio
async def test_ipo_parser_keeps_valid_rows_and_skips_malformed_dates() -> None:
    av = _Av()
    av.get_ipo_calendar.return_value = pd.DataFrame(
        [
            {
                "ipoDate": "2026-09-01",
                "name": "Example Corp",
                "exchange": "NASDAQ",
                "priceRangeLow": "10",
                "priceRangeHigh": "12",
                "shares": 1_000_000,
            },
            {"ipoDate": "not-a-date", "name": "Bad Date"},
            {"ipoDate": "", "name": "Missing Date"},
        ]
    )
    rows = await _manager(av)._fetch_ipo_calendar()

    assert len(rows) == 1
    assert rows[0].name == "Example Corp"
    assert rows[0].price_range_low == 10
    assert rows[0].date.tzinfo is not None


@pytest.mark.asyncio
async def test_ipo_capability_and_provider_failure_are_explicit() -> None:
    assert await _manager(object())._fetch_ipo_calendar() == []
    av = _Av()
    av.get_ipo_calendar.side_effect = RuntimeError("ipo unavailable")
    with pytest.raises(DataFetchError, match="ipo unavailable"):
        await _manager(av)._fetch_ipo_calendar()


@pytest.mark.asyncio
async def test_news_parser_normalizes_relevance_and_skips_bad_items() -> None:
    av = _Av()
    av.get_news_sentiment.return_value = {
        "feed": [
            {
                "time_published": "20260805T120000",
                "overall_sentiment_score": "0.6",
                "ticker_sentiment": [
                    {"relevance_score": "0.8"},
                    {"relevance_score": "0.4"},
                ],
                "title": "Earnings beat",
                "source": "Fixture Wire",
            },
            {"time_published": "invalid", "title": "Bad row"},
        ]
    }
    rows = await _manager(av)._fetch_news_sentiment("earnings", ["AAPL"])

    assert len(rows) == 1
    assert rows[0].sentiment_score == 0.6
    assert rows[0].ticker_relevance == pytest.approx(0.6)
    assert rows[0].title == "Earnings beat"
    av.get_news_sentiment.assert_awaited_once_with(tickers="AAPL", topics="earnings")


@pytest.mark.asyncio
async def test_news_empty_capability_and_failure_paths() -> None:
    assert await _manager(object())._fetch_news_sentiment(None, None) == []
    av = _Av()
    av.get_news_sentiment.return_value = {"items": []}
    assert await _manager(av)._fetch_news_sentiment(None, None) == []
    av.get_news_sentiment.side_effect = RuntimeError("news unavailable")
    with pytest.raises(DataFetchError, match="news unavailable"):
        await _manager(av)._fetch_news_sentiment(None, None)


@pytest.mark.asyncio
async def test_yfinance_company_news_normalizes_missing_and_invalid_timestamps() -> (
    None
):
    ticker = SimpleNamespace(
        news=[
            {
                "providerPublishTime": 1_786_000_000,
                "title": "Timestamped",
                "publisher": "Yahoo",
            },
            {
                "providerPublishTime": "bad",
                "title": "Fallback timestamp",
            },
        ]
    )
    with patch("yfinance.Ticker", return_value=ticker):
        rows = await DataManager._fetch_company_news_yfinance("AAPL")

    assert [row.title for row in rows] == ["Timestamped", "Fallback timestamp"]
    assert all(row.date.tzinfo is not None for row in rows)


@pytest.mark.asyncio
async def test_insider_provider_shapes_and_yfinance_fallback() -> None:
    av = _Av()
    av.get_insider_transactions.return_value = {
        "data": [{"symbol": "AAPL", "shares": 100}]
    }
    manager = _manager(av)
    rows = await manager._fetch_insider_trades("AAPL")
    assert rows == [{"symbol": "AAPL", "shares": 100}]

    av.get_insider_transactions.side_effect = RuntimeError("premium unavailable")
    frame = pd.DataFrame([{"Insider": "A", "Shares": 10}])
    with patch(
        "yfinance.Ticker", return_value=SimpleNamespace(insider_transactions=frame)
    ):
        fallback = await manager._fetch_insider_trades("AAPL")
    assert fallback[0]["Shares"] == 10


@pytest.mark.asyncio
async def test_insider_all_providers_failed_is_typed() -> None:
    av = _Av()
    av.get_insider_transactions.side_effect = RuntimeError("premium unavailable")
    manager = _manager(av)
    with patch(
        "src.services.data_manager.manager.DataManager._fetch_insider_trades_yfinance",
        AsyncMock(side_effect=RuntimeError("yahoo unavailable")),
    ):
        with pytest.raises(DataFetchError, match="All providers failed"):
            await manager._fetch_insider_trades("AAPL")


@pytest.mark.asyncio
async def test_treasury_prefers_configured_fred_and_closes_client() -> None:
    av = _Av()
    fred = SimpleNamespace(
        get_series=AsyncMock(
            return_value=pd.DataFrame(
                {"value": [4.5]}, index=[pd.Timestamp("2026-08-05")]
            )
        ),
        close=AsyncMock(),
    )
    with (
        patch(
            "src.core.config.get_settings",
            return_value=SimpleNamespace(fred_api_key="fred-key"),
        ),
        patch("src.services.market_data.fred.FREDService", return_value=fred),
    ):
        rows = await _manager(av)._fetch_treasury("10y", "daily")

    assert len(rows) == 1
    assert rows[0].yield_value == 4.5
    fred.get_series.assert_awaited_once_with("DGS10", days=365)
    fred.close.assert_awaited_once()
    av.get_treasury_yield.assert_not_awaited()


@pytest.mark.asyncio
async def test_price_on_date_prefers_forward_cached_bar() -> None:
    manager = _manager(_Av())
    target = datetime(2026, 8, 8)  # Saturday
    monday = target.replace(tzinfo=UTC) + timedelta(days=2)
    manager.get_ohlcv = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            OHLCVData(
                date=monday,
                open=199,
                high=202,
                low=198,
                close=201,
                volume=1000,
            )
        ]
    )
    manager._price_on_date_yfinance = AsyncMock()  # type: ignore[method-assign]

    price = await manager.get_price_on_date("aapl", target, max_forward_days=3)

    assert price == 201
    manager._price_on_date_yfinance.assert_not_awaited()


@pytest.mark.asyncio
async def test_price_on_date_uses_yfinance_after_primary_failure() -> None:
    manager = _manager(_Av())
    manager.get_ohlcv = AsyncMock(  # type: ignore[method-assign]
        side_effect=DataFetchError("primary down", "market")
    )
    manager._price_on_date_yfinance = AsyncMock(  # type: ignore[method-assign]
        return_value=188.5
    )
    target = datetime(2026, 8, 8, tzinfo=UTC)

    assert await manager.get_price_on_date("AAPL", target) == 188.5
    manager._price_on_date_yfinance.assert_awaited_once()


@pytest.mark.asyncio
async def test_price_on_date_returns_none_when_fallback_raises() -> None:
    manager = _manager(_Av())
    manager.get_ohlcv = AsyncMock(return_value=[])  # type: ignore[method-assign]
    manager._price_on_date_yfinance = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("yahoo down")
    )
    assert await manager.get_price_on_date("AAPL", datetime(2026, 8, 8)) is None
