"""Finnhub-backed company news tool."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from langchain_core.tools import tool

logger = structlog.get_logger()


def _news_source_id(provider: str, symbol: str, asof: datetime | None) -> str:
    """W3.4 stable footnote ID — ``{PREFIX}-N-{SYMBOL}-{YYYY-MM-DD}``.

    News is unique among the W3.x source-wrapped tools in that the asof
    is the date of the *latest headline*, not when the tool ran. That
    way a 5-day-old news bucket is still recognizable as 5 days old in
    the footnote even if the LLM cites it tomorrow.
    """
    prefix = {"finnhub": "FH", "alphavantage": "AV", "yfinance": "YF"}.get(
        provider.lower(), provider.upper()
    )
    asof_day = (asof or datetime.now(UTC)).strftime("%Y-%m-%d")
    return f"{prefix}-N-{symbol.upper()}-{asof_day}"


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

        # W3.4 provenance footnote. Provider attribution defaults to
        # "finnhub" (the primary in DataManager._fetch_company_news);
        # finer-grained AV/yfinance attribution after fallback is a
        # follow-up. asof is the latest headline date so a stale bucket
        # is still recognizable as stale at citation time.
        latest_dt = max((n.date for n in items), default=datetime.now(UTC))
        sid = _news_source_id("finnhub", symbol, latest_dt)
        asof_repr = latest_dt.strftime("%Y-%m-%dT%H:%MZ")
        lines.append("")
        lines.append(f"Source: finnhub [{sid}] asof {asof_repr}")
        return "\n".join(lines)

    return [finnhub_news]
