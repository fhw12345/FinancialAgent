"""
Fundamental Analysis Tools.

Provides tools for company fundamentals, financial statements, insider activity, and ETF holdings.
"""

from datetime import UTC, datetime

import structlog
from langchain_core.tools import tool

from src.core.config import get_settings
from src.services.alphavantage_market_data import AlphaVantageMarketDataService
from src.services.alphavantage_response_formatter import AlphaVantageResponseFormatter

logger = structlog.get_logger()


def create_fundamental_tools(
    service: AlphaVantageMarketDataService, formatter: AlphaVantageResponseFormatter
) -> list:
    """
    Create fundamental analysis tools.

    Args:
        service: Initialized AlphaVantageMarketDataService instance
        formatter: AlphaVantageResponseFormatter for consistent markdown output

    Returns:
        List of fundamental analysis LangChain tools
    """

    @tool
    async def get_company_overview(symbol: str) -> str:
        """
        Get comprehensive company fundamentals and overview.

        Returns key financial metrics, ratios, and company information including:
        - Company info: Name, Description, Industry, Sector
        - Market metrics: Market Cap, P/E Ratio, EPS, Beta
        - Financial ratios: Profit Margin, Revenue, Dividend Yield
        - Ownership: Percent held by insiders and institutions
        - Price metrics: 52-week high/low, Moving averages

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "MSFT", "TSLA")

        Returns:
            Formatted company overview with key metrics table

        Examples:
            - symbol="AAPL" → Apple Inc. fundamentals
            - symbol="MSFT" → Microsoft Corporation overview
        """
        try:
            data = await service.get_company_overview(symbol)

            if not data or "Symbol" not in data:
                return f"No company overview data available for {symbol}"

            # Use formatter for consistent rich markdown output
            return formatter.format_company_overview(
                raw_data=data,
                symbol=symbol,
                invoked_at=datetime.now(UTC).isoformat(),
            )

        except Exception as e:
            logger.error("Company overview tool failed", symbol=symbol, error=str(e))
            return f"Company overview error for {symbol}: {str(e)}"

    @tool
    async def get_financial_statements(
        symbol: str,
        statement_type: str = "cash_flow",
        count: int = 3,
        period: str = "quarter",
    ) -> str:
        """
        Get financial statements (Cash Flow or Balance Sheet) for a company.

        Returns annual and/or quarterly financial data with key metrics.
        Supports configurable number of periods for trend analysis.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "MSFT", "MRVL")
            statement_type: Type of statement - "cash_flow" or "balance_sheet"
            count: Number of periods to return (default: 3)
            period: "quarter" for quarterly data, "year" for annual data (default: "quarter")

        Limits:
            - Quarterly: max 20 periods
            - Annual: max 5 periods

        Returns:
            Multi-period financial statement with trends and analysis

        Cash Flow Metrics:
            - Operating Cash Flow, Capital Expenditures
            - Free Cash Flow (Operating - CapEx)
            - Dividend Payout, Net Income

        Balance Sheet Metrics:
            - Total Assets, Total Liabilities, Shareholder Equity
            - Current Assets/Liabilities, Cash, Debt

        Examples:
            - get_financial_statements("MRVL") → Latest 3 quarters cash flow (default)
            - get_financial_statements("AAPL", "cash_flow", 4, "quarter") → Last 4 quarters
            - get_financial_statements("GOOGL", "cash_flow", 2, "year") → Last 2 years
            - get_financial_statements("MSFT", "balance_sheet", 3, "quarter") → Last 3 quarters balance sheet
        """
        try:
            statement_type = statement_type.lower().strip()
            period = period.lower().strip()

            if statement_type not in ["cash_flow", "balance_sheet"]:
                return f"Invalid statement_type: {statement_type}. Use 'cash_flow' or 'balance_sheet'"

            if period not in ["quarter", "year"]:
                return f"Invalid period: {period}. Use 'quarter' or 'year'"

            # Validate and cap count based on period type (limits from config)
            settings = get_settings()
            if period == "quarter":
                count = min(max(1, count), settings.fundamentals_max_quarterly_periods)
            else:
                count = min(max(1, count), settings.fundamentals_max_annual_periods)

            # Fetch data based on type
            if statement_type == "cash_flow":
                data = await service.get_cash_flow(symbol)
                # Use formatter for consistent rich markdown output with trends
                return formatter.format_cash_flow(
                    raw_data=data,
                    symbol=symbol,
                    invoked_at=datetime.now(UTC).isoformat(),
                    count=count,
                    period=period,
                )
            else:
                data = await service.get_balance_sheet(symbol)
                # Use formatter for consistent rich markdown output with trends
                return formatter.format_balance_sheet(
                    raw_data=data,
                    symbol=symbol,
                    invoked_at=datetime.now(UTC).isoformat(),
                    count=count,
                    period=period,
                )

        except Exception as e:
            logger.error(
                "Financial statements tool failed",
                symbol=symbol,
                statement_type=statement_type,
                error=str(e),
            )
            return f"Financial statements error for {symbol}: {str(e)}"

    @tool
    async def get_insider_activity(symbol: str, limit: int = 50) -> str:
        """
        Get recent insider trading activity (executive buy/sell transactions).

        Shows insider sentiment through actual transactions by company executives,
        directors, and major shareholders. Useful for detecting insider confidence.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "TSLA")
            limit: Number of recent transactions to analyze (default: 50)

        Returns:
            Formatted insider activity summary with acquisition/disposal trends

        Examples:
            - symbol="AAPL" → Recent insider transactions with buy/sell ratio
            - symbol="NVDA", limit=100 → Extended insider activity analysis
        """
        try:
            data = await service.get_insider_transactions(symbol, limit)

            if not data or not data.get("data"):
                return f"No insider transaction data available for {symbol}"

            return formatter.format_insider_transactions(
                raw_data=data,
                symbol=symbol,
                invoked_at=datetime.now(UTC).isoformat(),
            )
        except Exception as e:
            logger.error("Insider activity tool failed", symbol=symbol, error=str(e))
            return f"Insider activity error for {symbol}: {str(e)}"

    @tool
    async def get_company_earnings(symbol: str) -> str:
        """
        Get quarterly and annual earnings (EPS) history with beat/miss analysis.

        Returns historical earnings per share with estimated vs reported EPS,
        surprise amounts, and beat/miss tracking. Useful for evaluating
        earnings quality and management execution.

        Args:
            symbol: Stock ticker symbol (e.g., "AAPL", "MSFT", "GOOGL")

        Returns:
            Formatted earnings history with beat rate and YoY growth

        Examples:
            - symbol="AAPL" → Apple quarterly EPS with beat/miss analysis
            - symbol="NVDA" → NVIDIA earnings trend and surprise history
        """
        try:
            data = await service.get_earnings(symbol)

            if not data:
                return f"No earnings data available for {symbol}"

            return formatter.format_earnings(
                raw_data=data,
                symbol=symbol,
                invoked_at=datetime.now(UTC).isoformat(),
            )

        except Exception as e:
            logger.error("Earnings tool failed", symbol=symbol, error=str(e))
            return f"Earnings data error for {symbol}: {str(e)}"

    @tool
    async def get_etf_holdings(symbol: str) -> str:
        """
        Get ETF profile with top holdings and sector allocation.

        Returns comprehensive ETF information including constituent stocks,
        sector breakdown, and fund characteristics. Useful for understanding
        ETF composition and diversification.

        Args:
            symbol: ETF ticker symbol (e.g., "QQQ", "SPY", "SOXS")

        Returns:
            Formatted ETF profile with holdings, sectors, and fund metrics

        Examples:
            - symbol="QQQ" → Nasdaq-100 ETF holdings (tech-heavy)
            - symbol="SOXS" → 3x leveraged semiconductor inverse ETF
            - symbol="SPY" → S&P 500 ETF holdings
        """
        try:
            data = await service.get_etf_profile(symbol)

            if not data:
                return (
                    f"No ETF profile data available for {symbol} (verify it's an ETF)"
                )

            return formatter.format_etf_profile(
                raw_data=data,
                symbol=symbol,
                invoked_at=datetime.now(UTC).isoformat(),
            )
        except Exception as e:
            logger.error("ETF holdings tool failed", symbol=symbol, error=str(e))
            return f"ETF holdings error for {symbol}: {str(e)}"

    return [
        get_company_overview,
        get_financial_statements,
        get_company_earnings,
        get_insider_activity,
        get_etf_holdings,
    ]
