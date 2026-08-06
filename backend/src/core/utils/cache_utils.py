"""
Generic caching utilities for tool execution.

Provides consistent cache key generation and TTL strategies
for all registered agent tools.
"""

import typing


def generate_tool_cache_key(
    tool_source: str,
    tool_name: str,
    params: dict[str, typing.Any],
) -> str:
    """
    Generate consistent cache key for ANY tool call.

    Cache key format: {api_source}:{tool_name}:{param1=val1}:{param2=val2}:...
    Parameters are sorted alphabetically for consistency.

    Args:
        tool_source: API source (mcp_alphavantage, 1st_party)
        tool_name: Tool name (GLOBAL_QUOTE, fibonacci_analysis_tool)
        params: Input parameters as dict

    Returns:
        Cache key string for Redis storage

    Examples:
        >>> generate_tool_cache_key(
        ...     "mcp_alphavantage",
        ...     "GLOBAL_QUOTE",
        ...     {"symbol": "AAPL"}
        ... )
        'mcp_alphavantage:GLOBAL_QUOTE:symbol=AAPL'

        >>> generate_tool_cache_key(
        ...     "mcp_alphavantage",
        ...     "RSI",
        ...     {"symbol": "AAPL", "interval": "daily", "time_period": "14"}
        ... )
        'mcp_alphavantage:RSI:interval=daily:symbol=AAPL:time_period=14'

        >>> generate_tool_cache_key(
        ...     "1st_party",
        ...     "fibonacci_analysis_tool",
        ...     {"symbol": "AAPL", "timeframe": "1d", "start_date": "2025-01-01"}
        ... )
        '1st_party:fibonacci_analysis_tool:start_date=2025-01-01:symbol=AAPL:timeframe=1d'
    """
    # Sort params alphabetically for consistency
    sorted_params = sorted(params.items())

    # Build param string
    param_str = ":".join(f"{k}={v}" for k, v in sorted_params)

    return f"{tool_source}:{tool_name}:{param_str}"


# TTL configuration for different tool types
TOOL_TTL_MAP = {
    # Alpha Vantage - Real-Time Data (5-minute update frequency)
    "GLOBAL_QUOTE": 300,  # 5 minutes (matches API update)
    "REALTIME_BULK_QUOTES": 300,  # 5 minutes
    "MARKET_STATUS": 300,  # 5 minutes
    # Alpha Vantage - News & Sentiment (hourly updates)
    "NEWS_SENTIMENT": 3600,  # 1 hour (news changes slowly)
    "EARNINGS_CALL_TRANSCRIPT": 86400,  # 24 hours
    "TOP_GAINERS_LOSERS": 1800,  # 30 minutes
    "INSIDER_TRANSACTIONS": 3600,  # 1 hour
    # Alpha Vantage - Technical Indicators (interval-dependent)
    # These will use get_tool_ttl() with interval parameter
    "RSI": "interval_dependent",
    "MACD": "interval_dependent",
    "STOCHASTIC": "interval_dependent",
    "SMA": "interval_dependent",
    "EMA": "interval_dependent",
    "DEMA": "interval_dependent",
    "TEMA": "interval_dependent",
    "WMA": "interval_dependent",
    "VWAP": "interval_dependent",
    "BBANDS": "interval_dependent",
    "ATR": "interval_dependent",
    "AD": "interval_dependent",
    "OBV": "interval_dependent",
    "ADOSC": "interval_dependent",
    "MFI": "interval_dependent",
    "BOP": "interval_dependent",
    "CCI": "interval_dependent",
    "AROON": "interval_dependent",
    "AROONOSC": "interval_dependent",
    "ADX": "interval_dependent",
    "ADXR": "interval_dependent",
    "APO": "interval_dependent",
    "PPO": "interval_dependent",
    "MOM": "interval_dependent",
    "ROC": "interval_dependent",
    "ROCR": "interval_dependent",
    "TRIX": "interval_dependent",
    "ULTOSC": "interval_dependent",
    "DX": "interval_dependent",
    "MINUS_DI": "interval_dependent",
    "PLUS_DI": "interval_dependent",
    "MINUS_DM": "interval_dependent",
    "PLUS_DM": "interval_dependent",
    "WILLR": "interval_dependent",
    "CMO": "interval_dependent",
    "MIDPOINT": "interval_dependent",
    "MIDPRICE": "interval_dependent",
    "SAR": "interval_dependent",
    "TRANGE": "interval_dependent",
    "NATR": "interval_dependent",
    "HT_TRENDLINE": "interval_dependent",
    # Alpha Vantage - Fundamental Data (quarterly/yearly updates)
    "COMPANY_OVERVIEW": 86400,  # 24 hours (fundamentals change rarely)
    "EARNINGS": 86400,  # 24 hours
    "BALANCE_SHEET": 86400,  # 24 hours
    "CASH_FLOW": 86400,  # 24 hours
    "INCOME_STATEMENT": 86400,  # 24 hours
    "EARNINGS_CALENDAR": 86400,  # 24 hours
    "IPO_CALENDAR": 86400,  # 24 hours
    # Alpha Vantage - Historical Time Series (immutable once written)
    "TIME_SERIES_INTRADAY": 1800,  # 30 minutes
    "TIME_SERIES_DAILY": 3600,  # 1 hour
    "TIME_SERIES_DAILY_ADJUSTED": 3600,  # 1 hour
    "TIME_SERIES_WEEKLY": 7200,  # 2 hours
    "TIME_SERIES_WEEKLY_ADJUSTED": 7200,  # 2 hours
    "TIME_SERIES_MONTHLY": 14400,  # 4 hours
    "TIME_SERIES_MONTHLY_ADJUSTED": 14400,  # 4 hours
    "GLOBAL_EQUITY": 3600,  # 1 hour
    # Alpha Vantage - Forex (real-time)
    "FX_INTRADAY": 300,  # 5 minutes
    "FX_DAILY": 3600,  # 1 hour
    "FX_WEEKLY": 7200,  # 2 hours
    "FX_MONTHLY": 14400,  # 4 hours
    # Alpha Vantage - Commodities
    "WTI": 1800,  # 30 minutes
    "BRENT": 1800,  # 30 minutes
    "NATURAL_GAS": 1800,  # 30 minutes
    "COPPER": 1800,  # 30 minutes
    "ALUMINUM": 1800,  # 30 minutes
    "WHEAT": 1800,  # 30 minutes
    "CORN": 1800,  # 30 minutes
    "COTTON": 1800,  # 30 minutes
    "SUGAR": 1800,  # 30 minutes
    "COFFEE": 1800,  # 30 minutes
    # Alpha Vantage - Economic Indicators (monthly/quarterly updates)
    "REAL_GDP": 86400,  # 24 hours
    "GDP_PER_CAPITA": 86400,  # 24 hours
    "TREASURY_YIELD": 3600,  # 1 hour
    "FEDERAL_FUNDS_RATE": 3600,  # 1 hour
    "CPI": 86400,  # 24 hours
    "INFLATION": 86400,  # 24 hours
    "INFLATION_EXPECTATION": 86400,  # 24 hours
    "RETAIL_SALES": 86400,  # 24 hours
    "DURABLES": 86400,  # 24 hours
    "UNEMPLOYMENT": 86400,  # 24 hours
    "NONFARM_PAYROLL": 86400,  # 24 hours
    # Alpha Vantage - Options (real-time)
    "REALTIME_OPTIONS": 300,  # 5 minutes
    "HISTORICAL_OPTIONS": 3600,  # 1 hour
    # 1st-Party Tools (depends on underlying data)
    "fibonacci_analysis_tool": 1800,  # 30 minutes (uses cached price data)
    "stochastic_analysis_tool": 1800,  # 30 minutes
}

# Interval-specific TTL map for technical indicators
INTERVAL_TTL_MAP = {
    "1min": 60,  # 1 minute interval → 1 min cache
    "5min": 300,  # 5 minute interval → 5 min cache
    "15min": 900,  # 15 minute interval → 15 min cache
    "30min": 1800,  # 30 minute interval → 30 min cache
    "60min": 3600,  # 1 hour interval → 1 hour cache
    "daily": 3600,  # Daily interval → 1 hour cache
    "weekly": 7200,  # Weekly → 2 hours
    "monthly": 14400,  # Monthly → 4 hours
}


def get_tool_ttl(tool_name: str, interval: str | None = None) -> int:
    """
    Get appropriate TTL for tool based on its type and interval.

    Args:
        tool_name: Name of tool (e.g., "GLOBAL_QUOTE", "RSI")
        interval: Data interval (for technical indicators)

    Returns:
        TTL in seconds

    Examples:
        >>> get_tool_ttl("GLOBAL_QUOTE")
        300  # 5 minutes

        >>> get_tool_ttl("NEWS_SENTIMENT")
        3600  # 1 hour

        >>> get_tool_ttl("RSI", "daily")
        3600  # 1 hour (matches daily interval)

        >>> get_tool_ttl("RSI", "5min")
        300  # 5 minutes (matches 5min interval)

        >>> get_tool_ttl("COMPANY_OVERVIEW")
        86400  # 24 hours (fundamentals change rarely)

        >>> get_tool_ttl("unknown_tool")
        1800  # Default: 30 minutes
    """
    ttl_config = TOOL_TTL_MAP.get(tool_name)

    # If tool not found, use default
    if ttl_config is None:
        return 1800  # Default: 30 minutes

    # Interval-dependent TTL (for technical indicators)
    if ttl_config == "interval_dependent" and interval:
        return INTERVAL_TTL_MAP.get(interval, 1800)

    # Fixed TTL
    if isinstance(ttl_config, int):
        return ttl_config

    # Fallback
    return 1800


# API cost tracking (Alpha Vantage free tier)
# Free tier: 25 calls/day, cost = $0/month
# Estimated cost per call if paying: $49.99/month for 75 calls/min = ~$0.00004/call
ALPHA_VANTAGE_FREE_TIER_CALL_COST = 0.00004  # Estimated value for tracking only


def get_api_cost(tool_source: str, tool_name: str) -> float:
    """
    Get estimated API cost for a tool call.

    Args:
        tool_source: Tool source (mcp_alphavantage, 1st_party)
        tool_name: Tool name

    Returns:
        Estimated cost in USD (0.0 for free APIs)

    Examples:
        >>> get_api_cost("mcp_alphavantage", "GLOBAL_QUOTE")
        0.00004  # Alpha Vantage free tier (tracking only)

        >>> get_api_cost("1st_party", "fibonacci_analysis_tool")
        0.0  # Our local tool, no external API cost
    """
    if tool_source == "mcp_alphavantage":
        return ALPHA_VANTAGE_FREE_TIER_CALL_COST

    # 1st-party tools have no API cost (just compute)
    return 0.0
