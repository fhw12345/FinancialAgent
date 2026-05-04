"""
Symbol search and market movers endpoints.

Handles symbol lookups, asset information, and market-wide trending stocks.
"""

from functools import lru_cache
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ...core.config import Settings
from ...core.utils.cache_utils import get_tool_ttl
from ...database.redis import RedisCache
from ...services.alphavantage_market_data import AlphaVantageMarketDataService
from ..dependencies.chat_deps import get_redis

router = APIRouter()
logger = structlog.get_logger()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def get_market_service() -> AlphaVantageMarketDataService:
    """Dependency to get market data service."""
    return AlphaVantageMarketDataService(get_settings())


class SymbolSearchResult(BaseModel):
    """Symbol search result."""

    symbol: str = Field(..., description="Stock symbol (e.g., AAPL)")
    name: str = Field(..., description="Company name")
    exchange: str = Field(default="", description="Exchange name")
    type: str = Field(default="", description="Security type")
    match_type: str = Field(
        default="",
        description="Match classification: exact_symbol | symbol_prefix | name_prefix | fuzzy",
    )
    confidence: float = Field(
        default=0.0, description="Confidence score 0-1 for ranking"
    )


class SymbolSearchResponse(BaseModel):
    """Symbol search response."""

    query: str = Field(..., description="Original search query")
    results: list[SymbolSearchResult] = Field(..., description="Search results")


@router.get("/search", response_model=SymbolSearchResponse)
async def search_symbols(
    q: str = Query(
        ...,
        min_length=1,
        max_length=50,
        description="Search query (company name or partial symbol)",
    ),
    service: AlphaVantageMarketDataService = Depends(get_market_service),
) -> SymbolSearchResponse:
    """
    Search for stock symbols.

    Provider chain:
      1. Local CSV (515 S&P 500 + Nasdaq 100 symbols) — instant, zero network
      2. Alpha Vantage SYMBOL_SEARCH — broader coverage but rate-limited (25/day on free)
      3. yfinance Search / Ticker probe — no key, no daily cap; catches recent
         IPOs and small-caps the local CSV misses (e.g. CRWV / CoreWeave)

    The local CSV covers the bulk of common queries. AV is consulted next for
    its richer match metadata. yfinance is the final safety net when AV fails
    or returns nothing — common because the AV free tier is quickly exhausted.
    """
    from src.services.market_data import yfinance_search

    try:
        query = q.strip()
        if len(query) < 1:
            raise ValueError("Search query must be at least 1 character")

        logger.info("Symbol search started", query=query)

        # Provider 1: local sector_universe.csv (instant)
        local_results = _search_local_universe(query, limit=10)
        if local_results:
            logger.info(
                "Symbol search served from local universe",
                query=query,
                result_count=len(local_results),
            )
            return SymbolSearchResponse(query=query, results=local_results)

        # Provider 2: Alpha Vantage (slower, rate-limited, but broader)
        results: list[SymbolSearchResult] = []
        try:
            raw_results = await service.search_symbols(query, limit=10)
            results = [
                SymbolSearchResult(
                    symbol=r["symbol"],
                    name=r["name"],
                    exchange=r["exchange"],
                    type=r["type"],
                    match_type=r["match_type"],
                    confidence=r["confidence"],
                )
                for r in raw_results
            ]
        except Exception as e:
            logger.warning(
                "Alpha Vantage symbol search failed, will try yfinance",
                query=query,
                error=str(e),
            )

        # Provider 3: yfinance (free, no cap) — kicks in when AV failed OR
        # returned nothing (e.g. recent IPOs not yet in AV's index).
        if not results:
            yf_raw = await yfinance_search.search_symbols(query, limit=10)
            results = [SymbolSearchResult(**r) for r in yf_raw]
            if results:
                logger.info(
                    "Symbol search served from yfinance fallback",
                    query=query,
                    result_count=len(results),
                )

        logger.info(
            "Symbol search completed",
            query=query,
            result_count=len(results),
        )

        return SymbolSearchResponse(query=query, results=results)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(
            "Symbol search failed", query=q, error=str(e), error_type=type(e).__name__
        )
        raise HTTPException(
            status_code=500, detail=f"Symbol search failed: {str(e)}"
        ) from e


def _search_local_universe(query: str, limit: int) -> list[SymbolSearchResult]:
    """
    Search the committed sector_universe.csv (515 large-caps).

    Ranking:
      1. Exact symbol match (confidence 1.0)
      2. Symbol prefix match (0.9)
      3. Name prefix match (0.8)
      4. Substring match in symbol or name (0.6)
    """
    from ...data.sector_universe import load_universe

    q_upper = query.upper()
    q_lower = query.lower()
    rows = load_universe()
    if not rows:
        return []

    scored: list[tuple[float, str, SymbolSearchResult]] = []
    for r in rows:
        sym_u = r.symbol.upper()
        name_l = r.name.lower()
        match_type = ""
        confidence = 0.0
        if sym_u == q_upper:
            match_type, confidence = "exact_symbol", 1.0
        elif sym_u.startswith(q_upper):
            match_type, confidence = "symbol_prefix", 0.9
        elif name_l.startswith(q_lower):
            match_type, confidence = "name_prefix", 0.8
        elif q_upper in sym_u or q_lower in name_l:
            match_type, confidence = "fuzzy", 0.6
        else:
            continue
        scored.append(
            (
                confidence,
                sym_u,
                SymbolSearchResult(
                    symbol=r.symbol,
                    name=r.name,
                    exchange="",  # CSV has no exchange field
                    type="Equity",
                    match_type=match_type,
                    confidence=confidence,
                ),
            )
        )

    # Sort: confidence desc, then symbol asc (deterministic tiebreak)
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [s[2] for s in scored[:limit]]


@router.get("/info/{symbol}")
async def get_symbol_info(
    symbol: str,
    service: AlphaVantageMarketDataService = Depends(get_market_service),
) -> dict[str, str]:
    """
    Get basic symbol information from Alpaca.

    Returns symbol, name, exchange for autocomplete enhancement.
    Note: Alpaca provides limited fundamental data compared to yfinance.
    """
    try:
        symbol = symbol.upper().strip()

        # Get assets and find matching symbol
        assets = await service._get_alpaca_assets()  # type: ignore[attr-defined]
        matching_asset = next((a for a in assets if a.symbol == symbol), None)

        if not matching_asset:
            raise ValueError(f"Symbol {symbol} not found")

        return {
            "symbol": matching_asset.symbol,
            "name": matching_asset.name,
            "exchange": (
                matching_asset.exchange.value
                if hasattr(matching_asset.exchange, "value")
                else str(matching_asset.exchange)
            ),
            "type": (
                matching_asset.asset_class.value
                if hasattr(matching_asset.asset_class, "value")
                else "EQUITY"
            ),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Symbol info fetch failed", symbol=symbol, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch symbol info: {str(e)}"
        ) from e


@router.get("/market-movers")
async def get_market_movers(
    service: AlphaVantageMarketDataService = Depends(get_market_service),
    redis_cache: RedisCache = Depends(get_redis),
) -> dict[str, Any]:
    """
    Get today's top market movers with 30-minute caching.

    Source priority: yfinance (primary, no rate limit) → Alpha Vantage (fallback,
    25 req/day free tier). yfinance is preferred because the AV free key is
    exhausted within a few page loads. AV is kept as a backup in case Yahoo's
    public screener endpoint is down.

    Returns:
    - top_gainers: Top 20 stocks with highest price increase (% and $)
    - top_losers: Top 20 stocks with largest price decrease (% and $)
    - most_actively_traded: Top 20 stocks by trading volume
    - source: "yfinance" or "alpha_vantage" — which provider actually served this

    Each entry includes: ticker, price, change_amount, change_percentage, volume

    Cache Duration: 30 minutes — applies to whichever source succeeded.
    """
    from src.services.market_data import yfinance_movers

    logger.info("Market movers request")
    cache_key = "market_movers:top_gainers_losers"

    cached_data = await redis_cache.get(cache_key)
    if cached_data is not None:
        logger.info("Market movers cache hit")
        return cached_data  # type: ignore[no-any-return]

    logger.info("Market movers cache miss, trying yfinance first")

    data: dict[str, Any] | None = None
    yf_error: str | None = None
    try:
        data = await yfinance_movers.get_market_movers()
    except Exception as e:
        yf_error = str(e)
        logger.warning("yfinance market movers failed, falling back to Alpha Vantage", error=yf_error)

    if data is None:
        try:
            data = await service.get_top_gainers_losers()
            data.setdefault("source", "alpha_vantage")
        except Exception as e:
            logger.error(
                "Both yfinance and Alpha Vantage market movers failed",
                yfinance_error=yf_error,
                alpha_vantage_error=str(e),
            )
            raise HTTPException(
                status_code=503,
                detail="Market movers temporarily unavailable (upstream sources failed)",
            ) from e

    ttl = get_tool_ttl("TOP_GAINERS_LOSERS")
    await redis_cache.set(cache_key, data, ttl_seconds=ttl)

    logger.info(
        "Market movers fetched and cached",
        source=data.get("source"),
        gainers_count=len(data.get("top_gainers", [])),
        losers_count=len(data.get("top_losers", [])),
        active_count=len(data.get("most_actively_traded", [])),
        ttl_seconds=ttl,
    )
    return data
