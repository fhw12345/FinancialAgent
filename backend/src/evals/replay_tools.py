from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from src.models.symbol_resolution import SymbolCandidate

_SYMBOL_FIXTURES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "NVDA": "NVIDIA Corporation",
    "TSLA": "Tesla Inc.",
}


class ReplaySymbolSearch:
    async def exact(self, symbol: str) -> SymbolCandidate | None:
        normalized = symbol.upper()
        name = _SYMBOL_FIXTURES.get(normalized)
        if name is None:
            return None
        return SymbolCandidate(
            symbol=normalized,
            name=name,
            exchange="NASDAQ",
            match_type="exact",
            confidence=1.0,
        )

    async def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[SymbolCandidate]:
        lowered = query.lower()
        matches: list[SymbolCandidate] = []
        for symbol, name in _SYMBOL_FIXTURES.items():
            if symbol.lower() not in lowered and name.lower() not in lowered:
                continue
            candidate = await self.exact(symbol)
            if candidate is not None:
                matches.append(candidate)
        return matches[:limit]


def _fixture_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized != "AAPL":
        raise ValueError(f"No replay fixture is registered for symbol {normalized!r}")
    return normalized


def create_replay_tools() -> list[BaseTool]:
    @tool
    async def get_stock_quote(symbol: str, region: str = "United States") -> str:
        """Get the current stock price, OHLC, volume, and market status."""
        normalized = _fixture_symbol(symbol)
        return (
            f"{normalized} current price is $210.25, open $208.10, high $212.40, "
            "low $207.55, volume 48,500,000, market closed. "
            "[REPLAY-Q-AAPL-2026-08-01]"
        )

    @tool
    async def get_news_sentiment(
        symbol: str,
        max_positive: int = 3,
        max_negative: int = 3,
    ) -> str:
        """Get the latest news and sentiment for a stock."""
        normalized = _fixture_symbol(symbol)
        return (
            f"{normalized} latest news: Services revenue grew 3.0% year over "
            "year; sentiment is cautiously bullish. "
            "[REPLAY-N-AAPL-2026-08-01]"
        )

    @tool
    async def get_company_overview(symbol: str) -> str:
        """Get company fundamentals including valuation and profitability."""
        normalized = _fixture_symbol(symbol)
        return (
            f"{normalized} company overview: trailing P/E 31.2, operating "
            "margin 31.5%, market cap $3.1T. "
            "[REPLAY-OV-AAPL-2026-06-30]"
        )

    @tool
    async def get_financial_statements(
        symbol: str,
        statement_type: str = "cash_flow",
    ) -> str:
        """Get cash-flow or balance-sheet financial statements."""
        normalized = _fixture_symbol(symbol)
        return (
            f"{normalized} {statement_type}: free cash flow $98.3B. "
            "[REPLAY-CF-AAPL-2026-06-30]"
        )

    @tool
    async def fibonacci_analysis_tool(
        symbol: str,
        timeframe: str = "1d",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> str:
        """Analyze Fibonacci support and resistance for a stock."""
        normalized = _fixture_symbol(symbol)
        return (
            f"{normalized} {timeframe} Fibonacci: key support $195.00, "
            "resistance $218.00, current price remains inside the swing range. "
            "[REPLAY-FIB-AAPL-2026-08-01]"
        )

    return [
        get_stock_quote,
        get_news_sentiment,
        get_company_overview,
        get_financial_statements,
        fibonacci_analysis_tool,
    ]
