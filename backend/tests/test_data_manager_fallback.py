"""DataManager fallback chain tests for Finnhub → AV → yfinance.

Critical correctness tests:
- Finnhub success → AV/yfinance not called
- Finnhub fails → AV called → success
- Both fail → yfinance called → success
- All three fail → DataFetchError("all_providers")
- finnhub_service=None → AV tried first (skip Finnhub silently)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.data_manager.manager import DataManager
from src.services.data_manager.types import DataFetchError, NewsData, QuoteData


def _quote(symbol: str, price: float) -> QuoteData:
    return QuoteData(
        symbol=symbol,
        price=price,
        volume=1000,
        latest_trading_day="2026-05-04",
        previous_close=price - 1,
        change=1.0,
        change_percent=0.5,
        open=price - 0.5,
        high=price + 0.5,
        low=price - 1.0,
    )


def _news(title: str) -> NewsData:
    from datetime import UTC, datetime

    return NewsData(
        date=datetime.now(UTC),
        sentiment_score=0.0,
        ticker_relevance=1.0,
        title=title,
        source="test",
    )


def _make_dm(finnhub_service=None, av_service=None, redis_cache=None) -> DataManager:
    if redis_cache is None:
        redis_cache = MagicMock()
        redis_cache.get = AsyncMock(return_value=None)  # No cache hits
        redis_cache.setex = AsyncMock(return_value=True)
    if av_service is None:
        av_service = MagicMock()
    return DataManager(
        redis_cache=redis_cache,
        alpha_vantage_service=av_service,
        finnhub_service=finnhub_service,
    )


# ====== get_quote fallback chain ======


class TestQuoteFallback:
    @pytest.mark.asyncio
    async def test_finnhub_success_skips_av(self):
        finnhub = MagicMock()
        finnhub.fetch_quote = AsyncMock(return_value=_quote("AAPL", 280.0))
        av = MagicMock()
        av.get_quote = AsyncMock()  # Should NOT be called
        dm = _make_dm(finnhub, av)

        q = await dm.get_quote("AAPL")

        assert q.price == 280.0
        finnhub.fetch_quote.assert_awaited_once_with("AAPL")
        av.get_quote.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_finnhub_fails_av_succeeds(self):
        finnhub = MagicMock()
        finnhub.fetch_quote = AsyncMock(side_effect=DataFetchError("boom", "finnhub"))
        av = MagicMock()
        av.get_quote = AsyncMock(
            return_value={
                "symbol": "AAPL",
                "price": 281.0,
                "volume": 100,
                "latest_trading_day": "2026-05-04",
                "previous_close": 280.0,
                "change": 1.0,
                "change_percent": 0.36,
                "open": 280.5,
                "high": 281.5,
                "low": 279.5,
            }
        )
        dm = _make_dm(finnhub, av)

        # Patch yfinance fallback so a bug in AV path can't silently rescue
        with patch.object(
            DataManager,
            "_fetch_quote_yfinance",
            new=AsyncMock(side_effect=AssertionError("yfinance must NOT be called")),
        ):
            q = await dm.get_quote("AAPL")

        assert q.price == 281.0
        finnhub.fetch_quote.assert_awaited_once()
        av.get_quote.assert_awaited_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_both_fail_yfinance_rescues(self):
        finnhub = MagicMock()
        finnhub.fetch_quote = AsyncMock(side_effect=Exception("x"))
        av = MagicMock()
        av.get_quote = AsyncMock(side_effect=Exception("y"))
        dm = _make_dm(finnhub, av)

        with patch.object(
            DataManager,
            "_fetch_quote_yfinance",
            new=AsyncMock(return_value=_quote("AAPL", 282.0)),
        ):
            q = await dm.get_quote("AAPL")

        assert q.price == 282.0

    @pytest.mark.asyncio
    async def test_all_three_fail_raises(self):
        finnhub = MagicMock()
        finnhub.fetch_quote = AsyncMock(side_effect=Exception("x"))
        av = MagicMock()
        av.get_quote = AsyncMock(side_effect=Exception("y"))
        dm = _make_dm(finnhub, av)

        with patch.object(
            DataManager,
            "_fetch_quote_yfinance",
            new=AsyncMock(side_effect=Exception("z")),
        ):
            with pytest.raises(DataFetchError, match="all_providers"):
                await dm.get_quote("AAPL")

    @pytest.mark.asyncio
    async def test_finnhub_none_av_tried_first(self):
        av = MagicMock()
        av.get_quote = AsyncMock(
            return_value={
                "symbol": "AAPL",
                "price": 281.0,
                "volume": 100,
                "latest_trading_day": "2026-05-04",
                "previous_close": 280.0,
                "change": 1.0,
                "change_percent": 0.36,
                "open": 280.5,
                "high": 281.5,
                "low": 279.5,
            }
        )
        dm = _make_dm(finnhub_service=None, av_service=av)

        with patch.object(
            DataManager,
            "_fetch_quote_yfinance",
            new=AsyncMock(side_effect=AssertionError("yfinance must NOT be called")),
        ):
            q = await dm.get_quote("AAPL")

        assert q.price == 281.0
        av.get_quote.assert_awaited_once()


# ====== get_company_news fallback chain ======


class TestCompanyNewsFallback:
    @pytest.mark.asyncio
    async def test_finnhub_success(self):
        finnhub = MagicMock()
        finnhub.fetch_company_news = AsyncMock(return_value=[_news("Apple beats Q2")])
        av = MagicMock()
        av.get_news_sentiment = AsyncMock()
        dm = _make_dm(finnhub, av)

        items = await dm.get_company_news("AAPL", "2026-04-01", "2026-05-01")

        assert len(items) == 1
        assert items[0].title == "Apple beats Q2"
        av.get_news_sentiment.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_finnhub_fails_av_succeeds(self):
        finnhub = MagicMock()
        finnhub.fetch_company_news = AsyncMock(side_effect=Exception("x"))
        av = MagicMock()
        av.get_news_sentiment = AsyncMock(
            return_value={
                "feed": [
                    {
                        "title": "AV news",
                        "time_published": "20260501T120000",
                        "overall_sentiment_score": "0.1",
                    }
                ]
            }
        )
        dm = _make_dm(finnhub, av)

        items = await dm.get_company_news("AAPL", "2026-04-01", "2026-05-01")

        # AV path returns NewsData via _fetch_news_sentiment helper
        assert isinstance(items, list)
        finnhub.fetch_company_news.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_all_fail_raises(self):
        finnhub = MagicMock()
        finnhub.fetch_company_news = AsyncMock(side_effect=Exception("x"))
        av = MagicMock()
        av.get_news_sentiment = AsyncMock(side_effect=Exception("y"))
        dm = _make_dm(finnhub, av)

        with patch.object(
            DataManager,
            "_fetch_company_news_yfinance",
            new=AsyncMock(side_effect=Exception("z")),
        ):
            with pytest.raises(DataFetchError, match="all_providers"):
                await dm.get_company_news("AAPL", "2026-04-01", "2026-05-01")


# ====== get_insider_trades fallback chain ======


class TestInsiderFallback:
    @pytest.mark.asyncio
    async def test_finnhub_success(self):
        finnhub = MagicMock()
        finnhub.fetch_insider_transactions = AsyncMock(
            return_value=[{"name": "Tim Cook", "share": 1000}]
        )
        av = MagicMock()
        dm = _make_dm(finnhub, av)

        rows = await dm.get_insider_trades("AAPL")

        assert len(rows) == 1
        assert rows[0]["name"] == "Tim Cook"

    @pytest.mark.asyncio
    async def test_finnhub_none_av_used(self):
        av = MagicMock()
        av.get_insider_transactions = AsyncMock(
            return_value={"data": [{"name": "AV insider", "share": 500}]}
        )
        dm = _make_dm(finnhub_service=None, av_service=av)

        rows = await dm.get_insider_trades("AAPL")

        assert len(rows) == 1
        assert rows[0]["name"] == "AV insider"
