"""
Market movers via yfinance (Yahoo Finance) — primary source.

Used as the primary fetcher for `/api/market/market-movers` because the
Alpha Vantage free tier is capped at 25 requests/day, which we blow through
in a few page loads. Yahoo Finance has no key, no daily cap, and exposes the
same three buckets (day gainers / day losers / most active).

Output shape mirrors `AlphaVantageMarketDataService.get_top_gainers_losers()`
so the route handler and downstream consumers don't need to know which source
the data came from:

    {
        "top_gainers":            [ {ticker, price, change_amount, change_percentage, volume}, ... ],
        "top_losers":             [ ... ],
        "most_actively_traded":   [ ... ],
        "last_updated":           "<UTC ISO>",
        "source":                 "yfinance",
    }

`change_percentage` is a string with a trailing `%` to match Alpha Vantage.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
import yfinance as yf

from src.core.utils.date_utils import utcnow

logger = structlog.get_logger()

# yfinance Screener id  →  AV-style bucket key
_SCREENER_TO_BUCKET = {
    "day_gainers": "top_gainers",
    "day_losers": "top_losers",
    "most_actives": "most_actively_traded",
}


def _adapt_quote(q: dict[str, Any]) -> dict[str, Any] | None:
    """Map a yfinance quote dict to the Alpha Vantage mover row shape.

    Returns None if the row is missing fields we can't fake (ticker / price)."""
    ticker = q.get("symbol")
    price = q.get("regularMarketPrice")
    if ticker is None or price is None:
        return None
    change = q.get("regularMarketChange") or 0.0
    change_pct = q.get("regularMarketChangePercent") or 0.0
    volume = q.get("regularMarketVolume") or 0
    return {
        "ticker": str(ticker),
        "price": float(price),
        "change_amount": float(change),
        # AV returns this as a string like "57.2513%" — keep that contract so
        # downstream parsers (`float(item["change_percentage"].rstrip("%"))`)
        # don't have to special-case the source.
        "change_percentage": f"{float(change_pct):.4f}%",
        "volume": int(volume),
    }


def _fetch_sync(count: int) -> dict[str, list[dict[str, Any]]]:
    """Blocking fetch of all three screener buckets. Run via to_thread."""
    out: dict[str, list[dict[str, Any]]] = {
        "top_gainers": [],
        "top_losers": [],
        "most_actively_traded": [],
    }
    for screener_id, bucket in _SCREENER_TO_BUCKET.items():
        try:
            r = yf.screen(screener_id, count=count)
            quotes = r.get("quotes", []) if isinstance(r, dict) else []
            adapted = [_adapt_quote(q) for q in quotes]
            out[bucket] = [row for row in adapted if row is not None]
        except Exception as e:
            # Per-bucket failure shouldn't kill the whole response — log and
            # leave that bucket empty.
            logger.warning(
                "yfinance_screener_bucket_failed",
                screener=screener_id,
                error=str(e),
            )
    return out


async def get_market_movers(count: int = 20) -> dict[str, Any]:
    """Async wrapper. Raises if every bucket comes back empty."""
    buckets = await asyncio.to_thread(_fetch_sync, count)
    total = sum(len(v) for v in buckets.values())
    if total == 0:
        raise RuntimeError("yfinance returned no movers across all three buckets")
    return {
        **buckets,
        "last_updated": utcnow().isoformat(),
        "source": "yfinance",
    }
