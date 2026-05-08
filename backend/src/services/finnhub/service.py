"""
Finnhub market data service.

Standalone async client for Finnhub.io REST API. Used as the primary provider
for real-time quote, company news, and insider trades — domains where Finnhub's
60/min free tier (no daily cap) outperforms Alpha Vantage's 5/min · 500/day.

Failures (HTTP non-200, timeout, empty/error payload) raise DataFetchError;
DataManager catches and routes to the next provider in the fallback chain.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from ..data_manager.types import DataFetchError, NewsData, QuoteData

logger = structlog.get_logger(__name__)

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
DEFAULT_TIMEOUT = 10.0


class FinnhubService:
    """Async client for Finnhub REST endpoints."""

    def __init__(self, api_key: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        if not api_key:
            raise ValueError("FinnhubService requires a non-empty api_key")
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=FINNHUB_BASE_URL,
            timeout=timeout,
            headers={"X-Finnhub-Token": api_key},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            r = await self._client.get(path, params=params or {})
        except httpx.TimeoutException as e:
            raise DataFetchError(f"finnhub timeout on {path}", "finnhub") from e
        except httpx.HTTPError as e:
            raise DataFetchError(f"finnhub http error on {path}: {e}", "finnhub") from e

        if r.status_code != 200:
            raise DataFetchError(
                f"finnhub {path} returned HTTP {r.status_code}",
                "finnhub",
            )

        body = r.json()
        if isinstance(body, dict) and body.get("error"):
            raise DataFetchError(f"finnhub error: {body['error']}", "finnhub")
        return body

    async def fetch_quote(self, symbol: str) -> QuoteData:
        """
        GET /quote — real-time quote.
        Response: {c: current, d: change, dp: pct, h: high, l: low, o: open, pc: prev_close, t: ts}

        NOTE: Finnhub /quote returns the last RTH trade only; it cannot
        produce a pre/post extended-hours session label. We therefore stamp
        session="regular" unconditionally. yfinance is the provider that
        supplies extended-hours data.
        """
        body = await self._get("/quote", {"symbol": symbol.upper()})
        if not isinstance(body, dict) or "c" not in body or body.get("c") in (None, 0):
            raise DataFetchError(f"finnhub quote empty for {symbol}", "finnhub")

        ts = body.get("t") or 0
        latest_day = datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d") if ts else ""
        return QuoteData(
            symbol=symbol.upper(),
            price=float(body["c"]),
            volume=0,  # Finnhub /quote doesn't include volume; AV does
            latest_trading_day=latest_day,
            previous_close=float(body.get("pc", 0.0)),
            change=float(body.get("d", 0.0)),
            change_percent=float(body.get("dp", 0.0)),
            open=float(body.get("o", 0.0)),
            high=float(body.get("h", 0.0)),
            low=float(body.get("l", 0.0)),
            session="regular",
            source="finnhub",
            asof=datetime.fromtimestamp(ts, UTC) if ts else datetime.now(UTC),
        )

    async def fetch_company_news(
        self, symbol: str, from_date: str, to_date: str
    ) -> list[NewsData]:
        """
        GET /company-news — news for a symbol within a date window.
        from_date / to_date format: YYYY-MM-DD.
        Response: list of {category, datetime (unix), headline, image, related, source, summary, url}
        """
        body = await self._get(
            "/company-news",
            {"symbol": symbol.upper(), "from": from_date, "to": to_date},
        )
        if not isinstance(body, list):
            raise DataFetchError(f"finnhub news non-list for {symbol}", "finnhub")

        out: list[NewsData] = []
        for item in body:
            if not isinstance(item, dict):
                continue
            ts = item.get("datetime") or 0
            try:
                dt = datetime.fromtimestamp(int(ts), UTC) if ts else datetime.now(UTC)
            except (TypeError, ValueError):
                dt = datetime.now(UTC)
            out.append(
                NewsData(
                    date=dt,
                    sentiment_score=0.0,  # Finnhub /company-news has no sentiment
                    ticker_relevance=1.0,  # Symbol-scoped query → relevance 1.0
                    title=str(item.get("headline", "")),
                    source=str(item.get("source", "finnhub")),
                )
            )
        return out

    async def fetch_insider_transactions(self, symbol: str) -> list[dict[str, Any]]:
        """
        GET /stock/insider-transactions — recent insider trades.
        Response: {data: [{name, share, change, filingDate, transactionDate, transactionCode, transactionPrice}], symbol}
        """
        body = await self._get(
            "/stock/insider-transactions", {"symbol": symbol.upper()}
        )
        if not isinstance(body, dict):
            raise DataFetchError(f"finnhub insider non-dict for {symbol}", "finnhub")
        data = body.get("data")
        if not isinstance(data, list):
            return []
        return data
