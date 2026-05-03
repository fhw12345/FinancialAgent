"""
Price and quote data endpoints.

Handles real-time quotes and historical price data using Alpha Vantage API.
"""

from datetime import datetime
from functools import lru_cache

import pandas as pd
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ...core.config import Settings
from ...core.utils import get_valid_frontend_intervals
from ...database.redis import RedisCache
from ...services.alphavantage_market_data import (
    AlphaVantageMarketDataService,
    get_market_session,
    validate_date_range,
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


class PriceDataPoint(BaseModel):
    """Single price data point."""

    time: str = Field(
        ..., description="Timestamp (YYYY-MM-DD format for daily, ISO for intraday)"
    )
    open: float = Field(..., description="Opening price")
    high: float = Field(..., description="High price")
    low: float = Field(..., description="Low price")
    close: float = Field(..., description="Closing price")
    volume: int = Field(..., description="Trading volume")
    market_session: str | None = Field(
        None,
        description="Market session indicator for intraday data: pre (pre-market), regular (regular hours), post (post-market), closed (after hours/weekends)",
    )


class PriceDataResponse(BaseModel):
    """Price data response."""

    symbol: str = Field(..., description="Stock symbol")
    interval: str = Field(..., description="Data interval")
    data: list[PriceDataPoint] = Field(..., description="Price data points")
    last_updated: str = Field(..., description="Last updated timestamp")


class QuoteResponse(BaseModel):
    """Global quote response."""

    symbol: str = Field(..., description="Stock symbol")
    price: float = Field(..., description="Current/latest price")
    open: float = Field(..., description="Open price")
    high: float = Field(..., description="Day high")
    low: float = Field(..., description="Day low")
    volume: int = Field(..., description="Trading volume")
    latest_trading_day: str = Field(
        default="", description="Latest trading day (YYYY-MM-DD)"
    )
    previous_close: float = Field(..., description="Previous close price")
    change: float = Field(..., description="Price change")
    change_percent: str = Field(..., description="Price change percentage")
    next_open: str | None = Field(
        default=None, description="Next market open time (ISO format)"
    )
    next_close: str | None = Field(
        default=None, description="Next market close time (ISO format)"
    )
    timestamp: str = Field(..., description="Current timestamp (ISO format)")


@router.get("/price/{symbol}", response_model=PriceDataResponse)
async def get_price_data(
    symbol: str,
    service: AlphaVantageMarketDataService = Depends(get_market_service),
    redis_cache: RedisCache = Depends(get_redis),
    interval: str = Query(
        default="1d",
        description="Data interval: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo",
    ),
    period: str = Query(
        default="6mo",
        description="Data period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max",
    ),
    start_date: str | None = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end_date: str | None = Query(default=None, description="End date (YYYY-MM-DD)"),
) -> PriceDataResponse:
    """
    Get price data using Alpha Vantage with extended hours support.

    Supports multiple time intervals:
    - Intraday: 1m, 5m, 15m, 30m, 60m
    - Daily+: 1d, 1wk, 1mo

    Uses Alpha Vantage TIME_SERIES_INTRADAY with extended_hours=true for pre/post market data.
    """
    try:
        # Validate symbol
        symbol = symbol.upper().strip()
        if not symbol:
            raise ValueError("Symbol is required")

        # Validate interval
        valid_intervals = get_valid_frontend_intervals()
        if interval not in valid_intervals:
            raise ValueError(f"Invalid interval. Must be one of: {valid_intervals}")

        # Validate custom date range if provided
        if start_date or end_date:
            is_valid, error_msg = validate_date_range(start_date, end_date, interval)
            if not is_valid:
                raise ValueError(error_msg)

        logger.info(
            "Price data request",
            symbol=symbol,
            interval=interval,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )

        # Generate cache key
        cache_key = f"price:{symbol}:{interval}:{period}"
        if start_date or end_date:
            cache_key += f":{start_date or 'none'}:{end_date or 'none'}"

        # Check cache first
        cached_response = await redis_cache.get(cache_key)
        if cached_response is not None:
            logger.info(
                "Price data cache hit",
                symbol=symbol,
                interval=interval,
            )
            return PriceDataResponse(**cached_response)

        logger.info(
            "Price data cache miss, fetching from API",
            symbol=symbol,
            interval=interval,
        )

        # Fetch data using Alpha Vantage
        data = await service.get_price_bars(
            symbol=symbol,
            interval=interval,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )

        if data.empty:
            logger.warning("No price data available", symbol=symbol, period=period)
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"No data available for symbol {symbol}",
                    "suggestions": [],
                },
            )

        # Convert to response format
        price_points = []
        for index, row in data.iterrows():
            # Format time based on interval
            # Note: "1h" is an alias for "60m" but already in the intraday list
            if interval in ["1m", "5m", "15m", "30m", "60m", "1h"]:
                # Intraday: use full timestamp and add market session indicator
                time_str = index.strftime("%Y-%m-%dT%H:%M:%S")
                market_session = get_market_session(index)
            else:
                # Daily+: use date only, no market session indicator
                time_str = index.strftime("%Y-%m-%d")
                market_session = None

            price_point = PriceDataPoint(
                time=time_str,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
                market_session=market_session,
            )
            price_points.append(price_point)

        logger.info(
            "Price data fetched successfully",
            symbol=symbol,
            bars_count=len(price_points),
            interval=interval,
        )

        response = PriceDataResponse(
            symbol=symbol,
            interval=interval,
            data=price_points,
            last_updated=datetime.now().isoformat(),
        )

        # Cache with interval-appropriate TTL
        # 1m: 60s, 5m: 300s, 15m: 900s, 1h: 3600s, 1d+: 3600s
        ttl_map = {
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "60m": 3600,
            "1h": 3600,
            "1d": 3600,
            "1wk": 3600,
            "1mo": 3600,
        }
        ttl = ttl_map.get(interval, 3600)
        await redis_cache.set(cache_key, response.model_dump(), ttl_seconds=ttl)

        logger.info(
            "Price data cached",
            symbol=symbol,
            interval=interval,
            ttl_seconds=ttl,
        )

        return response

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(
            "Price data fetch failed",
            symbol=symbol,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch price data: {str(e)}"
        ) from e


@router.get("/quote/{symbol}")
async def get_quote(
    symbol: str,
    service: AlphaVantageMarketDataService = Depends(get_market_service),
    redis: RedisCache = Depends(get_redis),
) -> QuoteResponse:
    """
    Get real-time quote for a symbol using GLOBAL_QUOTE.

    Returns the latest price, volume, and change information.
    Note: Uses 15-minute delayed data with premium API key.
    """
    try:
        symbol = symbol.upper().strip()
        if not symbol:
            raise ValueError("Symbol is required")

        logger.info("Quote request", symbol=symbol)

        # Check cache first
        cache_key = f"quote:{symbol}"
        cached_data = await redis.get(cache_key)
        if cached_data:
            logger.info("Quote cache hit", symbol=symbol)
            return QuoteResponse(**cached_data)

        # Fetch from Alpha Vantage
        quote_data = await service.get_quote(symbol)

        response = QuoteResponse(
            symbol=quote_data.get("symbol", symbol),
            price=float(quote_data.get("price", 0)),
            open=float(quote_data.get("open", 0)),
            high=float(quote_data.get("high", 0)),
            low=float(quote_data.get("low", 0)),
            volume=int(quote_data.get("volume", 0)),
            latest_trading_day=quote_data.get("latest_trading_day", ""),
            previous_close=float(quote_data.get("previous_close", 0)),
            change=float(quote_data.get("change", 0)),
            change_percent=quote_data.get("change_percent", "0%"),
            timestamp=datetime.now().isoformat(),
        )

        # Cache for 60 seconds (quote data is frequently updated)
        await redis.set(cache_key, response.model_dump(), ttl_seconds=60)
        logger.info("Quote cached", symbol=symbol, ttl_seconds=60)

        return response

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Quote fetch failed", symbol=symbol, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch quote: {str(e)}"
        ) from e
