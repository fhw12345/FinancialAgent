"""
Macro sentiment analysis endpoint.

Provides macro-level market sentiment analysis using economic indicators,
market indices, and sector performance to gauge overall market conditions.
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException

from ...core.config import get_settings
from ...core.financial_analysis import MacroAnalyzer
from ...database.redis import RedisCache
from ...services.alphavantage_market_data import AlphaVantageMarketDataService
from ..health import get_redis
from ..models import MacroAnalysisRequest, MacroSentimentResponse
from .shared import get_market_service

logger = structlog.get_logger()
router = APIRouter()


@router.post("/macro", response_model=MacroSentimentResponse)
async def macro_sentiment_analysis(
    request: MacroAnalysisRequest,
    redis_cache: RedisCache = Depends(get_redis),
    market_service: AlphaVantageMarketDataService = Depends(get_market_service),
) -> MacroSentimentResponse:
    """
    Analyze macro market sentiment using economic indicators from AlphaVantage.

    Provides fear/greed analysis and overall market outlook based on economic data.
    """
    try:
        # Check cache first (shorter cache time for macro data)
        # Include date to prevent serving stale data from previous day
        from datetime import UTC, datetime

        current_date = datetime.now(UTC).strftime("%Y-%m-%d")
        cache_key = (
            f"macro:{current_date}:{request.include_sectors}:{request.include_indices}"
        )
        cached_result = await redis_cache.get(cache_key)
        if cached_result:
            return MacroSentimentResponse.model_validate(cached_result)

        # Perform analysis with market_service dependency
        analyzer = MacroAnalyzer(market_service)
        result = await analyzer.analyze(
            include_sectors=request.include_sectors,
            include_indices=request.include_indices,
        )

        # Cache for 30 min - Macro sentiment provides intraday market overview
        # Date-based cache key ensures fresh data each day
        settings = get_settings()
        await redis_cache.set(
            cache_key, result.model_dump(), ttl_seconds=settings.cache_ttl_analysis
        )

        return result

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Macro analysis failed: {str(e)}"
        ) from e
