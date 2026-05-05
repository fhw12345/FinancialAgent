"""
Alpha Vantage Agent Tools for LLM Access.

Provides rich markdown outputs with metadata and trend analysis.
All tools use AlphaVantageMarketDataService for market data access.

This module is organized into the following submodules:
- quotes: Stock quotes and symbol search
- fundamentals: Company overview, financial statements, insider activity, ETF holdings
- news: News sentiment analysis
- technical: Market movers, commodities, and technical indicators
"""

from typing import Any

from src.services.alphavantage_market_data import AlphaVantageMarketDataService
from src.services.alphavantage_response_formatter import AlphaVantageResponseFormatter

from .fundamentals import create_fundamental_tools
from .news import create_news_tools
from .quotes import create_quote_tools
from .technical import create_technical_tools

__all__ = ["create_alpha_vantage_tools"]


def create_alpha_vantage_tools(
    service: AlphaVantageMarketDataService,
    formatter: AlphaVantageResponseFormatter,
    data_manager: Any | None = None,
) -> list:
    """
    Create Alpha Vantage agent tools with service dependency injection.

    Args:
        service: Initialized AlphaVantageMarketDataService instance
        formatter: AlphaVantageResponseFormatter for consistent markdown output
        data_manager: Optional DataManager. When provided, the quote tool
            routes through the Finnhub → yfinance → AV fallback chain instead
            of always calling AV directly.

    Returns:
        List of LangChain tools for agent access
    """
    # Collect tools from all submodules
    tools = []

    # Quote tools (get_stock_quote, search_ticker)
    tools.extend(create_quote_tools(service, data_manager=data_manager))

    # Fundamental tools (company_overview, financial_statements, insider_activity, etf_holdings)
    tools.extend(create_fundamental_tools(service, formatter))

    # News tools (get_news_sentiment)
    tools.extend(create_news_tools(service, formatter))

    # Technical tools (market_movers, copper_commodity, trend_indicator, momentum_indicator, volume_indicator)
    tools.extend(create_technical_tools(service, formatter))

    return tools
