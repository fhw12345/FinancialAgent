"""
Core utility functions for the financial agent backend.
"""

from .cache_utils import (
    ALPHA_VANTAGE_FREE_TIER_CALL_COST,
    generate_tool_cache_key,
    get_api_cost,
    get_tool_ttl,
)
from .date_utils import (
    utcfromtimestamp,
    utcnow,
)
from .message_content import message_content_to_text
from .token_utils import (
    extract_token_usage_from_agent_result,
    extract_token_usage_from_messages,
)
from .yfinance_utils import (
    get_valid_alphavantage_intervals,
    get_valid_frontend_intervals,
    map_frontend_to_alphavantage,
    map_timeframe_to_yfinance_interval,
)

__all__ = [
    # Interval mapping
    "map_timeframe_to_yfinance_interval",
    "map_frontend_to_alphavantage",
    "get_valid_frontend_intervals",
    "get_valid_alphavantage_intervals",
    # Cache utilities
    "generate_tool_cache_key",
    "get_tool_ttl",
    "get_api_cost",
    "ALPHA_VANTAGE_FREE_TIER_CALL_COST",
    # Token utilities
    "extract_token_usage_from_messages",
    "extract_token_usage_from_agent_result",
    # LangChain message content
    "message_content_to_text",
    # Date utilities (replacements for deprecated datetime methods)
    "utcnow",
    "utcfromtimestamp",
]
