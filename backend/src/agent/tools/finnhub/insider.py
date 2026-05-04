"""Finnhub-backed insider trades tool."""

from __future__ import annotations

import structlog
from langchain_core.tools import tool

logger = structlog.get_logger()


def create_finnhub_insider_tool(data_manager: object) -> list:
    """Build the finnhub_insider_trades LangChain tool."""

    @tool
    async def finnhub_insider_trades(symbol: str) -> str:
        """
        Get recent insider transactions for a US-listed symbol.

        Provider chain: Finnhub (primary) → Alpha Vantage (premium endpoint, may 403) → yfinance.
        Returns insider name, share count, transaction code, and date.
        Use to check whether company insiders are buying or selling.
        """
        try:
            rows = await data_manager.get_insider_trades(symbol)  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("finnhub_insider_tool_failed", symbol=symbol, error=str(e))
            return f"Failed to fetch insider trades for {symbol}: {e}"

        if not rows:
            return f"No recent insider transactions found for {symbol}."

        lines = [f"{symbol} recent insider transactions ({len(rows)} rows):"]
        for r in rows[:10]:
            name = r.get("name") or r.get("Insider") or "?"
            share = r.get("share") or r.get("Shares") or r.get("change") or "?"
            code = (
                r.get("transactionCode")
                or r.get("Transaction")
                or r.get("transaction_code")
                or ""
            )
            date = (
                r.get("transactionDate")
                or r.get("filingDate")
                or r.get("Date")
                or r.get("Start Date")
                or ""
            )
            lines.append(f"- [{date}] {name}: {share} shares ({code})")
        return "\n".join(lines)

    return [finnhub_insider_trades]
