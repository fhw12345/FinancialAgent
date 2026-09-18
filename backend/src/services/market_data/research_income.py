"""Income statements for explicit research contracts; provider currency and signs stay visible."""

import asyncio
from typing import Any

import yfinance as yf

from .yfinance_fundamentals import _df_to_reports

FIELDS = [
    ("dilutedEPS", ["Diluted EPS"]),
    ("dilutedAverageShares", ["Diluted Average Shares"]),
    ("interestExpense", ["Interest Expense"]),
    ("totalRevenue", ["Total Revenue"]),
    ("netIncome", ["Net Income"]),
]


def _yahoo(symbol: str) -> dict[str, Any]:
    ticker = yf.Ticker(symbol)
    reports = _df_to_reports(ticker.income_stmt, FIELDS)
    if not reports:
        raise ValueError("Income statement unavailable")
    return {
        "symbol": symbol,
        "annualReports": reports,
        "reportedCurrency": (ticker.info or {}).get("financialCurrency"),
        "_source": "yfinance",
    }


async def fetch_income(service: Any, symbol: str) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(_yahoo, symbol)
    except Exception:
        if not service.api_key:
            raise
    response = await service.client.get(
        service.base_url,
        params={
            "function": "INCOME_STATEMENT",
            "symbol": symbol,
            "apikey": service.api_key,
        },
    )
    if response.status_code != 200:
        raise ValueError("Income provider unavailable")
    data = response.json()
    if not isinstance(data, dict) or "annualReports" not in data:
        raise ValueError("Income statement unavailable")
    return {**data, "_source": "alphavantage"}
