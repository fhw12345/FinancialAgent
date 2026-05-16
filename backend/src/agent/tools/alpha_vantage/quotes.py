"""
Stock Quote and Symbol Search Tools.

Provides tools for getting current stock prices and searching ticker symbols.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from langchain_core.tools import tool

from src.services.alphavantage_market_data import AlphaVantageMarketDataService

logger = structlog.get_logger()


_SOURCE_PREFIX = {
    "finnhub": "FH",
    "yfinance": "YF",
    "alphavantage": "AV",
}


def _quote_source_id(source: str | None, symbol: str, asof: datetime | None) -> str:
    """Stable footnote ID for a quote (W3.2).

    Format: ``{PREFIX}-Q-{SYMBOL}-{YYYY-MM-DD}`` — short enough to read
    in markdown and stable across the trading day so the LLM can cite it
    once and reuse it. Falls back to the raw source name when we don't
    have a registered prefix yet (e.g., a newly-added provider).
    """
    prefix = _SOURCE_PREFIX.get((source or "").lower(), (source or "src").upper())
    asof_day = (asof or datetime.now(UTC)).strftime("%Y-%m-%d")
    return f"{prefix}-Q-{symbol.upper()}-{asof_day}"


def create_quote_tools(
    service: AlphaVantageMarketDataService,
    data_manager: Any | None = None,
) -> list:
    """
    Create quote and symbol search tools.

    Args:
        service: Initialized AlphaVantageMarketDataService instance. Still
            required for market_status and as the eventual fallback for the
            search tool — both of which are AV-only paths today.
        data_manager: Optional DataManager. When provided, the quote tool
            routes through DataManager.get_quote() so it benefits from the
            Finnhub → yfinance → AV fallback chain instead of burning the
            25/day AV quota on every quote.

    Returns:
        List of quote-related LangChain tools
    """

    @tool
    async def get_stock_quote(symbol: str, region: str = "United States") -> str:
        """
        Get current stock price with OHLC data and market status.

        Returns real-time quote (15-min delayed) with:
        - Current price and daily change percentage
        - Open, High, Low prices for the trading day
        - Trading volume
        - Market status (open/closed) from Alpha Vantage global market API
        - Current local time for the market and UTC time

        Use this tool when the user asks about current stock price,
        today's price movement, or wants to know if the market is open.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "TSLA", "VRT", "BABA")
            region: Market region for status check. Supported values:
                - "United States" (default) - NYSE, NASDAQ
                - "Hong Kong" - HKEX
                - "Mainland China" - Shanghai, Shenzhen
                - "Japan" - Tokyo
                - "United Kingdom" - London

        Returns:
            Compact quote summary with price, OHLC, market status, and timestamps

        Examples:
            - symbol="AAPL" → Apple current price with US market status
            - symbol="VRT" → Vertiv current quote
            - symbol="9988.HK", region="Hong Kong" → Alibaba HK with HK market status
        """
        try:
            # Quote: prefer DataManager (Finnhub → yfinance → AV fallback chain)
            # so we don't burn the AV daily quota on every quote. Fall back to
            # the AV service if no DataManager was wired in.
            source_name: str | None = None
            asof_dt: datetime | None = None
            if data_manager is not None:
                qd = await data_manager.get_quote(symbol)
                quote_data = {
                    "symbol": qd.symbol,
                    "price": qd.price,
                    "open": qd.open,
                    "high": qd.high,
                    "low": qd.low,
                    "volume": qd.volume,
                    "change_percent": str(qd.change_percent),
                    "latest_trading_day": qd.latest_trading_day,
                    "previous_close": qd.previous_close,
                    "session": getattr(qd, "session", None),
                    # W3.18 — pass-through for the ext-hours companion line below.
                    "ext_hours_price": getattr(qd, "ext_hours_price", None),
                    "ext_hours_session": getattr(qd, "ext_hours_session", None),
                    "ext_hours_change_percent": getattr(
                        qd, "ext_hours_change_percent", None
                    ),
                }
                source_name = getattr(qd, "source", None)
                asof_dt = getattr(qd, "asof", None)
            else:
                quote_data = await service.get_quote(symbol)
                # AV-direct path: no fallback chain ran, source is AV.
                source_name = "alphavantage"

            if not quote_data or quote_data.get("price", 0) == 0:
                return f"No quote data available for {symbol}"

            # Get market status from Alpha Vantage MARKET_STATUS API
            try:
                market_status = await service.get_market_status(region)
                current_status = market_status.get("current_status", "unknown")
                local_time = market_status.get("local_time", "N/A")
                utc_time = market_status.get("utc_time", "N/A")
                notes = market_status.get("notes", "")
            except Exception as e:
                logger.warning(
                    "Market status fetch failed, using fallback",
                    region=region,
                    error=str(e),
                )
                current_status = "unknown"
                local_time = "N/A"
                utc_time = "N/A"
                notes = ""

            # Extract quote fields
            price = quote_data.get("price", 0)
            open_price = quote_data.get("open", 0)
            high = quote_data.get("high", 0)
            low = quote_data.get("low", 0)
            volume = quote_data.get("volume", 0)
            change_pct = quote_data.get("change_percent", "0")
            latest_day = quote_data.get("latest_trading_day", "N/A")
            prev_close = quote_data.get("previous_close", 0)

            # Format change percent (ensure % sign)
            if not change_pct.endswith("%"):
                change_pct = f"{change_pct}%"

            # Build compact output for LLM
            session = quote_data.get("session")
            output_lines = [
                f"{symbol}: ${price:.2f} ({change_pct}) | "
                f"O:${open_price:.2f} H:${high:.2f} L:${low:.2f} | Vol:{volume:,}",
                f"Prev Close: ${prev_close:.2f} | Date: {latest_day}",
                f"Market: {current_status} | Local: {local_time} | {utc_time}",
            ]
            if session in ("pre", "post"):
                output_lines.append(
                    f"Session: {session} (extended-hours; volume thin, "
                    "price is indicative)"
                )
            elif session and session != "regular":
                output_lines.append(f"Session: {session}")

            # W3.18 — extended-hours companion print, if any. Surfaces the
            # most recent pre/post move *alongside* the regular/closed
            # primary so the agent can reason about overnight gaps. The
            # source-id token reused below pins the citation to the same
            # quote — one quote = one citation, regardless of whether the
            # number cited is the primary or the companion.
            ext_price = quote_data.get("ext_hours_price")
            ext_session = quote_data.get("ext_hours_session")
            ext_pct = quote_data.get("ext_hours_change_percent")
            if ext_price is not None and ext_session in ("pre", "post"):
                label = "After-hours" if ext_session == "post" else "Pre-market"
                pct_str = (
                    f" ({ext_pct:+.2f}%)" if isinstance(ext_pct, int | float) else ""
                )
                output_lines.append(
                    f"{label}: ${ext_price:.2f}{pct_str} vs primary print"
                )

            # Add notes if present (e.g., lunch breaks for Asian markets)
            if notes:
                output_lines.append(f"Note: {notes}")

            # W3.2 provenance footnote — gives the Phase2 prompt a stable
            # token to cite ("[YF-Q-AAPL-2026-05-09]") so thesis bullets
            # can be traced back to a source. Frontend (W3.7) parses these
            # tokens to render the footnote list.
            if source_name:
                source_id = _quote_source_id(source_name, symbol, asof_dt)
                asof_repr = (
                    asof_dt.strftime("%Y-%m-%dT%H:%MZ") if asof_dt else "asof unknown"
                )
                output_lines.append(
                    f"Source: {source_name} [{source_id}] asof {asof_repr}"
                )

            output_lines.append("⚠️ Data delayed 15 minutes")

            logger.info(
                "Stock quote fetched",
                symbol=symbol,
                price=price,
                region=region,
                market_status=current_status,
            )

            return "\n".join(output_lines)

        except Exception as e:
            logger.error("Stock quote tool failed", symbol=symbol, error=str(e))
            return f"Stock quote error for {symbol}: {str(e)}"

    @tool
    async def search_ticker(query: str) -> str:
        """
        Search for stock ticker symbols by company name or partial symbol.

        Supports fuzzy matching on company names and symbols.
        Returns top matches with symbol, name, exchange, and confidence scores.

        Args:
            query: Company name or partial symbol (e.g., "apple", "micro", "AAPL")

        Returns:
            Compressed search results (top 5 matches with confidence scores)

        Examples:
            - query="apple" → AAPL, AAON, etc.
            - query="microsoft" → MSFT
            - query="TSL" → TSLA (Tesla)
        """
        try:
            results = await service.search_symbols(query, limit=5)

            if not results:
                return f"No ticker symbols found for query: {query}"

            # Format top 5 results
            formatted = [
                f"{r['symbol']} ({r['name']}, {r['exchange']}, {r['confidence']:.0%})"
                for r in results[:5]
            ]

            return f"""Ticker Search: "{query}"
Top Matches: {", ".join(formatted[:3])}
{f"More: {', '.join(formatted[3:])}" if len(formatted) > 3 else ""}"""

        except Exception as e:
            logger.error("Ticker search tool failed", query=query, error=str(e))
            return f"Ticker search error for '{query}': {str(e)}"

    return [get_stock_quote, search_ticker]
