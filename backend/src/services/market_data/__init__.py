"""
Market data services for financial data access.

This module provides:
- Alpha Vantage API integration for market data
- FRED API integration for economic/liquidity indicators

Components:
- base: Initialization, HTTP client, and sanitization utilities
- quotes: Stock quotes, symbol search, and price bars
- fundamentals: Company data, financial statements, earnings
- macro: Economic indicators and commodity prices
- technical: Technical indicators (SMA, EMA, RSI, MACD, etc.)
- fred: FRED API for SOFR, EFFR, RRP liquidity metrics
"""

from datetime import datetime, time
from typing import Literal

import pandas as pd

from ...core.utils.market_calendar import market_today
from .bars_basic import BarsBasicMixin
from .bars_extended import BarsExtendedMixin
from .base import AlphaVantageBase
from .fred import FREDService
from .fundamentals import FundamentalsMixin
from .macro import MacroMixin
from .options import OptionsMixin
from .quotes import QuotesMixin
from .technical import TechnicalMixin


def get_market_session(
    timestamp: pd.Timestamp,
) -> Literal["pre", "regular", "post", "closed"]:
    """
    Determine market session for a given timestamp (US Eastern Time).

    Market hours (ET):
    - Pre-market: 4:00 AM - 9:30 AM
    - Regular: 9:30 AM - 4:00 PM
    - Post-market: 4:00 PM - 8:00 PM
    - Closed: 8:00 PM - 4:00 AM, weekends

    Args:
        timestamp: Timestamp to check (should be in ET timezone)

    Returns:
        Market session: "pre", "regular", "post", or "closed"
    """
    # Convert to ET if not already
    if timestamp.tz is None:
        # Assume UTC, convert to ET
        timestamp = timestamp.tz_localize("UTC").tz_convert("America/New_York")
    elif str(timestamp.tz) != "America/New_York":
        timestamp = timestamp.tz_convert("America/New_York")

    # Check if weekend
    if timestamp.weekday() >= 5:  # Saturday=5, Sunday=6
        return "closed"

    time_of_day = timestamp.time()

    # Define session boundaries
    pre_start = time(4, 0)  # 4:00 AM
    regular_start = time(9, 30)  # 9:30 AM
    regular_end = time(16, 0)  # 4:00 PM
    post_end = time(20, 0)  # 8:00 PM

    if pre_start <= time_of_day < regular_start:
        return "pre"
    elif regular_start <= time_of_day < regular_end:
        return "regular"
    elif regular_end <= time_of_day < post_end:
        return "post"
    else:
        return "closed"


def validate_date_range(
    start_date: str | None,
    end_date: str | None,
    interval: str,
    symbol: str | None = None,
) -> tuple[bool, str | None]:
    """
    Validate date range based on interval constraints.

    Rules:
    - Intraday (1m, 1h): Must be today only (enforced in UI via market status)
    - Daily+ (1d, 1w, 1mo): No restrictions, any historical range allowed

    Args:
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        interval: Data interval (1m, 1h, 1d, etc.)

    Returns:
        (is_valid, error_message)
    """
    if bool(start_date) != bool(end_date):
        return False, "Both start_date and end_date are required together"

    # If no custom dates provided, always valid (use defaults)
    if not start_date and not end_date:
        return True, None

    assert start_date is not None
    assert end_date is not None

    # Parse dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as e:
        return False, f"Invalid date format: {e}. Use YYYY-MM-DD"

    # Validate start <= end
    if start > end:
        return False, "Start date must be before or equal to end date"

    # For intraday intervals, allow recent dates (last 30 days)
    # Show whatever data is available - market closed/pre/post hours data included
    intraday_intervals = [
        "1m",
        "2m",
        "5m",
        "15m",
        "30m",
        "60m",
        "1h",
        "60min",
    ]
    if interval in intraday_intervals:
        # Get current date in Eastern Time
        today = market_today(symbol)

        # Allow dates within last 30 days (Alpha Vantage intraday limit)
        earliest_allowed = today - pd.Timedelta(days=30)

        if start.date() < earliest_allowed:
            return (
                False,
                f"Intraday data ({interval}) only available for last 30 days (since {earliest_allowed})",
            )

        if end.date() > today:
            return False, f"End date cannot be in the future (today is {today})"

    # Daily+ intervals: no restrictions
    return True, None


class AlphaVantageMarketDataService(
    QuotesMixin,
    BarsBasicMixin,
    BarsExtendedMixin,
    FundamentalsMixin,
    MacroMixin,
    OptionsMixin,
    TechnicalMixin,
    AlphaVantageBase,
):
    """
    Alpha Vantage/yfinance provider adapter used by DataManager and direct APIs.

    Features:
    - Symbol search (SYMBOL_SEARCH)
    - Real-time quotes (GLOBAL_QUOTE)
    - Intraday data with pre/post market (TIME_SERIES_INTRADAY_EXTENDED)
    - Daily/Weekly/Monthly data (TIME_SERIES_DAILY/WEEKLY/MONTHLY)
    - Company fundamentals (OVERVIEW, CASH_FLOW, BALANCE_SHEET)
    - Economic indicators (GDP, CPI, INFLATION, UNEMPLOYMENT)
    - Technical indicators (SMA, EMA, RSI, MACD, etc.)

    Performance optimizations:
    - Connection pooling with persistent HTTP client
    - Pre-compiled regex patterns for API key sanitization
    """


__all__ = [
    "AlphaVantageMarketDataService",
    "FREDService",
    "get_market_session",
    "validate_date_range",
]
