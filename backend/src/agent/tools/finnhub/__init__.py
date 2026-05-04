"""Finnhub-backed LangChain tools (quote, news, insider trades).

All tools call DataManager so the Finnhub → Alpha Vantage → yfinance fallback
chain applies; tools never call FinnhubService directly.
"""

from .insider import create_finnhub_insider_tool
from .news import create_finnhub_news_tool
from .quotes import create_finnhub_quote_tool


def create_finnhub_tools(data_manager: object) -> list:
    """Aggregate all Finnhub-backed tools (quote + news + insider)."""
    return [
        *create_finnhub_quote_tool(data_manager),
        *create_finnhub_news_tool(data_manager),
        *create_finnhub_insider_tool(data_manager),
    ]


__all__ = [
    "create_finnhub_insider_tool",
    "create_finnhub_news_tool",
    "create_finnhub_quote_tool",
    "create_finnhub_tools",
]
