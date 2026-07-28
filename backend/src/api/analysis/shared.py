"""
Shared utilities and dependencies for analysis API endpoints.

Provides common dependencies, validation functions, and constants used across
all analysis endpoints.
"""

from datetime import datetime
from typing import Any

import structlog

from ...core.utils.market_calendar import market_today
from ...services.alphavantage_market_data import AlphaVantageMarketDataService
from ...services.alphavantage_response_formatter import AlphaVantageResponseFormatter
from ...services.data_manager import DataManager
from ..models import ToolCall

logger = structlog.get_logger()

# Tool Registry for UI Metadata
TOOL_REGISTRY = {
    "fibonacci": {"title": "Fibonacci Analysis", "icon": "📊"},
    "macro": {"title": "Macro Sentiment", "icon": "🌍"},
    "company_overview": {"title": "Company Overview", "icon": "🏢"},
    "stochastic": {"title": "Stochastic Oscillator", "icon": "📈"},
    "cash_flow": {"title": "Cash Flow", "icon": "💵"},
    "balance_sheet": {"title": "Balance Sheet", "icon": "📋"},
    "news_sentiment": {"title": "News Sentiment", "icon": "📰"},
    "market_movers": {"title": "Market Movers", "icon": "🔥"},
}


def create_tool_call(
    tool_name: str, symbol: str | None = None, **metadata: Any
) -> ToolCall:
    """
    Helper to create ToolCall object with metadata from registry.

    Args:
        tool_name: Tool identifier (e.g., 'company_overview')
        symbol: Stock symbol if applicable (e.g., 'TSLA')
        **metadata: Additional tool-specific data

    Returns:
        ToolCall object with title, icon, and metadata populated
    """
    tool_info = TOOL_REGISTRY.get(tool_name, {"title": tool_name, "icon": "🔧"})
    return ToolCall(
        tool_name=tool_name,
        title=tool_info["title"],
        icon=tool_info["icon"],
        symbol=symbol,
        metadata=metadata,
    )


def get_market_service() -> AlphaVantageMarketDataService:
    """Dependency to get market data service from app state."""
    from ...main import app

    market_service: AlphaVantageMarketDataService = app.state.market_service
    return market_service


def get_data_manager() -> DataManager:
    """Dependency to get singleton DataManager from app state."""
    from ...main import app

    data_manager: DataManager = app.state.data_manager
    return data_manager


def get_formatter() -> AlphaVantageResponseFormatter:
    """Dependency to get Alpha Vantage response formatter."""
    return AlphaVantageResponseFormatter()


def validate_date_range(
    start_date: str | None,
    end_date: str | None,
    symbol: str | None = None,
) -> None:
    """
    Validate date range inputs.

    Raises:
        ValueError: If dates are invalid or in the future
    """
    if bool(start_date) != bool(end_date):
        raise ValueError("Both start_date and end_date are required together")

    today = market_today(symbol)

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            if start_dt > today:
                raise ValueError(
                    f"Start date {start_date} cannot be in the future. Latest allowed date is {today}"
                )
        except ValueError as e:
            if "cannot be in the future" in str(e):
                raise
            raise ValueError(
                f"Invalid start date format: {start_date}. Expected YYYY-MM-DD"
            ) from None

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            if end_dt > today:
                raise ValueError(
                    f"End date {end_date} cannot be in the future. Latest allowed date is {today}"
                )
        except ValueError as e:
            if "cannot be in the future" in str(e):
                raise
            raise ValueError(
                f"Invalid end date format: {end_date}. Expected YYYY-MM-DD"
            ) from None

    if start_date and end_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        if start_dt > end_dt:
            raise ValueError(
                f"Start date {start_date} cannot be after end date {end_date}"
            )

        # Check if date range is too long (more than 5 years)
        if (end_dt - start_dt).days > 5 * 365:
            raise ValueError("Date range is too long. Maximum allowed range is 5 years")
