"""Finnhub-backed quote tool. Goes through DataManager so the fallback chain applies."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from langchain_core.tools import tool

logger = structlog.get_logger()


_SOURCE_PREFIX = {
    "finnhub": "FH",
    "yfinance": "YF",
    "alphavantage": "AV",
}


def _quote_source_id(source: str | None, symbol: str, asof: datetime | None) -> str:
    """Stable footnote ID for a quote (W3.2 / W3.16).

    Mirrors ``alpha_vantage.quotes._quote_source_id`` so both quote tools
    emit the same footnote-token shape regardless of which one the ReAct
    agent picks. Format: ``{PREFIX}-Q-{SYMBOL}-{YYYY-MM-DD}``.
    """
    prefix = _SOURCE_PREFIX.get((source or "").lower(), (source or "src").upper())
    asof_day = (asof or datetime.now(UTC)).strftime("%Y-%m-%d")
    return f"{prefix}-Q-{symbol.upper()}-{asof_day}"


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
        # W3.18 — extended-hours companion line. Surfaces the freshest
        # pre/post print alongside a regular/closed primary so the agent
        # can reason about overnight gaps. Same source-id token as the
        # primary quote (one quote = one citation).
        ext_price = getattr(q, "ext_hours_price", None)
        ext_session = getattr(q, "ext_hours_session", None)
        ext_pct = getattr(q, "ext_hours_change_percent", None)
        ext_line = ""
        if ext_price is not None and ext_session in ("pre", "post"):
            label = "After-hours" if ext_session == "post" else "Pre-market"
            pct_str = f" ({ext_pct:+.2f}%)" if isinstance(ext_pct, int | float) else ""
            ext_line = f"{label}: ${ext_price:.2f}{pct_str} vs primary print\n"
        body = (
            f"{q.symbol}: ${q.price:.2f} ({q.change:+.2f}, {q.change_percent:+.2f}%)\n"
            f"Open ${q.open:.2f} · High ${q.high:.2f} · Low ${q.low:.2f} · "
            f"Prev Close ${q.previous_close:.2f}\n"
            f"{session_line}"
            f"{ext_line}"
            f"As of {q.latest_trading_day or 'latest'}"
        )

        # W3.16-A provenance footnote — same shape as the AV `get_stock_quote`
        # tool (see alpha_vantage/quotes.py W3.2). The ReAct agent has both
        # tools registered; whichever one it picks, downstream Phase2 + the
        # frontend footnote chip resolver get an identical token.
        # Skip the footnote when the QuoteData object pre-dates W3.2 (no
        # source/asof attributes) so legacy cached rows don't render
        # "Source: None [...]".
        source_name = getattr(q, "source", None)
        if source_name:
            asof_dt = getattr(q, "asof", None)
            sid = _quote_source_id(source_name, q.symbol, asof_dt)
            asof_repr = (
                asof_dt.strftime("%Y-%m-%dT%H:%MZ") if asof_dt else "asof unknown"
            )
            body = f"{body}\n\nSource: {source_name} [{sid}] asof {asof_repr}"

        return body

    return [finnhub_quote]
