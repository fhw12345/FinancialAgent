"""
LangChain tools for Put/Call Ratio analysis.

Provides AI agent access to per-symbol PCR calculations with:
- ATM Dollar-Weighted methodology
- Automatic Redis caching (1-hour TTL)
- Rich output including price, ATM zone, notionals, interpretation
"""

import typing
from typing import TYPE_CHECKING

import structlog
from langchain_core.tools import tool

if TYPE_CHECKING:
    from ...services.data_manager import DataManager, SymbolPCRData

logger = structlog.get_logger()


def create_pcr_tools(data_manager: "DataManager") -> list[typing.Any]:
    """
    Create Put/Call Ratio tools for the LLM agent.

    These tools allow the agent to analyze options market sentiment
    for individual symbols using ATM dollar-weighted PCR methodology.

    Args:
        data_manager: DataManager instance for cached PCR calculations

    Returns:
        List of LangChain tools
    """

    @tool
    async def get_put_call_ratio(symbol: str) -> str:
        """
        Get the Put/Call Ratio for a stock symbol.

        Calculates ATM (at-the-money) dollar-weighted Put/Call Ratio:
        - Filters to options within 15% of current price
        - Requires minimum $0.50 premium and 500 open interest
        - Uses notional value: OI x Premium x 100

        PCR Interpretation (Contrarian):
        - PCR < 0.5: Extreme bullish sentiment -> Contrarian bearish signal
        - PCR 0.5-0.7: Bullish sentiment -> Cautionary signal
        - PCR 0.7-1.0: Moderate bullish -> Neutral
        - PCR 1.0-1.3: Moderate bearish -> Neutral
        - PCR 1.3-1.5: Bearish sentiment -> Contrarian optimistic
        - PCR > 1.5: Extreme fear -> Contrarian bullish signal

        Args:
            symbol: Stock symbol (e.g., "NVDA", "AAPL", "TSLA")

        Returns:
            Rich analysis including:
            - Current price and ATM zone range
            - Put and Call notional values
            - PCR ratio with interpretation
            - Number of contracts analyzed

        Example:
            get_put_call_ratio("NVDA")
        """
        try:
            pcr_data = await data_manager.get_symbol_pcr(symbol)

            if pcr_data is None:
                return (
                    f"Unable to calculate Put/Call Ratio for {symbol.upper()}. "
                    "This may be due to:\n"
                    "- Symbol not found or no options available\n"
                    "- Insufficient ATM options meeting quality filters\n"
                    "- Market data temporarily unavailable\n\n"
                    "Try a major stock with high options volume "
                    "(e.g., NVDA, AAPL, TSLA, GOOGL, META)."
                )

            return _format_pcr_output(pcr_data)

        except Exception as e:
            logger.error(
                "PCR tool error",
                symbol=symbol,
                error=str(e),
            )
            return f"Error calculating Put/Call Ratio for {symbol}: {str(e)}"

    return [get_put_call_ratio]


def _format_pcr_output(pcr_data: "SymbolPCRData") -> str:
    """Format PCR data as rich markdown output.

    Args:
        pcr_data: SymbolPCRData from DataManager

    Returns:
        Formatted markdown string
    """
    # Determine sentiment indicator
    if pcr_data.pcr < 0.7:
        sentiment_emoji = "🟢"  # Bullish (contrarian bearish)
    elif pcr_data.pcr < 1.0:
        sentiment_emoji = "🔵"  # Neutral-bullish
    elif pcr_data.pcr < 1.3:
        sentiment_emoji = "🟠"  # Neutral-bearish
    else:
        sentiment_emoji = "🔴"  # Bearish (contrarian bullish)

    lines = [
        f"## {pcr_data.symbol} Put/Call Ratio Analysis {sentiment_emoji}\n",
        "### Overview",
        "| Metric | Value |",
        "|--------|-------|",
        f"| **Current Price** | ${pcr_data.current_price:,.2f} |",
        f"| **ATM Zone** | ${pcr_data.atm_zone_low:,.2f} - ${pcr_data.atm_zone_high:,.2f} |",
        f"| **Put Notional** | ${pcr_data.put_notional_mm:.2f}M |",
        f"| **Call Notional** | ${pcr_data.call_notional_mm:.2f}M |",
        f"| **Contracts Analyzed** | {pcr_data.contracts_analyzed:,} |",
        "",
        "### Put/Call Ratio",
        f"**PCR: {pcr_data.pcr:.2f}** {sentiment_emoji}",
        "",
        f"📊 *{pcr_data.interpretation}*",
        "",
        "### Methodology",
        f"- ATM Zone: +/- {pcr_data.atm_zone_pct * 100:.0f}% of current price",
        f"- Min Premium: ${pcr_data.min_premium:.2f}",
        f"- Min Open Interest: {pcr_data.min_oi:,} contracts",
        "",
        f"---\n*Calculated: {pcr_data.calculated_at.strftime('%Y-%m-%d %H:%M UTC')}*",
    ]

    return "\n".join(lines)
