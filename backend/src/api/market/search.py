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
    Search for stock symbols using Alpaca assets with fuzzy matching.

    Supports queries like 'apple', 'microsoft', 'AAPL', etc.
    Uses client-side fuzzy matching on Alpaca's asset list.
    """
    try:
        # Clean query
        query = q.strip()
        if len(query) < 1:
            raise ValueError("Search query must be at least 1 character")

        logger.info("Symbol search started", query=query)

        # Use hybrid service
        raw_results = await service.search_symbols(query, limit=10)

        # Convert to response model
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

    Returns:
    - top_gainers: Top 20 stocks with highest price increase (% and $)
    - top_losers: Top 20 stocks with largest price decrease (% and $)
    - most_actively_traded: Top 20 stocks by trading volume

    Each entry includes: ticker, price, change_amount, change_percentage, volume

    Cache Duration: 30 minutes (configured in cache_utils.py)
    - Market movers change throughout trading day but not every second
    - 30-min refresh balances freshness vs API efficiency
    - Reduces Alpha Vantage API calls by 12x per 6-hour period
    """
    try:
        logger.info("Market movers request")

        # Generate cache key
        cache_key = "market_movers:top_gainers_losers"

        # Check cache first
        cached_data = await redis_cache.get(cache_key)
        if cached_data is not None:
            logger.info("Market movers cache hit")
            return cached_data  # type: ignore[no-any-return]

        logger.info("Market movers cache miss, fetching from API")

        # Fetch from Alpha Vantage API
        data = await service.get_top_gainers_losers()

        # Cache with 30-minute TTL (configured in TOOL_TTL_MAP)
        ttl = get_tool_ttl("TOP_GAINERS_LOSERS")  # Returns 1800 seconds (30 minutes)
        await redis_cache.set(cache_key, data, ttl_seconds=ttl)

        logger.info(
            "Market movers fetched and cached",
            gainers_count=len(data.get("top_gainers", [])),
            losers_count=len(data.get("top_losers", [])),
            active_count=len(data.get("most_actively_traded", [])),
            ttl_seconds=ttl,
        )

        return data

    except Exception as e:
        logger.error("Market movers fetch failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch market movers: {str(e)}"
        ) from e
