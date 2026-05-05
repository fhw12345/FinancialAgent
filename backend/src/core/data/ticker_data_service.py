"""
Centralized ticker data service with intelligent caching.

This service eliminates redundant API calls by providing shared ticker data
to all analyzers through a unified caching layer.

MIGRATION: Replaced yfinance with Alpaca for FREE paper trading data.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from ...database.redis import RedisCache
from ...services.alphavantage_market_data import AlphaVantageMarketDataService
from ..utils.date_utils import DateUtils

logger = structlog.get_logger()


class TickerDataService:
    """
    Centralized service for fetching and caching raw ticker data.

    Provides unified interface to ticker data with intelligent caching
    to prevent redundant API calls across analyzers.

    MIGRATION: Now uses Alpaca instead of yfinance for FREE real-time data.
    """

    def __init__(
        self,
        redis_cache: RedisCache,
        alpaca_data_service: Any | None = None,
        alpha_vantage_service: AlphaVantageMarketDataService | None = None,
    ):
        """
        Initialize ticker data service.

        Args:
            redis_cache: Redis cache instance for data storage
            alpaca_data_service: Alpaca data service for market data (optional)
            alpha_vantage_service: Alpha Vantage service for fallback (optional)
        """
        self.redis_cache = redis_cache
        self.alpaca_data_service = alpaca_data_service
        self.alpha_vantage_service = alpha_vantage_service
        self.default_ttl = 1800  # 30 minutes default TTL

    async def get_ticker_history(
        self,
        symbol: str,
        interval: str = "1d",
        period: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        """
        Get ticker history with unified caching.

        Args:
            symbol: Stock symbol (e.g., "AAPL")
            interval: Data interval ("1m", "1h", "1d", "1wk", "1mo")
            period: Relative period ("1d", "5d", "1mo", "6mo", "1y", etc.)
                   OR
            start_date: Start date ("YYYY-MM-DD") - requires end_date
            end_date: End date ("YYYY-MM-DD") - requires start_date

        Returns:
            DataFrame with OHLCV data

        Raises:
            ValueError: If both period and date range are provided or parameters are invalid
        """
        logger.info(
            "Ticker data request",
            symbol=symbol,
            interval=interval,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )

        # Validate parameters
        self._validate_parameters(period, start_date, end_date)

        # Normalize to start/end dates for consistent caching
        normalized_start, normalized_end = self._normalize_to_date_range(
            period, start_date, end_date
        )

        # Generate cache key
        cache_key = self._generate_cache_key(
            symbol, normalized_start, normalized_end, interval
        )

        logger.info(
            "Normalized ticker request",
            symbol=symbol,
            cache_key=cache_key,
            start_date=normalized_start,
            end_date=normalized_end,
        )

        # Check cache first
        cached_data = await self.redis_cache.get(cache_key)
        if cached_data is not None:
            logger.info("Cache hit", cache_key=cache_key)
            # Deserialize DataFrame from cached dict
            df = pd.DataFrame(cached_data)
            # Convert string index back to DatetimeIndex (was converted to str for Redis)
            df.index = pd.to_datetime(df.index)
            return df

        logger.info("Cache miss", cache_key=cache_key)

        # Fetch from Alpaca
        df = await self._fetch_from_alpaca(
            symbol, interval, normalized_start, normalized_end
        )

        # Cache the result if non-empty
        if not df.empty:
            ttl = self._calculate_ttl(interval, normalized_start, normalized_end)
            # Serialize DataFrame to dict for Redis storage
            # Convert Timestamp index to strings (Redis only accepts basic types)
            df_copy = df.copy()
            df_copy.index = df_copy.index.astype(str)
            await self.redis_cache.set(cache_key, df_copy.to_dict(), ttl_seconds=ttl)
            logger.info(
                "Cached ticker data", cache_key=cache_key, ttl=ttl, rows=len(df)
            )

        return df

    async def get_current_price(self, symbol: str) -> float | None:
        """
        Get current/latest price for a symbol using Alpaca.

        Caches prices for 30 seconds to reduce API calls for real-time data.

        Args:
            symbol: Stock symbol (e.g., "AAPL")

        Returns:
            Current price as float, or None if unavailable
        """
        # Check cache first (30 second TTL for real-time prices)
        cache_key = f"current_price:{symbol}"
        cached_price = await self.redis_cache.get(cache_key)
        if cached_price is not None:
            logger.debug(
                "Cache hit for current price", symbol=symbol, price=cached_price
            )
            return float(cached_price)

        try:
            price = None

            # If Alpaca is available, use it for real-time price
            if self.alpaca_data_service:
                logger.info("Fetching current price from Alpaca", symbol=symbol)
                price = await self.alpaca_data_service.get_latest_price(symbol)
                if price and price > 0:
                    logger.info("Got price from Alpaca", symbol=symbol, price=price)
                else:
                    logger.warning(
                        "Invalid price from Alpaca",
                        symbol=symbol,
                        price=price,
                    )
                    price = None

            # Cache the price if we got a valid one (30 second TTL)
            if price and price > 0:
                await self.redis_cache.set(cache_key, price, ttl_seconds=30)
                return price
            else:
                return None

        except Exception as e:
            logger.error(
                "Error fetching current price",
                symbol=symbol,
                error=str(e),
                exc_info=True,
            )
            return None

    def _validate_parameters(
        self, period: str | None, start_date: str | None, end_date: str | None
    ) -> None:
        """Validate input parameters."""
        # Cannot specify both period and date range
        if period and (start_date or end_date):
            raise ValueError(
                "Cannot specify both 'period' and date range (start_date/end_date)"
            )

        # Date range requires both start and end
        if (start_date and not end_date) or (end_date and not start_date):
            raise ValueError(
                "Both start_date and end_date are required for date range queries"
            )

        # Validate date format and logic if provided
        if start_date and end_date:
            DateUtils.validate_date_range(start_date, end_date)

    def _normalize_to_date_range(
        self, period: str | None, start_date: str | None, end_date: str | None
    ) -> tuple[str, str]:
        """
        Normalize all requests to start/end date format for consistent caching.

        Returns:
            Tuple of (start_date, end_date) as YYYY-MM-DD strings
        """
        if period:
            # Convert period to date range
            return DateUtils.period_to_date_range(period)
        elif start_date and end_date:
            # Already in date range format
            return start_date, end_date
        else:
            # Default to 6mo if nothing specified
            return DateUtils.period_to_date_range("6mo")

    def _generate_cache_key(
        self, symbol: str, start_date: str, end_date: str, interval: str
    ) -> str:
        """
        Generate unified cache key using normalized dates.

        Args:
            symbol: Stock symbol (normalized to uppercase)
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            interval: Data interval

        Returns:
            Cache key string for Redis storage
        """
        normalized_symbol = symbol.upper().strip()
        return f"ticker_data:{normalized_symbol}:{start_date}:{end_date}:{interval}"

    def _calculate_ttl(self, interval: str, start_date: str, end_date: str) -> int:
        """
        Calculate appropriate TTL based on data characteristics.

        Args:
            interval: Data interval
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            TTL in seconds
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo

        # Base TTL by interval
        base_ttl_map = {
            "1m": 60,  # 1 minute data - cache for 1 minute
            "5m": 300,  # 5 minute data - cache for 5 minutes
            "1h": 1800,  # 1 hour data - cache for 30 minutes
            "1d": 3600,  # Daily data - cache for 1 hour
            "1wk": 7200,  # Weekly data - cache for 2 hours
            "1mo": 14400,  # Monthly data - cache for 4 hours
        }

        base_ttl = base_ttl_map.get(interval, self.default_ttl)

        # Historical data can be cached longer
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().strftime("%Y-%m-%d")
        is_current_data = end_date == today

        if not is_current_data:
            # Historical data cache 8x longer
            base_ttl *= 8

        return base_ttl

    async def _fetch_from_alpaca(
        self, symbol: str, interval: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """
        Fetch ticker data from Alpaca Data API (with yfinance fallback).

        MIGRATION: Replaced yfinance with Alpaca for:
        - FREE real-time data (no 15-minute delay)
        - Extended hours support (pre/post-market)
        - Consistent with trading service

        Args:
            symbol: Stock symbol
            interval: Data interval
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            DataFrame with OHLCV data, or empty DataFrame on error
        """
        try:
            # Try Alpaca first if available
            if self.alpaca_data_service:
                logger.info(
                    "Fetching from Alpaca",
                    symbol=symbol,
                    interval=interval,
                    start=start_date,
                    end=end_date,
                )

                # Fetch data using Alpaca
                df = await self.alpaca_data_service.get_bars(
                    symbol=symbol,
                    interval=interval,
                    start_date=start_date,
                    end_date=end_date,
                )

                if df.empty:
                    logger.warning(
                        "No data returned from Alpaca",
                        symbol=symbol,
                        interval=interval,
                        start=start_date,
                        end=end_date,
                    )
                else:
                    logger.info(
                        "Successfully fetched from Alpaca",
                        symbol=symbol,
                        rows=len(df),
                        columns=list(df.columns),
                    )
                    return df

            # No data available from Alpaca
            logger.warning("No data from Alpaca", symbol=symbol)
            return pd.DataFrame()

        except Exception as e:
            logger.error(
                "Error fetching ticker data",
                symbol=symbol,
                interval=interval,
                error=str(e),
                exc_info=True,
            )
            return pd.DataFrame()
