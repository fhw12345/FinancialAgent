"""
Symbol search via yfinance — fallback for newly-IPO'd / small-cap tickers
that aren't in our local sector_universe.csv (S&P 500 + Nasdaq 100).

The local CSV covers ~515 large-caps. Alpha Vantage SYMBOL_SEARCH would catch
the rest, but its free tier (25 req/day) blows out fast. yfinance has no key,
no daily cap, and surfaces newly-listed names like CRWV (CoreWeave, IPO'd
2025-03) almost immediately.

Two access paths used:

1. **Exact ticker probe** via `yf.Ticker(query).info` — handles the case where
   the user types a ticker we've never heard of (most likely intent for an
   uppercase 1-5 letter query).
2. **Free-text search** via `yf.Search(query)` — handles company-name queries
   like "coreweave".

Output is filtered to US equity exchanges only; foreign listings (`CRWV.MX`,
`I1V.F`, etc.) and ETPs that wrap a US ticker get dropped.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
import yfinance as yf

logger = structlog.get_logger()

# Yahoo's exchange codes for US-listed equities. Anything else (LSE, FRA, MEX,
# DUS…) is filtered out. Keep this conservative — adding a foreign exchange
# would let `CRWV.MX` show up alongside `CRWV` and confuse the user.
_US_EXCHANGES = {
    "NMS",  # Nasdaq Global Select
    "NGM",  # Nasdaq Global Market
    "NCM",  # Nasdaq Capital Market
    "NYQ",  # NYSE
    "ASE",  # NYSE American
    "PCX",  # NYSE Arca
    "BTS",  # BATS
    "OTC",  # Over-the-counter
}


def _is_us_equity(symbol: str | None, exchange: str | None, quote_type: str | None) -> bool:
    if not symbol or "." in symbol:
        # Foreign tickers are formatted SYMBOL.EXCHANGE on Yahoo
        # (e.g. CRWV.MX, I1V.F). US tickers have no dot.
        return False
    if quote_type and quote_type.upper() != "EQUITY":
        return False
    if exchange and exchange.upper() not in _US_EXCHANGES:
        return False
    return True


def _ticker_probe(query: str) -> dict[str, Any] | None:
    """If `query` looks like a ticker, return its info dict (or None)."""
    q = query.strip().upper()
    if not (1 <= len(q) <= 5) or not q.isalpha():
        return None
    try:
        info = yf.Ticker(q).info or {}
    except Exception as e:
        logger.debug("yfinance Ticker probe failed", query=q, error=str(e))
        return None
    if not _is_us_equity(info.get("symbol"), info.get("exchange"), info.get("quoteType")):
        return None
    if info.get("symbol", "").upper() != q:
        # Defensive: yfinance sometimes echoes back a different symbol on a
        # bad lookup. Only trust an exact match.
        return None
    return info


def _name_search(query: str, limit: int) -> list[dict[str, Any]]:
    """Fuzzy-search Yahoo by company name. Returns raw quote dicts."""
    try:
        # max_results gets a few extra so we can drop foreign listings and
        # still come out near `limit`.
        s = yf.Search(query, max_results=max(limit * 3, 10))
        return list(s.quotes or [])
    except Exception as e:
        logger.debug("yfinance Search failed", query=query, error=str(e))
        return []


def _fetch_sync(query: str, limit: int) -> list[dict[str, Any]]:
    """Blocking fetch — run via to_thread. Output is SymbolSearchResult-shaped."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Path 1: exact ticker probe — strongest signal, surface first.
    info = _ticker_probe(query)
    if info:
        sym = info["symbol"].upper()
        out.append(
            {
                "symbol": sym,
                "name": info.get("longName") or info.get("shortName") or sym,
                "exchange": info.get("exchange", "") or "",
                "type": (info.get("quoteType") or "EQUITY").lower(),
                "match_type": "exact_symbol",
                "confidence": 1.0,
            }
        )
        seen.add(sym)

    # Path 2: free-text search — catches company-name queries.
    raw = _name_search(query, limit)
    q_upper = query.strip().upper()
    for q in raw:
        sym = (q.get("symbol") or "").upper()
        if not sym or sym in seen:
            continue
        if not _is_us_equity(sym, q.get("exchange"), q.get("quoteType")):
            continue

        # Confidence: exact symbol = 0.95 (already covered above but keep
        # consistent), prefix match = 0.85, otherwise 0.7.
        if sym == q_upper:
            match_type, confidence = "exact_symbol", 0.95
        elif sym.startswith(q_upper):
            match_type, confidence = "symbol_prefix", 0.85
        else:
            match_type, confidence = "fuzzy", 0.7

        out.append(
            {
                "symbol": sym,
                "name": q.get("shortname") or q.get("longname") or sym,
                "exchange": q.get("exchange", "") or "",
                "type": (q.get("quoteType") or "EQUITY").lower(),
                "match_type": match_type,
                "confidence": confidence,
            }
        )
        seen.add(sym)
        if len(out) >= limit:
            break

    return out


async def search_symbols(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Async wrapper. Returns [] on any error rather than raising — this is a
    fallback and we'd rather show empty than 500 the route."""
    try:
        return await asyncio.to_thread(_fetch_sync, query, limit)
    except Exception as e:
        logger.warning("yfinance symbol search failed", query=query, error=str(e))
        return []
