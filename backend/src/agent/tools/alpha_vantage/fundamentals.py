"""
Fundamental Analysis Tools.

Provides tools for company fundamentals, financial statements, insider activity, and ETF holdings.

Each tool tries Alpha Vantage first, then falls back to yfinance via
`_yf_fallback` (W1.4) when AV returns empty or raises. When both fail,
returns a deterministic "unavailable" string the W1.10 consistency
gate can pattern-match to reject downstream valuation claims.

W3.3 adds a one-line provenance footnote at the bottom of every
successful return:

    Source: alphavantage [AV-OV-AAPL-2025-09-30] asof 2025-09-30T00:00Z

The bracketed token is the citation handle the W3.6 Phase2 prompt
will require thesis bullets to reference, and the W3.7 frontend
ReportRenderer will resolve into a footnote chip. Format:

    {PREFIX}-{FIELD}-{SYMBOL}-{YYYY-MM-DD}

Per-field codes: ``OV`` = company_overview, ``CF`` = cash_flow,
``BS`` = balance_sheet, ``EAR`` = earnings, ``INS`` = insider.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from langchain_core.tools import tool

from src.agent.tools._yf_fallback import (
    fetch_balance_sheet_yf,
    fetch_cash_flow_yf,
    fetch_earnings_yf,
    fetch_insider_yf,
    fetch_overview_yf,
    unavailable_message,
)
from src.core.config import get_settings
from src.services.alphavantage_market_data import AlphaVantageMarketDataService
from src.services.alphavantage_response_formatter import AlphaVantageResponseFormatter

logger = structlog.get_logger()


# Same prefix table as quotes.py — kept duplicated rather than centralized
# while only two callsites use it; collapse if a third Source-wrap tool
# lands.
_SOURCE_PREFIX = {
    "finnhub": "FH",
    "yfinance": "YF",
    "alphavantage": "AV",
}


def _parse_av_date(value: Any) -> datetime | None:
    """Parse an AV response date string ("2025-09-30") into UTC datetime.

    Returns None for missing / malformed values; callers fall back to
    ``datetime.now(UTC)`` so a single rotten field doesn't kill the
    whole footnote line.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None


def _statement_asof(data: dict[str, Any] | None, *, period: str) -> datetime | None:
    """Pull the most recent ``fiscalDateEnding`` from an AV statement payload.

    AV cash-flow / balance-sheet responses have the shape:
        {"symbol": "...",
         "annualReports":   [{"fiscalDateEnding": "2024-12-31", ...}, ...],
         "quarterlyReports":[{"fiscalDateEnding": "2025-06-30", ...}, ...]}

    We pick the latest entry from whichever bucket the caller is rendering
    so the footnote ``asof`` matches the reader's view, not the other one.
    """
    if not data:
        return None
    bucket_key = "quarterlyReports" if period == "quarter" else "annualReports"
    bucket = data.get(bucket_key) or []
    if not bucket:
        return None
    return _parse_av_date(bucket[0].get("fiscalDateEnding"))


def _fundamentals_source_id(
    *,
    source: str,
    symbol: str,
    field_code: str,
    asof: datetime | None,
) -> str:
    """Stable footnote ID — ``{PREFIX}-{FIELD}-{SYMBOL}-{YYYY-MM-DD}``."""
    prefix = _SOURCE_PREFIX.get(source.lower(), source.upper())
    asof_day = (asof or datetime.now(UTC)).strftime("%Y-%m-%d")
    return f"{prefix}-{field_code}-{symbol.upper()}-{asof_day}"


def _append_source_footnote(
    body: str,
    *,
    source: str,
    symbol: str,
    field_code: str,
    asof: datetime | None,
) -> str:
    """Append the provenance line. Mirrors quote-tool format exactly."""
    sid = _fundamentals_source_id(
        source=source, symbol=symbol, field_code=field_code, asof=asof
    )
    asof_repr = asof.strftime("%Y-%m-%dT%H:%MZ") if asof else "asof unknown"
    return f"{body}\n\nSource: {source} [{sid}] asof {asof_repr}"


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
        av_error: str | None = None
        try:
            data = await service.get_company_overview(symbol)
            if data and "Symbol" in data:
                body = formatter.format_company_overview(
                    raw_data=data,
                    symbol=symbol,
                    invoked_at=datetime.now(UTC).isoformat(),
                )
                # AV OVERVIEW carries `LatestQuarter` (e.g. "2025-09-30"),
                # which is the truthful asof for the snapshot. Fall back
                # to "now" if the field is missing or malformed.
                asof = _parse_av_date(data.get("LatestQuarter")) or datetime.now(UTC)
                return _append_source_footnote(
                    body,
                    source="alphavantage",
                    symbol=symbol,
                    field_code="OV",
                    asof=asof,
                )
            av_error = "Alpha Vantage returned empty response"
        except Exception as e:
            av_error = str(e)
            logger.warning(
                "company_overview_av_failed_trying_yf",
                symbol=symbol,
                error=av_error,
            )

        # Fallback: yfinance
        yf_md = await fetch_overview_yf(symbol)
        if yf_md is not None:
            return _append_source_footnote(
                yf_md,
                source="yfinance",
                symbol=symbol,
                field_code="OV",
                asof=datetime.now(UTC),
            )
        return unavailable_message(symbol, "Company overview", av_error=av_error)

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
        av_error: str | None = None
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
                if data:
                    body = formatter.format_cash_flow(
                        raw_data=data,
                        symbol=symbol,
                        invoked_at=datetime.now(UTC).isoformat(),
                        count=count,
                        period=period,
                    )
                    asof = _statement_asof(data, period=period) or datetime.now(UTC)
                    return _append_source_footnote(
                        body,
                        source="alphavantage",
                        symbol=symbol,
                        field_code="CF",
                        asof=asof,
                    )
                av_error = "Alpha Vantage returned empty cash flow"
            else:
                data = await service.get_balance_sheet(symbol)
                if data:
                    body = formatter.format_balance_sheet(
                        raw_data=data,
                        symbol=symbol,
                        invoked_at=datetime.now(UTC).isoformat(),
                        count=count,
                        period=period,
                    )
                    asof = _statement_asof(data, period=period) or datetime.now(UTC)
                    return _append_source_footnote(
                        body,
                        source="alphavantage",
                        symbol=symbol,
                        field_code="BS",
                        asof=asof,
                    )
                av_error = "Alpha Vantage returned empty balance sheet"
        except Exception as e:
            av_error = str(e)
            logger.warning(
                "financial_statements_av_failed_trying_yf",
                symbol=symbol,
                statement_type=statement_type,
                error=av_error,
            )

        # Fallback: yfinance
        if statement_type == "cash_flow":
            yf_md = await fetch_cash_flow_yf(symbol, count=count, period=period)
            label = "Cash flow"
            field_code = "CF"
        else:
            yf_md = await fetch_balance_sheet_yf(symbol, count=count, period=period)
            label = "Balance sheet"
            field_code = "BS"
        if yf_md is not None:
            return _append_source_footnote(
                yf_md,
                source="yfinance",
                symbol=symbol,
                field_code=field_code,
                asof=datetime.now(UTC),
            )
        return unavailable_message(symbol, label, av_error=av_error)

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
        av_error: str | None = None
        try:
            data = await service.get_insider_transactions(symbol, limit)
            if data and data.get("data"):
                body = formatter.format_insider_transactions(
                    raw_data=data,
                    symbol=symbol,
                    invoked_at=datetime.now(UTC).isoformat(),
                )
                # AV insider rows carry `transaction_date`; pick the most
                # recent (rows are returned newest-first per AV contract).
                rows = data.get("data") or []
                asof = _parse_av_date(
                    rows[0].get("transaction_date") if rows else None
                ) or datetime.now(UTC)
                return _append_source_footnote(
                    body,
                    source="alphavantage",
                    symbol=symbol,
                    field_code="INS",
                    asof=asof,
                )
            av_error = "Alpha Vantage returned empty insider data"
        except Exception as e:
            av_error = str(e)
            logger.warning(
                "insider_activity_av_failed_trying_yf",
                symbol=symbol,
                error=av_error,
            )

        yf_md = await fetch_insider_yf(symbol, limit=limit)
        if yf_md is not None:
            return _append_source_footnote(
                yf_md,
                source="yfinance",
                symbol=symbol,
                field_code="INS",
                asof=datetime.now(UTC),
            )
        return unavailable_message(symbol, "Insider activity", av_error=av_error)

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
        av_error: str | None = None
        try:
            data = await service.get_earnings(symbol)
            if data:
                body = formatter.format_earnings(
                    raw_data=data,
                    symbol=symbol,
                    invoked_at=datetime.now(UTC).isoformat(),
                )
                # Latest reported date from `quarterlyEarnings[0]`. The AV
                # contract puts most recent first; field is `reportedDate`
                # with `fiscalDateEnding` as fallback.
                quarters = data.get("quarterlyEarnings") or []
                latest = quarters[0] if quarters else {}
                asof = (
                    _parse_av_date(latest.get("reportedDate"))
                    or _parse_av_date(latest.get("fiscalDateEnding"))
                    or datetime.now(UTC)
                )
                return _append_source_footnote(
                    body,
                    source="alphavantage",
                    symbol=symbol,
                    field_code="EAR",
                    asof=asof,
                )
            av_error = "Alpha Vantage returned empty earnings"
        except Exception as e:
            av_error = str(e)
            logger.warning(
                "earnings_av_failed_trying_yf", symbol=symbol, error=av_error
            )

        yf_md = await fetch_earnings_yf(symbol)
        if yf_md is not None:
            return _append_source_footnote(
                yf_md,
                source="yfinance",
                symbol=symbol,
                field_code="EAR",
                asof=datetime.now(UTC),
            )
        return unavailable_message(symbol, "Earnings", av_error=av_error)

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
