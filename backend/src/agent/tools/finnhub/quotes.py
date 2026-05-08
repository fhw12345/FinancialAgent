"""Finnhub-backed quote tool. Goes through DataManager so the fallback chain applies."""

from __future__ import annotations

import structlog
from langchain_core.tools import tool

logger = structlog.get_logger()


def create_finnhub_quote_tool(data_manager: object) -> list:
    """Build the finnhub_quote LangChain tool."""

    @tool
    async def finnhub_quote(symbol: str) -> str:
        """
        Get the latest real-time stock quote for a US-listed symbol.

        Provider chain: Finnhub (primary, 60/min) → Alpha Vantage → yfinance.
        Returns price, day change, day high/low/open, previous close.
        Use when the user asks for the current price or today's movement.
        """
        try:
            q = await data_manager.get_quote(symbol)  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("finnhub_quote_tool_failed", symbol=symbol, error=str(e))
            return f"Failed to fetch quote for {symbol}: {e}"

        session = getattr(q, "session", None)
        session_line = (
            f"Session: {session} (extended-hours; volume thin, treat as indicative)\n"
            if session in ("pre", "post")
            else (f"Session: {session}\n" if session and session != "regular" else "")
        )
        return (
            f"{q.symbol}: ${q.price:.2f} ({q.change:+.2f}, {q.change_percent:+.2f}%)\n"
            f"Open ${q.open:.2f} · High ${q.high:.2f} · Low ${q.low:.2f} · "
            f"Prev Close ${q.previous_close:.2f}\n"
            f"{session_line}"
            f"As of {q.latest_trading_day or 'latest'}"
        )

    return [finnhub_quote]
