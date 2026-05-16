"""
Extended price bars methods (extended intraday and unified get_price_bars).
"""

import asyncio
from datetime import datetime, timedelta
from io import StringIO
from typing import Any

import pandas as pd
import structlog

from . import yfinance_bars
from .base import AlphaVantageBase

logger = structlog.get_logger()


class BarsExtendedMixin(AlphaVantageBase):
    """Methods for extended price bars and unified price bar fetching."""

    async def get_intraday_bars_extended(
        self,
        symbol: str,
        interval: str = "1min",
        months: int = 3,
    ) -> pd.DataFrame:
        """
        Get extended intraday bars using TIME_SERIES_INTRADAY_EXTENDED (Premium feature).

        This endpoint provides up to 2 years of historical intraday data by fetching
        monthly slices. Each slice represents one month of data.

        Args:
            symbol: Stock symbol
            interval: 1min, 5min, 15min, 30min, 60min
            months: Number of recent months to fetch (1-24, default 3)

        Returns:
            DataFrame with Open, High, Low, Close, Volume columns

        Note:
            - Requires Premium API key
            - Each month is fetched as a separate "slice" (year1month1, year1month2, etc.)
            - year1month1 = most recent month, year2month1 = 13-24 months ago
            - Extended hours (pre/post market) included by default
        """
        try:
            if months < 1 or months > 24:
                raise ValueError("months must be between 1 and 24")

            # Prepare all API requests concurrently for better performance
            async def fetch_slice(
                month_offset: int,
            ) -> tuple[str, Any | None]:
                """Fetch a single month slice."""
                year = ((month_offset - 1) // 12) + 1
                month = ((month_offset - 1) % 12) + 1
                slice_name = f"year{year}month{month}"

                logger.info(
                    "Fetching extended intraday slice",
                    symbol=symbol,
                    interval=interval,
                    slice=slice_name,
                    month_offset=month_offset,
                )

                try:
                    response = await self.client.get(
                        self.base_url,
                        params={
                            "function": "TIME_SERIES_INTRADAY_EXTENDED",
                            "symbol": symbol,
                            "interval": interval,
                            "slice": slice_name,
                            "adjusted": "false",  # Raw prices
                            "apikey": self.api_key,
                        },
                    )
                    return slice_name, response
                except Exception as e:
                    logger.warning(
                        "Extended intraday slice fetch exception",
                        symbol=symbol,
                        slice=slice_name,
                        error=str(e),
                    )
                    return slice_name, None

            # Fetch all slices concurrently (3x faster for 3 months)
            tasks = [fetch_slice(i) for i in range(1, months + 1)]
            results = await asyncio.gather(*tasks)

            # Process all responses and parse CSV using pandas
            all_dataframes = []
            for slice_name, response in results:
                if response is None or response.status_code != 200:
                    if response is not None:
                        sanitized_text = self._sanitize_text(response.text)
                        logger.warning(
                            "Extended intraday slice fetch failed",
                            symbol=symbol,
                            slice=slice_name,
                            status=response.status_code,
                            error=sanitized_text,
                        )
                    continue

                # Check for API error messages before parsing
                response_text = response.text.strip()
                if (
                    not response_text
                    or "Error" in response_text
                    or "please see" in response_text
                ):
                    logger.warning(
                        "API error or no data in extended intraday slice",
                        symbol=symbol,
                        slice=slice_name,
                        response_preview=(
                            response_text[:200] if response_text else "empty"
                        ),
                    )
                    continue

                # Parse CSV using pandas (2-3x faster than manual parsing)
                try:
                    df_slice = pd.read_csv(
                        StringIO(response_text),
                        parse_dates=[0],  # First column is timestamp
                        index_col=0,  # Use timestamp as index
                        names=["timestamp", "Open", "High", "Low", "Close", "Volume"],
                        dtype={
                            "Open": float,
                            "High": float,
                            "Low": float,
                            "Close": float,
                            "Volume": int,
                        },
                        on_bad_lines="skip",  # Skip malformed lines
                    )

                    if not df_slice.empty:
                        all_dataframes.append(df_slice)
                    else:
                        logger.warning(
                            "No data in extended intraday slice",
                            symbol=symbol,
                            slice=slice_name,
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to parse CSV for slice",
                        symbol=symbol,
                        slice=slice_name,
                        error=str(e),
                    )

            if not all_dataframes:
                error_msg = (
                    f"No extended intraday data retrieved for {symbol}. "
                    f"API Note: TIME_SERIES_INTRADAY_EXTENDED has been deprecated and merged into TIME_SERIES_INTRADAY."
                )
                logger.error(
                    "Extended endpoint failed - API deprecated",
                    symbol=symbol,
                    interval=interval,
                    months_requested=months,
                )
                raise ValueError(error_msg)

            # Combine all dataframes efficiently
            df = pd.concat(all_dataframes, axis=0)
            df.sort_index(inplace=True)  # Ensure chronological order

            # Remove duplicates (in case of overlapping slices)
            df = df[~df.index.duplicated(keep="first")]

            # Alpha Vantage returns intraday timestamps in US Eastern Time
            # Localize naive timestamps to ET for proper session detection
            if not df.empty and df.index.tz is None:
                df.index = df.index.tz_localize("America/New_York")

            logger.info(
                "Extended intraday bars fetched",
                symbol=symbol,
                interval=interval,
                bars_count=len(df),
                months_fetched=months,
                date_range=(
                    f"{df.index.min()} to {df.index.max()}" if not df.empty else "empty"
                ),
            )

            return df

        except Exception as e:
            logger.error(
                "Extended intraday bars fetch failed",
                symbol=symbol,
                interval=interval,
                error=str(e),
            )
            raise

    async def get_price_bars(
        self,
        symbol: str,
        interval: str = "1d",
        period: str = "6mo",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        """
        Unified method to get price bars for any interval/period.

        Args:
            symbol: Stock symbol
            interval: 1m, 5m, 15m, 30m, 60m, 1d, 1wk, 1mo
            period: Relative period (1d, 5d, 1mo, 6mo, 1y, etc.) - ignored if dates provided
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            DataFrame with Open, High, Low, Close, Volume columns
        """
        # yfinance is the primary source — AV's free tier no longer serves
        # most chart endpoints (returns "Information" upsell payload). AV is
        # used only as a fallback when yfinance fails AND a key is configured.
        frontend_to_granularity = {
            "1m": "1min",
            "1min": "1min",
            "5m": "5min",
            "5min": "5min",
            "15m": "15min",
            "15min": "15min",
            "30m": "30min",
            "30min": "30min",
            "60m": "60min",
            "60min": "60min",
            "1h": "60min",
            "1d": "daily",
            "day": "daily",
            "1w": "weekly",
            "1wk": "weekly",
            "week": "weekly",
            "1mo": "monthly",
            "1M": "monthly",
            "month": "monthly",
        }
        granularity = frontend_to_granularity.get(interval)
        if granularity:
            outputsize = (
                "full"
                if (start_date and end_date)
                or interval in ("1d", "1w", "1wk", "1mo", "1M")
                else "compact"
            )
            try:
                df_yf = await yfinance_bars.get_bars(symbol, granularity, outputsize)
                logger.info(
                    "Price bars via yfinance",
                    symbol=symbol,
                    interval=interval,
                    granularity=granularity,
                    bars_count=len(df_yf),
                )
                return self._postprocess_price_bars(
                    df_yf, symbol, interval, start_date, end_date
                )
            except Exception as yf_err:
                if not self.api_key:
                    logger.error(
                        "yfinance bars failed (no AV fallback)",
                        symbol=symbol,
                        interval=interval,
                        error=str(yf_err),
                    )
                    raise
                logger.warning(
                    "yfinance bars failed, falling back to Alpha Vantage",
                    symbol=symbol,
                    interval=interval,
                    error=str(yf_err),
                )

        try:
            # Map intervals to Alpha Vantage format
            if interval in ["1m", "5m", "15m", "30m", "60m", "60min", "1h"]:
                # Map to Alpha Vantage interval format
                if interval in ["1h", "60m"]:
                    av_interval = "60min"
                else:
                    av_interval = interval.replace("m", "min")

                # Use TIME_SERIES_INTRADAY (converged API with extended hours support)
                # Use compact mode (100 bars)
                df = await self.get_intraday_bars(symbol, av_interval, "compact")  # type: ignore[attr-defined]

                logger.info(
                    "Fetched intraday data",
                    symbol=symbol,
                    interval=interval,
                    outputsize="compact",
                    bars_count=len(df),
                    time_range=(
                        f"{df.index.min()} to {df.index.max()}"
                        if not df.empty
                        else "empty"
                    ),
                )

            elif interval in ["1d", "day"]:
                # Daily - use full mode for complete historical data (20+ years)
                df = await self.get_daily_bars(symbol, "full")  # type: ignore[attr-defined]
            elif interval in ["1wk", "1w", "week"]:
                # Weekly
                df = await self.get_weekly_bars(symbol, "full")  # type: ignore[attr-defined]
            elif interval in ["1mo", "1M", "month"]:
                # Monthly
                df = await self.get_monthly_bars(symbol, "full")  # type: ignore[attr-defined]
            else:
                # Default to daily
                logger.warning(
                    f"Unsupported interval '{interval}', defaulting to daily",
                    symbol=symbol,
                )
                df = await self.get_daily_bars(symbol, "compact")  # type: ignore[attr-defined]

            # For intraday data, always return the most recent data available
            if (
                interval in ["1m", "5m", "15m", "30m", "60m", "60min", "1h"]
                and not df.empty
            ):
                logger.info(
                    "Returning latest available intraday data",
                    symbol=symbol,
                    requested_range=(
                        f"{start_date} to {end_date}"
                        if start_date and end_date
                        else "none"
                    ),
                    actual_range=f"{df.index.min()} to {df.index.max()}",
                )

            return self._postprocess_price_bars(
                df, symbol, interval, start_date, end_date
            )

        except Exception as e:
            logger.error(
                "Price bars fetch failed",
                symbol=symbol,
                interval=interval,
                error=str(e),
            )
            raise

    def _postprocess_price_bars(
        self,
        df: pd.DataFrame,
        symbol: str,
        interval: str,
        start_date: str | None,
        end_date: str | None,
    ) -> pd.DataFrame:
        """Apply time caps, custom date filtering, and default bar limits.

        Shared between the yfinance and Alpha Vantage code paths so both
        sources produce identically-shaped output.
        """
        # Apply interval-specific time caps
        if not df.empty:
            time_cap_years = {
                "1d": 2,
                "day": 2,
                "1w": 6,
                "1wk": 6,
                "week": 6,
            }

            years_cap = time_cap_years.get(interval)

            if years_cap:
                cutoff_date = datetime.now() - timedelta(days=years_cap * 365)

                if df.index.tz is not None:
                    cutoff_dt = pd.to_datetime(cutoff_date).tz_localize(
                        "America/New_York"
                    )
                else:
                    cutoff_dt = pd.to_datetime(cutoff_date)

                original_count = len(df)
                df = df[df.index >= cutoff_dt]

                logger.info(
                    "Applied time cap",
                    symbol=symbol,
                    interval=interval,
                    years_cap=years_cap,
                    cutoff_date=cutoff_dt,
                    original_count=original_count,
                    filtered_count=len(df),
                )

        # Filter data by custom date range OR apply default limits
        if not df.empty:
            if start_date and end_date:
                if df.index.tz is not None:
                    start_dt = pd.to_datetime(start_date).tz_localize(
                        "America/New_York"
                    )
                    end_dt = (
                        pd.to_datetime(end_date)
                        + pd.Timedelta(days=1)
                        - pd.Timedelta(seconds=1)
                    ).tz_localize("America/New_York")
                else:
                    start_dt = pd.to_datetime(start_date)
                    end_dt = (
                        pd.to_datetime(end_date)
                        + pd.Timedelta(days=1)
                        - pd.Timedelta(seconds=1)
                    )

                original_count = len(df)
                original_df_copy = df.copy()
                df = df[(df.index >= start_dt) & (df.index <= end_dt)]

                logger.info(
                    "Filtered to custom date range",
                    symbol=symbol,
                    interval=interval,
                    start_date=start_date,
                    end_date=end_date,
                    original_count=original_count,
                    filtered_count=len(df),
                )

                # For intraday: if no data, fall back to most recent available
                if df.empty and interval in ["1m", "60m", "1h", "60min"]:
                    logger.info(
                        "No data for requested date range, returning most recent intraday data",
                        symbol=symbol,
                        interval=interval,
                        requested_range=f"{start_date} to {end_date}",
                    )
                    df = original_df_copy
                    max_bars = 420 if interval == "1m" else 85
                    if len(df) > max_bars:
                        df = df.tail(max_bars)
            else:
                # Apply default bar limits
                max_bars_map: dict[str, int] = {
                    "1m": 100,
                    "1h": 100,
                    "60min": 100,
                }
                max_bars_optional: int | None = max_bars_map.get(interval)
                if max_bars_optional is not None and len(df) > max_bars_optional:
                    original_count = len(df)
                    df = df.tail(max_bars_optional)
                    logger.info(
                        "Limited data to max bars",
                        symbol=symbol,
                        interval=interval,
                        original_count=original_count,
                        limited_count=len(df),
                        max_bars=max_bars_optional,
                    )

        return df
