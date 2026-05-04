"""Finnhub-backed company news tool."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from langchain_core.tools import tool

logger = structlog.get_logger()


def create_finnhub_news_tool(data_manager: object) -> list:
    """Build the finnhub_news LangChain tool."""

    @tool
    async def finnhub_news(symbol: str, days: int = 7) -> str:
        """
        Get recent company-specific news for a US-listed symbol.

        Provider chain: Finnhub /company-news (primary) → Alpha Vantage → yfinance.
        `days` controls the lookback window (default 7).
        Returns top headlines with source and timestamp.
        """
        days = max(1, min(int(days), 30))
        end = datetime.now(UTC).date()
        start = end - timedelta(days=days)
        try:
            items = await data_manager.get_company_news(  # type: ignore[attr-defined]
                symbol, start.isoformat(), end.isoformat()
            )
        except Exception as e:
            logger.warning("finnhub_news_tool_failed", symbol=symbol, error=str(e))
            return f"Failed to fetch news for {symbol}: {e}"

        if not items:
            return f"No recent news found for {symbol} (last {days}d)."

        lines = [f"Recent {symbol} news (last {days}d, {len(items)} items):"]
        for n in items[:10]:
            lines.append(f"- [{n.date.strftime('%Y-%m-%d')}] {n.title} ({n.source})")
        return "\n".join(lines)

    return [finnhub_news]
