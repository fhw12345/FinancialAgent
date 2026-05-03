"""
LangChain web search tool — W7 free replacement.

Originally backed by Exa (paid API). Now implemented using:
  1. yfinance.Ticker.news for symbol-specific headlines
  2. Google News RSS + Yahoo Finance RSS via feedparser for general queries

Public surface (`create_exa_tools(api_key=...)`) is preserved so callers
do not need to change. The api_key argument is accepted but ignored.
"""

import asyncio
import json
import re
from urllib.parse import quote_plus

import structlog
import yfinance as yf
from langchain_core.tools import tool

logger = structlog.get_logger()

_TICKER_RE = re.compile(r"\b[A-Z]{1,5}\b")


def _try_extract_ticker(query: str) -> str | None:
    """Best-effort: pull a likely ticker symbol from the query."""
    candidates = _TICKER_RE.findall(query)
    # Skip common stop-word uppercase tokens
    blacklist = {"AI", "CEO", "USA", "US", "EU", "IPO", "SEC", "FED", "CSAM"}
    for c in candidates:
        if c not in blacklist:
            return c
    return None


def _search_sync(query: str, num_results: int = 5) -> list[dict]:
    """Search news via yfinance (if ticker detected) or Google News RSS."""
    results: list[dict] = []
    ticker = _try_extract_ticker(query)
    if ticker:
        try:
            news = yf.Ticker(ticker).news or []
            for n in news[:num_results]:
                results.append(
                    {
                        "title": n.get("title", ""),
                        "url": n.get("link", ""),
                        "snippet": n.get("publisher", ""),
                    }
                )
        except Exception as e:
            logger.debug("yfinance news failed", ticker=ticker, error=str(e))

    if len(results) < num_results:
        # Fall back to Google News RSS (no key required)
        try:
            import feedparser

            url = (
                "https://news.google.com/rss/search?q="
                + quote_plus(query)
                + "&hl=en-US&gl=US&ceid=US:en"
            )
            feed = feedparser.parse(url)
            for entry in feed.entries[: num_results - len(results)]:
                results.append(
                    {
                        "title": entry.get("title", ""),
                        "url": entry.get("link", ""),
                        "snippet": entry.get("summary", "")[:500],
                    }
                )
        except Exception as e:
            logger.debug("Google News RSS failed", query=query, error=str(e))

    return results[:num_results]


def create_exa_tools(api_key: str = "") -> list:
    """Create web search tools (free yfinance + RSS implementation).

    Args:
        api_key: Ignored (kept for backward-compat with old call sites).

    Returns:
        List of LangChain tools.
    """

    @tool
    async def search_web_exa(query: str) -> str:
        """Search the web for financial news, lawsuits, regulatory actions, and analysis.

        Use this to find information that financial data APIs may miss:
        litigation, regulatory filings, analyst opinions, competitive threats.

        Args:
            query: Search query (e.g., "Apple CSAM lawsuit West Virginia AG")

        Returns:
            JSON string with search results including titles, URLs, and snippets.
        """
        try:
            results = await asyncio.to_thread(_search_sync, query, 5)
            return json.dumps({"source": "yfinance+rss", "results": results})
        except Exception as e:
            logger.warning("Web search failed", query=query, error=str(e))
            return json.dumps({"source": "yfinance+rss", "error": str(e)})

    return [search_web_exa]
