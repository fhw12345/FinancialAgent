"""
Alpha Vantage response formatters package.

Provides unified, rich markdown formatting for all Alpha Vantage API responses.
Re-exports AlphaVantageResponseFormatter for backward compatibility.

Usage:
    from src.services.formatters import AlphaVantageResponseFormatter

    formatter = AlphaVantageResponseFormatter()
    output = formatter.format_company_overview(data, "AAPL", "2024-01-01")
"""

from typing import Any

from .fundamentals import FundamentalsFormatter
from .market import MarketFormatter
from .technical import TechnicalFormatter


class AlphaVantageResponseFormatter:
    """
    Centralized formatter for Alpha Vantage API responses.

    This is a facade class that delegates to specialized formatters
    while maintaining backward compatibility with the original interface.
    """

    def __init__(self):
        """Initialize formatter components."""
        self._fundamentals = FundamentalsFormatter()
        self._market = MarketFormatter()
        self._technical = TechnicalFormatter()

    # Fundamentals methods (delegated)
    def format_company_overview(
        self, raw_data: dict[str, Any], symbol: str, invoked_at: str
    ) -> str:
        """Format company overview with comprehensive metrics."""
        return self._fundamentals.format_company_overview(raw_data, symbol, invoked_at)

    def format_earnings(
        self,
        raw_data: dict[str, Any],
        symbol: str,
        invoked_at: str,
        quarterly_count: int = 8,
    ) -> str:
        """Format earnings data with beat/miss analysis."""
        return self._fundamentals.format_earnings(
            raw_data, symbol, invoked_at, quarterly_count
        )

    def format_cash_flow(
        self,
        raw_data: dict[str, Any],
        symbol: str,
        invoked_at: str,
        count: int = 3,
        period: str = "quarter",
    ) -> str:
        """Format cash flow statement with configurable period selection."""
        return self._fundamentals.format_cash_flow(
            raw_data, symbol, invoked_at, count, period
        )

    def format_balance_sheet(
        self,
        raw_data: dict[str, Any],
        symbol: str,
        invoked_at: str,
        count: int = 3,
        period: str = "quarter",
    ) -> str:
        """Format balance sheet with configurable period selection."""
        return self._fundamentals.format_balance_sheet(
            raw_data, symbol, invoked_at, count, period
        )

    # Market methods (delegated)
    def format_news_sentiment(
        self, raw_data: dict[str, Any], symbol: str, invoked_at: str
    ) -> str:
        """Format news sentiment with positive/negative articles."""
        return self._market.format_news_sentiment(raw_data, symbol, invoked_at)

    def format_market_movers(self, raw_data: dict[str, Any], invoked_at: str) -> str:
        """Format market movers (gainers, losers, most active)."""
        return self._market.format_market_movers(raw_data, invoked_at)

    def format_insider_transactions(
        self, raw_data: dict[str, Any], symbol: str, invoked_at: str
    ) -> str:
        """Format insider transactions for LLM consumption."""
        return self._market.format_insider_transactions(raw_data, symbol, invoked_at)

    def format_etf_profile(
        self, raw_data: dict[str, Any], symbol: str, invoked_at: str
    ) -> str:
        """Format ETF profile with top holdings and sector allocation."""
        return self._market.format_etf_profile(raw_data, symbol, invoked_at)

    # Technical methods (delegated)
    def format_commodity_price(
        self,
        df: Any,  # pd.DataFrame
        commodity: str,
        interval: str,
        invoked_at: str,
    ) -> str:
        """Format commodity price data with trend analysis."""
        return self._technical.format_commodity_price(
            df, commodity, interval, invoked_at
        )

    def format_technical_indicator(
        self,
        df: Any,  # pd.DataFrame
        symbol: str,
        function: str,
        interval: str,
        invoked_at: str,
    ) -> str:
        """Format technical indicator with current value and signal."""
        return self._technical.format_technical_indicator(
            df, symbol, function, interval, invoked_at
        )

    # Legacy static methods for backward compatibility
    @staticmethod
    def _safe_float(value: str | None, default: float = 0.0) -> float:
        """Safely convert string to float."""
        from src.shared.formatters import safe_float

        return safe_float(value, default)

    @staticmethod
    def _format_large_number(value: float | None) -> str:
        """Format large numbers with M/B suffixes."""
        from src.shared.formatters import format_large_number

        return format_large_number(value)

    @staticmethod
    def _calculate_qoq_growth(current: float | None, previous: float | None) -> str:
        """Calculate quarter-over-quarter growth percentage."""
        from src.shared.formatters import calculate_qoq_growth

        return calculate_qoq_growth(current, previous)

    @staticmethod
    def _generate_metadata_header(
        tool_name: str, symbol: str | None, invoked_at: str, data_source: str
    ) -> str:
        """Generate metadata header for tool output."""
        from .base import generate_metadata_header

        return generate_metadata_header(tool_name, symbol, invoked_at, data_source)

    @staticmethod
    def _extract_current_year_quarters(
        quarterly_reports: list[dict[str, Any]], current_year: int | None = None
    ) -> list[dict[str, Any]]:
        """Extract quarters from the current year."""
        from .base import extract_current_year_quarters

        return extract_current_year_quarters(quarterly_reports, current_year)


__all__ = [
    "AlphaVantageResponseFormatter",
    "FundamentalsFormatter",
    "MarketFormatter",
    "TechnicalFormatter",
]
