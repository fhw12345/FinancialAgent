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
from ...models.symbol_resolution import SymbolCandidate
from ...services.alphavantage_market_data import AlphaVantageMarketDataService
from ...services.symbol_search_service import (
    SymbolSearchService,
    search_local_symbols,
)
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


def get_symbol_search_service(
    service: AlphaVantageMarketDataService = Depends(get_market_service),
) -> SymbolSearchService:
    """Create the shared symbol-search service for the API request."""
    return SymbolSearchService(service)


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
    search_service: SymbolSearchService = Depends(get_symbol_search_service),
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
    try:
        query = q.strip()
        if len(query) < 1:
            raise ValueError("Search query must be at least 1 character")

        logger.info("Symbol search started", query=query)

        candidates = await search_service.search(query, limit=10)
        results = [_to_api_result(candidate) for candidate in candidates]

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
    Search local CSVs for matching symbols.

    Two sources, merged with priority:
      - sector_universe.csv (515 curated large-caps with sector + market_cap data)
      - tickers_directory.csv (~6800 actively listed US tickers, narrow schema)

    The directory provides wide coverage so tickers like "BE" (Bloom Energy)
    that aren't in the curated set still surface; sector_universe still wins
    on exchange field richness for the symbols it does cover.

    Ranking:
      1. Exact symbol match (confidence 1.0)
      2. Symbol prefix match (0.9)
      3. Name prefix match (0.8)
      4. Substring match in symbol or name (0.6)

    Same symbol appearing in both sources is de-duped (sector_universe wins
    because it has type + sector data the directory lacks).
    """
    return [
        _to_api_result(candidate) for candidate in search_local_symbols(query, limit)
    ]


def _to_api_result(candidate: SymbolCandidate) -> SymbolSearchResult:
    return SymbolSearchResult(**candidate.model_dump())


@router.get("/info/{symbol}")
async def get_symbol_info(
    symbol: str,
    service: AlphaVantageMarketDataService = Depends(get_market_service),
) -> dict[str, str]:
    """
    Get basic symbol information from the local market-data service.
    """
    try:
        symbol = symbol.upper().strip()

        matches = await service.search_symbols(symbol, limit=10)
        matching_asset = next(
            (item for item in matches if item.get("symbol", "").upper() == symbol),
            None,
        )

        if not matching_asset:
            raise ValueError(f"Symbol {symbol} not found")

        return {
            "symbol": matching_asset["symbol"],
            "name": matching_asset.get("name", ""),
            "exchange": matching_asset.get("exchange", ""),
            "type": matching_asset.get("type", "Equity"),
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
        logger.warning(
            "yfinance market movers failed, falling back to Alpha Vantage",
            error=yf_error,
        )

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
