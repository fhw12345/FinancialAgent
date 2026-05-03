"""
Technical analysis endpoints.

Provides technical analysis indicators including Stochastic Oscillator,
chart generation, and other technical analysis tools for market timing.
"""

import time
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException

from ...core.config import get_settings
from ...core.financial_analysis import StochasticAnalyzer
from ...database.redis import RedisCache
from ...services.data_manager import DataManager
from ..health import get_redis
from ..models import (
    ChartGenerationResponse,
    ChartRequest,
    StochasticAnalysisRequest,
    StochasticAnalysisResponse,
)
from .shared import get_data_manager, validate_date_range

logger = structlog.get_logger()
router = APIRouter()


@router.post("/stochastic", response_model=StochasticAnalysisResponse)
async def stochastic_analysis(
    request: StochasticAnalysisRequest,
    redis_cache: RedisCache = Depends(get_redis),
    data_manager: DataManager = Depends(get_data_manager),
) -> StochasticAnalysisResponse:
    """
    Perform Stochastic Oscillator technical analysis on a stock symbol.

    Analyzes overbought/oversold conditions, crossover signals, and potential
    reversals using the Stochastic Oscillator indicator.
    """
    request_start_time = time.time()

    # Log incoming request details
    logger.info(
        "Stochastic analysis request received",
        symbol=request.symbol,
        start_date=request.start_date,
        end_date=request.end_date,
        timeframe=request.timeframe,
        k_period=request.k_period,
        d_period=request.d_period,
    )

    try:
        # Validate date range if provided
        validate_date_range(request.start_date, request.end_date)

        # Intraday intervals (1m, 60m) are not supported for Stochastic analysis
        # Reason: Insufficient historical data and excessive noise
        if request.timeframe in ["1m", "60m", "60min", "1h"]:
            logger.error(
                "Stochastic analysis not supported for intraday intervals",
                symbol=request.symbol,
                timeframe=request.timeframe,
            )
            raise ValueError(
                f"Stochastic analysis is not available for {request.timeframe} interval. "
                f"Please use daily (1d), weekly (1w), or monthly (1mo) intervals for reliable analysis."
            )

        # Check cache first
        cache_start_time = time.time()
        cache_key = f"stochastic:{request.symbol}:{request.start_date}:{request.end_date}:{request.timeframe}:{request.k_period}:{request.d_period}"

        logger.info(
            "Checking cache for Stochastic analysis",
            cache_key=cache_key,
            symbol=request.symbol,
        )

        cached_result = await redis_cache.get(cache_key)
        cache_check_duration = time.time() - cache_start_time

        if cached_result:
            total_duration = time.time() - request_start_time
            logger.info(
                "Stochastic analysis cache HIT - returning cached result",
                symbol=request.symbol,
                cache_key=cache_key,
                cache_check_duration_ms=round(cache_check_duration * 1000, 2),
                total_duration_ms=round(total_duration * 1000, 2),
            )
            return StochasticAnalysisResponse.model_validate(cached_result)

        logger.info(
            "Stochastic analysis cache MISS - proceeding with calculation",
            symbol=request.symbol,
            cache_key=cache_key,
            cache_check_duration_ms=round(cache_check_duration * 1000, 2),
        )

        # Perform analysis
        analysis_start_time = time.time()
        logger.info(
            "Starting Stochastic analysis calculation",
            symbol=request.symbol,
            timeframe=request.timeframe,
            k_period=request.k_period,
            d_period=request.d_period,
        )

        # Use singleton DataManager for cached OHLCV access
        analyzer = StochasticAnalyzer(data_manager)

        result = await analyzer.analyze(
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            timeframe=request.timeframe,
            k_period=request.k_period,
            d_period=request.d_period,
        )

        analysis_duration = time.time() - analysis_start_time
        logger.info(
            "Stochastic analysis calculation completed",
            symbol=result.symbol,
            timeframe=result.timeframe,
            current_signal=result.current_signal,
            k_value=result.current_k,
            d_value=result.current_d,
            analysis_duration_ms=round(analysis_duration * 1000, 2),
        )

        # Cache for 30 min - Stochastic oscillator needs regular updates
        # Date-based cache key ensures data refreshes
        settings = get_settings()
        cache_store_start_time = time.time()
        await redis_cache.set(
            cache_key, result.model_dump(), ttl_seconds=settings.cache_ttl_analysis
        )
        cache_store_duration = time.time() - cache_store_start_time

        total_duration = time.time() - request_start_time
        logger.info(
            "Stochastic analysis request completed successfully",
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
            "Stochastic analysis request failed - invalid input",
            symbol=request.symbol,
            error=str(e),
            total_duration_ms=round(total_duration * 1000, 2),
        )
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}") from e
    except Exception as e:
        total_duration = time.time() - request_start_time
        logger.error(
            "Stochastic analysis request failed - unexpected error",
            symbol=request.symbol,
            error=str(e),
            error_type=type(e).__name__,
            total_duration_ms=round(total_duration * 1000, 2),
        )
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}") from e


@router.post("/chart", response_model=ChartGenerationResponse)
async def generate_chart(
    request: ChartRequest,
    redis_cache: RedisCache = Depends(get_redis),
) -> ChartGenerationResponse:
    """
    Generate a financial chart for the specified symbol and type.

    Supports various chart types including price, Fibonacci, and volume charts.
    Chart generation happens asynchronously for better performance.
    """
    try:
        # Validate date range first
        validate_date_range(request.start_date, request.end_date)

        # For now, return chart data structure that frontend can use
        # Chart image generation will be implemented in next phase
        generation_date = datetime.now().isoformat()
        chart_data: dict[str, Any] = {
            "symbol": request.symbol,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "chart_type": request.chart_type,
            "includes_indicators": request.include_indicators,
            "data_points": [],  # Will be populated with actual chart data
            "generated_at": generation_date,
        }

        result = ChartGenerationResponse(
            symbol=request.symbol,
            chart_type=request.chart_type,
            chart_url=None,  # Will be set when image generation is implemented
            chart_data=chart_data,
            generation_date=generation_date,
            success=True,
            error_message=None,
        )

        # Chart data returned for frontend use

        return result

    except Exception as e:
        return ChartGenerationResponse(
            symbol=request.symbol,
            chart_type=request.chart_type,
            chart_url=None,
            chart_data={},
            generation_date=datetime.now().isoformat(),
            success=False,
            error_message=str(e),
        )
