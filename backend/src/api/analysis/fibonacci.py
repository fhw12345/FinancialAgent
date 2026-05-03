"""
Fibonacci retracement analysis endpoint.

Provides Fibonacci retracement level calculations for technical analysis,
identifying potential support and resistance levels based on historical price data.
"""

import time
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException

from ...core.config import get_settings
from ...core.financial_analysis import FibonacciAnalyzer
from ...database.redis import RedisCache
from ...services.data_manager import DataManager
from ..health import get_redis
from ..models import FibonacciAnalysisRequest, FibonacciAnalysisResponse
from .shared import get_data_manager, validate_date_range

logger = structlog.get_logger()
router = APIRouter()


@router.post("/fibonacci", response_model=FibonacciAnalysisResponse)
async def fibonacci_analysis(
    request: FibonacciAnalysisRequest,
    redis_cache: RedisCache = Depends(get_redis),
    data_manager: DataManager = Depends(get_data_manager),
) -> FibonacciAnalysisResponse:
    """
    Perform Fibonacci retracement analysis on a stock symbol.

    This endpoint analyzes market structure and calculates Fibonacci retracement levels
    for the specified stock symbol and date range.
    """
    request_start_time = time.time()

    # Log incoming request details
    logger.info(
        "Fibonacci analysis request received",
        symbol=request.symbol,
        start_date=request.start_date,
        end_date=request.end_date,
        timeframe=request.timeframe,
        include_chart=request.include_chart,
    )

    try:
        # Validate date range first
        validate_date_range(request.start_date, request.end_date)

        # Intraday intervals (1m, 60m) are not supported for Fibonacci analysis
        # Reason: Insufficient historical data (Alpha Vantage compact mode ~100 bars)
        # and excessive noise in intraday swings make analysis unreliable
        if request.timeframe in ["1m", "60m", "60min", "1h"]:
            logger.error(
                "Fibonacci analysis not supported for intraday intervals",
                symbol=request.symbol,
                timeframe=request.timeframe,
            )
            raise ValueError(
                f"Fibonacci analysis is not available for {request.timeframe} interval. "
                f"Please use daily (1d), weekly (1w), or monthly (1mo) intervals for reliable analysis."
            )

        # Require both start and end dates for Fibonacci analysis
        if not request.start_date or not request.end_date:
            logger.error(
                "Fibonacci analysis request failed - missing date range",
                symbol=request.symbol,
                timeframe=request.timeframe,
                start_date=request.start_date,
                end_date=request.end_date,
            )
            raise ValueError(
                f"Both start_date and end_date are required for {request.timeframe} Fibonacci analysis"
            )

        # Check cache first
        cache_start_time = time.time()
        cache_key = f"fibonacci:{request.symbol}:{request.start_date}:{request.end_date}:{request.timeframe}"

        logger.info(
            "Checking cache for Fibonacci analysis",
            cache_key=cache_key,
            symbol=request.symbol,
        )

        cached_result = await redis_cache.get(cache_key)
        cache_check_duration = time.time() - cache_start_time

        if cached_result:
            total_duration = time.time() - request_start_time
            logger.info(
                "Fibonacci analysis cache HIT - returning cached result",
                symbol=request.symbol,
                cache_key=cache_key,
                cache_check_duration_ms=round(cache_check_duration * 1000, 2),
                total_duration_ms=round(total_duration * 1000, 2),
            )
            return FibonacciAnalysisResponse.model_validate(cached_result)

        logger.info(
            "Fibonacci analysis cache MISS - proceeding with calculation",
            symbol=request.symbol,
            cache_key=cache_key,
            cache_check_duration_ms=round(cache_check_duration * 1000, 2),
        )

        # Perform analysis with timeframe parameter
        analysis_start_time = time.time()
        logger.info(
            "Starting Fibonacci analysis calculation",
            symbol=request.symbol,
            timeframe=request.timeframe,
            date_range_days=(
                datetime.strptime(request.end_date, "%Y-%m-%d")
                - datetime.strptime(request.start_date, "%Y-%m-%d")
            ).days,
        )

        # Use singleton DataManager for cached OHLCV access
        analyzer = FibonacciAnalyzer(data_manager)
        result = await analyzer.analyze(
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            timeframe=request.timeframe,
        )

        analysis_duration = time.time() - analysis_start_time
        logger.info(
            "Fibonacci analysis calculation completed",
            symbol=result.symbol,
            timeframe=result.timeframe,
            confidence_score=result.confidence_score,
            fibonacci_levels_count=len(result.fibonacci_levels),
            analysis_duration_ms=round(analysis_duration * 1000, 2),
        )

        # Cache for 30 min - Fibonacci levels based on recent price action
        # Date-based cache key ensures data refreshes
        settings = get_settings()
        cache_store_start_time = time.time()
        await redis_cache.set(
            cache_key, result.model_dump(), ttl_seconds=settings.cache_ttl_analysis
        )
        cache_store_duration = time.time() - cache_store_start_time

        total_duration = time.time() - request_start_time
        logger.info(
            "Fibonacci analysis request completed successfully",
            symbol=result.symbol,
            cache_key=cache_key,
            cache_stored=True,
            cache_ttl_seconds=300,
            cache_store_duration_ms=round(cache_store_duration * 1000, 2),
            analysis_duration_ms=round(analysis_duration * 1000, 2),
            total_duration_ms=round(total_duration * 1000, 2),
        )

        return result

    except ValueError as e:
        total_duration = time.time() - request_start_time
        logger.error(
            "Fibonacci analysis request failed - invalid input",
            symbol=request.symbol,
            error=str(e),
            total_duration_ms=round(total_duration * 1000, 2),
        )
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}") from e
    except Exception as e:
        total_duration = time.time() - request_start_time
        logger.error(
            "Fibonacci analysis request failed - unexpected error",
            symbol=request.symbol,
            error=str(e),
            error_type=type(e).__name__,
            total_duration_ms=round(total_duration * 1000, 2),
        )
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}") from e
