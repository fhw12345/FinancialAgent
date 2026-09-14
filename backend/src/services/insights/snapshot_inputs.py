"""Request-local snapshot inputs: real DataManager prefetch, no singleton mutation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from ..data_manager import DataManager
from ..data_manager.types import (
    DataFetchError,
    Granularity,
    IPOData,
    NewsData,
    OHLCVData,
    TreasuryData,
)
from .base import InsightCategoryBase
from .categories.ai_sector_risk import AISectorRiskCategory


class FullHistoryPrefetch(DataManager):
    """Use the real inherited prefetch orchestrator with four delegated readers.

    Snapshot price metrics need >=200 days, not the compact 100-bar default.
    Only prefetch_shared is exposed to the caller; normal DataManager caches and
    provider fallback remain owned by the source, not copied or reconfigured.
    """

    def __init__(self, source: DataManager) -> None:
        self.source = source

    async def get_ohlcv(
        self,
        symbol: str,
        granularity: str | Granularity,
        outputsize: str = "compact",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[OHLCVData]:
        return await self.source.get_ohlcv(
            symbol, granularity, "full", start_date, end_date
        )

    async def get_treasury(
        self, maturity: str, interval: str = "daily"
    ) -> list[TreasuryData]:
        return await self.source.get_treasury(maturity, interval)

    async def get_news_sentiment(
        self, topic: str | None = None, tickers: list[str] | None = None
    ) -> list[NewsData]:
        return await self.source.get_news_sentiment(topic, tickers)

    async def get_ipo_calendar(self) -> list[IPOData]:
        return await self.source.get_ipo_calendar()


class PrefetchedMarketData:
    """Adapt typed DML rows to the existing calculators' provider shapes.

    Failed prefetched sources raise a typed data error: calculators retain their
    explicit placeholder behavior instead of making a duplicate network request.
    Unshared capabilities (intraday/options/etc.) delegate to the original source.
    """

    def __init__(self, source: Any, shared: dict[str, Any]) -> None:
        self.source = source
        self.shared = shared

    def __getattr__(self, name: str) -> Any:
        return getattr(self.source, name)

    def _check(self, key: str) -> None:
        if key in self.shared["errors"]:
            raise DataFetchError(self.shared["errors"][key], key)

    async def get_daily_bars(
        self, symbol: str, outputsize: str = "full"
    ) -> pd.DataFrame:
        self._check(f"ohlcv:{symbol.upper()}")
        rows: list[OHLCVData] = self.shared["ohlcv"][symbol.upper()]
        frame = pd.DataFrame(
            [
                {
                    "date": row.date,
                    "Open": row.open,
                    "High": row.high,
                    "Low": row.low,
                    "Close": row.close,
                    "Volume": row.volume,
                }
                for row in rows
            ],
            columns=["date", "Open", "High", "Low", "Close", "Volume"],
        )
        return frame.set_index("date").sort_index()

    async def get_treasury_yield(
        self, maturity: str, interval: str = "daily"
    ) -> pd.DataFrame:
        key = maturity.lower().replace("year", "y")
        self._check(f"treasury:{key}")
        rows: list[TreasuryData] = self.shared["treasury"][key]
        return pd.DataFrame(
            {"value": [row.yield_value for row in rows]},
            index=pd.DatetimeIndex([row.date for row in rows]),
        ).sort_index()

    async def get_news_sentiment(
        self, topics: str = "technology", limit: int = 50
    ) -> dict[str, Any]:
        self._check(f"news:{topics}")
        rows: list[NewsData] = self.shared["news"][topics]
        return {
            "feed": [
                {"overall_sentiment_score": row.sentiment_score, "title": row.title}
                for row in rows[:limit]
            ]
        }

    async def get_ipo_calendar(self) -> list[dict[str, Any]]:
        self._check("ipo:calendar")
        rows: list[IPOData] = self.shared["ipo"]
        return [
            {
                "ipoDate": row.date.strftime("%Y-%m-%d"),
                "name": row.name,
                "exchange": row.exchange,
            }
            for row in rows
        ]


class PreparedAICategory(AISectorRiskCategory):
    """Private per-run instance; every calculator sees the same resolved basket."""

    def __init__(
        self,
        original: AISectorRiskCategory,
        shared: dict[str, Any],
        basket: tuple[list[str], str],
    ) -> None:
        super().__init__(
            settings=original.settings,
            redis_cache=original.redis_cache,
            market_service=PrefetchedMarketData(original.market_service, shared),
            fred_service=original.fred_service,
        )
        self.basket = basket

    async def _get_ai_basket_symbols(self) -> tuple[list[str], str]:
        return self.basket


@dataclass
class SnapshotInputs:
    category: InsightCategoryBase
    manager: DataManager
    basket: tuple[list[str], str] | None = None

    @property
    def symbols(self) -> list[str] | None:
        return self.basket[0] if self.basket is not None else None

    def calculator(self, shared: dict[str, Any]) -> InsightCategoryBase:
        if isinstance(self.category, AISectorRiskCategory) and self.basket is not None:
            return PreparedAICategory(self.category, shared, self.basket)
        return self.category


async def prepare_snapshot_inputs(
    category: InsightCategoryBase, manager: DataManager
) -> SnapshotInputs:
    if isinstance(category, AISectorRiskCategory):
        basket = await category._get_ai_basket_symbols()
        return SnapshotInputs(category, FullHistoryPrefetch(manager), basket)
    # Preserve the existing plugin behavior for non-AI categories.
    return SnapshotInputs(category, manager)
