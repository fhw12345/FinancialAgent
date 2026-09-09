"""Deterministic outer market/cache fixtures shared by PH-002 composition and E2E."""

from collections import Counter
from datetime import UTC, datetime, timedelta

import pandas as pd

from src.services.data_manager import CacheKeys
from src.services.data_manager.types import SymbolPCRData

SYMBOLS = ["NVDA", "MSFT", "AMD", "PLTR"]


class RecordedMarket:
    def __init__(self):
        self.calls = Counter()
        self.outputs = []
        self.fail_news = False

    async def get_etf_profile(self, symbol):
        self.calls["basket"] += 1
        return {"holdings": [{"symbol": s, "weight": 0.2} for s in SYMBOLS]}

    async def bars(
        self, symbol, granularity, outputsize, start_date=None, end_date=None
    ):
        self.calls[f"ohlcv:{symbol}"] += 1
        self.outputs.append(outputsize)
        prices = [100 + i * 0.1 for i in range(250)]
        return pd.DataFrame(
            {
                "Open": prices,
                "High": prices,
                "Low": prices,
                "Close": prices,
                "Volume": [1000] * 250,
            },
            index=pd.date_range("2025-01-01", periods=250, tz="UTC"),
        )

    async def get_daily_bars(self, symbol, outputsize="full"):
        return await self.bars(symbol, "daily", outputsize)

    async def get_intraday_bars(self, symbol, **kwargs):
        self.calls[f"intraday:{symbol}"] += 1
        return pd.DataFrame(
            {"Open": [100, 100], "Close": [101, 102]},
            index=pd.date_range(
                "2026-09-08T09:30:00", periods=2, freq="h", tz="America/New_York"
            ),
        )

    async def get_treasury_yield(self, maturity, interval="daily"):
        self.calls[f"treasury:{maturity}"] += 1
        return pd.DataFrame(
            {"value": [4.5 - i * 0.01 for i in range(25)]},
            index=pd.date_range("2026-08-01", periods=25, tz="UTC"),
        )

    async def get_news_sentiment(self, **kwargs):
        self.calls["news"] += 1
        if self.fail_news:
            raise RuntimeError("fixture news unavailable")
        return {
            "feed": [
                {
                    "time_published": "20260909T120000",
                    "overall_sentiment_score": 0.14,
                    "title": "Recorded technology news",
                    "source": "fixture",
                }
            ]
        }

    async def get_ipo_calendar(self):
        self.calls["ipo"] += 1
        return pd.DataFrame(
            [
                {
                    "ipoDate": (datetime.now(UTC) + timedelta(days=30)).strftime(
                        "%Y-%m-%d"
                    ),
                    "name": "Fixture Tech",
                    "exchange": "NASDAQ",
                }
            ]
        )


class RecordedFred:
    async def get_sofr(self, days=60):
        return pd.DataFrame({"value": [4.51] * days})

    async def get_effr(self, days=60):
        return pd.DataFrame({"value": [4.5] * days})

    async def get_rrp_balance(self, days=60):
        return pd.DataFrame({"value": [1000.0] * days})


async def seed_pcr(cache):
    for symbol in SYMBOLS:
        data = SymbolPCRData(
            symbol, 100, 85, 115, 1, 1, 20, 1, "neutral fixture", datetime.now(UTC)
        )
        await cache.set(CacheKeys.pcr_symbol(symbol), data.to_dict(), ttl_seconds=3600)
