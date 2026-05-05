"""
Base helpers for Alpha Vantage response formatting.

Provides common utilities used across all formatter modules.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.shared.formatters import (
    calculate_qoq_growth,
    format_large_number,
    safe_float,
)


def generate_metadata_header(
    tool_name: str, symbol: str | None, invoked_at: str, data_source: str
) -> str:
    """
    Generate metadata header for tool output.

    Args:
        tool_name: Name of the tool (e.g., "Cash Flow Analysis")
        symbol: Stock symbol (optional)
        invoked_at: ISO timestamp of invocation
        data_source: API endpoint name

    Returns:
        Formatted metadata header
    """
    lines = [
        "---",
        f"**Tool:** {tool_name}",
    ]

    if symbol:
        lines.append(f"**Symbol:** {symbol}")

    lines.extend(
        [
            f"**Invoked:** {invoked_at}",
            f"**Data Source:** Alpha Vantage {data_source} API",
            "---",
            "",
        ]
    )

    return "\n".join(lines)


def extract_current_year_quarters(
    quarterly_reports: list[dict[str, Any]], current_year: int | None = None
) -> list[dict[str, Any]]:
    """
    Extract quarters from the current year.

    Args:
        quarterly_reports: List of quarterly reports from Alpha Vantage
        current_year: Year to filter (defaults to current year)

    Returns:
        List of quarters from current year, sorted chronologically
    """
    if current_year is None:
        current_year = datetime.now(ZoneInfo("Asia/Shanghai")).year

    current_year_quarters = [
        q
        for q in quarterly_reports
        if q.get("fiscalDateEnding", "").startswith(str(current_year))
    ]

    # Sort by fiscal date (chronological order)
    current_year_quarters.sort(key=lambda x: x.get("fiscalDateEnding", ""))

    return current_year_quarters


def get_quarter_label(fiscal_date_ending: str) -> str:
    """
    Convert fiscal date to quarter label (e.g., "Q1 2024").

    Args:
        fiscal_date_ending: Date string in YYYY-MM-DD format

    Returns:
        Quarter label string
    """
    if not fiscal_date_ending or len(fiscal_date_ending) < 7:
        return "Unknown"

    year = fiscal_date_ending[:4]
    month = int(fiscal_date_ending[5:7])
    quarter = (month - 1) // 3 + 1

    return f"Q{quarter} {year}"


# Re-export shared formatters for convenience
__all__ = [
    "generate_metadata_header",
    "extract_current_year_quarters",
    "get_quarter_label",
    "safe_float",
    "format_large_number",
    "calculate_qoq_growth",
]
