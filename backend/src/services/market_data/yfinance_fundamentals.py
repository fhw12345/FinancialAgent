"""
Fundamentals via yfinance — primary source for company overview, cash flow,
balance sheet, and news sentiment endpoints.

Used as the primary fetcher because Alpha Vantage's free tier (25 requests/day)
runs out instantly and most fundamentals endpoints (`OVERVIEW`, `CASH_FLOW`,
`BALANCE_SHEET`, `NEWS_SENTIMENT`) are now premium-only — free keys get back
a single-key payload `{"Information": "premium endpoint..."}`.

Output dict shape mirrors `AlphaVantageMarketDataService.get_*()` so the route
handler and downstream consumers don't need to know which source produced the
data. Fields yfinance can't supply (e.g. `PercentInsiders`) are included with
the AV `"None"` sentinel string so downstream `safe_float()` calls produce
the same `null` they would for AV.

News sentiment uses VADER (lexicon-based, no API key, runs offline) for
per-article sentiment because yfinance's `Ticker.news` doesn't include scores.
This is less accurate than Alpha Vantage's ML model but still usable for the
positive/negative bucketing the front-end needs.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import structlog
import yfinance as yf

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _av_str(value: Any) -> str:
    """Render a number as the string format AV uses; missing → 'None'."""
    if value is None or value == "":
        return "None"
    if isinstance(value, float) and value != value:  # NaN
        return "None"
    return str(value)


def _row_value(df: pd.DataFrame, candidates: list[str], col: Any) -> Any:
    """Find the first matching row name and return df.loc[row, col], else None."""
    for c in candidates:
        if c in df.index:
            v = df.loc[c, col]
            if pd.isna(v):
                return None
            return v
    return None


# ---------------------------------------------------------------------------
# Company overview — yfinance Ticker.info → AV OVERVIEW shape
# ---------------------------------------------------------------------------


def _overview_sync(symbol: str) -> dict[str, Any]:
    info = yf.Ticker(symbol).info or {}
    # yfinance returns a stub for unknown tickers — treat it as "no data"
    # so callers can fall back to AV.
    if not info or len(info) <= 3 or not info.get("longName"):
        raise RuntimeError(f"yfinance has no overview data for {symbol}")
    return {
        "Symbol": symbol.upper(),
        "Name": info.get("longName") or info.get("shortName") or "",
        "Description": info.get("longBusinessSummary") or "",
        "Industry": info.get("industry") or "",
        "Sector": info.get("sector") or "",
        "Exchange": info.get("exchange") or "",
        "Country": info.get("country") or "",
        "Currency": info.get("currency") or "USD",
        "MarketCapitalization": _av_str(info.get("marketCap")),
        "PERatio": _av_str(info.get("trailingPE")),
        "ForwardPE": _av_str(info.get("forwardPE")),
        "EPS": _av_str(info.get("trailingEps")),
        "ProfitMargin": _av_str(info.get("profitMargins")),
        "RevenueTTM": _av_str(info.get("totalRevenue")),
        "DividendYield": _av_str(info.get("dividendYield")),
        "Beta": _av_str(info.get("beta")),
        "52WeekHigh": _av_str(info.get("fiftyTwoWeekHigh")),
        "52WeekLow": _av_str(info.get("fiftyTwoWeekLow")),
        "PercentInsiders": _av_str(
            (info.get("heldPercentInsiders") or 0) * 100
            if info.get("heldPercentInsiders") is not None
            else None
        ),
        "PercentInstitutions": _av_str(
            (info.get("heldPercentInstitutions") or 0) * 100
            if info.get("heldPercentInstitutions") is not None
            else None
        ),
        "AnalystTargetPrice": _av_str(info.get("targetMeanPrice")),
        "_source": "yfinance",
    }


async def get_company_overview(symbol: str) -> dict[str, Any]:
    return await asyncio.to_thread(_overview_sync, symbol)


# ---------------------------------------------------------------------------
# Cash flow — yfinance DataFrame → AV annualReports/quarterlyReports
# ---------------------------------------------------------------------------


_CASH_FLOW_FIELDS: list[tuple[str, list[str]]] = [
    # AV key, yfinance row candidates
    (
        "operatingCashflow",
        ["Operating Cash Flow", "Total Cash From Operating Activities"],
    ),
    ("capitalExpenditures", ["Capital Expenditure", "Capital Expenditures"]),
    ("dividendPayout", ["Cash Dividends Paid", "Common Stock Dividend Paid"]),
    (
        "cashflowFromInvestment",
        ["Investing Cash Flow", "Total Cashflows From Investing Activities"],
    ),
    (
        "cashflowFromFinancing",
        ["Financing Cash Flow", "Total Cash From Financing Activities"],
    ),
    ("netIncome", ["Net Income From Continuing Operations", "Net Income"]),
]


def _df_to_reports(
    df: pd.DataFrame, fields: list[tuple[str, list[str]]]
) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    reports = []
    for col in df.columns:
        report: dict[str, Any] = {
            "fiscalDateEnding": (
                col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
            ),
        }
        for av_key, candidates in fields:
            v = _row_value(df, candidates, col)
            report[av_key] = _av_str(int(v) if isinstance(v, (int, float)) else v)
        reports.append(report)
    return reports


def _cash_flow_sync(symbol: str) -> dict[str, Any]:
    t = yf.Ticker(symbol)
    annual = _df_to_reports(t.cashflow, _CASH_FLOW_FIELDS)
    quarterly = _df_to_reports(t.quarterly_cashflow, _CASH_FLOW_FIELDS)
    if not annual and not quarterly:
        raise RuntimeError(f"yfinance has no cash flow data for {symbol}")
    return {
        "symbol": symbol.upper(),
        "annualReports": annual,
        "quarterlyReports": quarterly,
        "_source": "yfinance",
    }


async def get_cash_flow(symbol: str) -> dict[str, Any]:
    return await asyncio.to_thread(_cash_flow_sync, symbol)


# ---------------------------------------------------------------------------
# Balance sheet — yfinance DataFrame → AV annualReports/quarterlyReports
# ---------------------------------------------------------------------------


_BALANCE_SHEET_FIELDS: list[tuple[str, list[str]]] = [
    ("totalAssets", ["Total Assets"]),
    ("totalLiabilities", ["Total Liabilities Net Minority Interest", "Total Liab"]),
    ("totalShareholderEquity", ["Stockholders Equity", "Total Stockholder Equity"]),
    ("totalCurrentAssets", ["Current Assets", "Total Current Assets"]),
    ("totalCurrentLiabilities", ["Current Liabilities", "Total Current Liabilities"]),
    ("cashAndCashEquivalentsAtCarryingValue", ["Cash And Cash Equivalents", "Cash"]),
    ("currentAssets", ["Current Assets", "Total Current Assets"]),
    ("currentLiabilities", ["Current Liabilities", "Total Current Liabilities"]),
    ("inventory", ["Inventory"]),
    ("currentNetReceivables", ["Receivables", "Net Receivables"]),
    ("longTermDebt", ["Long Term Debt"]),
]


def _balance_sheet_sync(symbol: str) -> dict[str, Any]:
    t = yf.Ticker(symbol)
    annual = _df_to_reports(t.balance_sheet, _BALANCE_SHEET_FIELDS)
    quarterly = _df_to_reports(t.quarterly_balance_sheet, _BALANCE_SHEET_FIELDS)
    if not annual and not quarterly:
        raise RuntimeError(f"yfinance has no balance sheet data for {symbol}")
    return {
        "symbol": symbol.upper(),
        "annualReports": annual,
        "quarterlyReports": quarterly,
        "_source": "yfinance",
    }


async def get_balance_sheet(symbol: str) -> dict[str, Any]:
    return await asyncio.to_thread(_balance_sheet_sync, symbol)


# ---------------------------------------------------------------------------
# News sentiment — yfinance Ticker.news + VADER local sentiment
# ---------------------------------------------------------------------------

_vader_analyzer = None


def _get_vader():
    """Lazy-load VADER (downloads NLTK lexicon on first use)."""
    global _vader_analyzer
    if _vader_analyzer is None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        _vader_analyzer = SentimentIntensityAnalyzer()
    return _vader_analyzer


def _vader_score(text: str) -> tuple[float, str]:
    """Return (compound_score in [-1,1], AV-style label)."""
    if not text:
        return 0.0, "Neutral"
    score = _get_vader().polarity_scores(text)["compound"]
    if score >= 0.35:
        label = "Bullish"
    elif score >= 0.15:
        label = "Somewhat-Bullish"
    elif score <= -0.35:
        label = "Bearish"
    elif score <= -0.15:
        label = "Somewhat-Bearish"
    else:
        label = "Neutral"
    return score, label


def _news_sync(symbol: str, limit: int) -> dict[str, Any]:
    raw = yf.Ticker(symbol).news or []
    if not raw:
        raise RuntimeError(f"yfinance has no news for {symbol}")
    feed: list[dict[str, Any]] = []
    for item in raw[:limit]:
        # yfinance has shipped two shapes over time; handle both.
        content = item.get("content") if isinstance(item, dict) else None
        if isinstance(content, dict):
            title = content.get("title", "")
            url = (
                (content.get("clickThroughUrl") or {}).get("url")
                or (content.get("canonicalUrl") or {}).get("url")
                or ""
            )
            source = (content.get("provider") or {}).get("displayName", "")
            published = content.get("pubDate") or ""
            summary = content.get("summary") or content.get("description") or ""
        else:
            title = item.get("title", "")
            url = item.get("link", "")
            source = item.get("publisher", "")
            ts = item.get("providerPublishTime")
            published = (
                datetime.fromtimestamp(ts, UTC).strftime("%Y%m%dT%H%M%S")
                if isinstance(ts, (int, float))
                else ""
            )
            summary = item.get("summary", "") or ""
        score, label = _vader_score(f"{title}. {summary}")
        feed.append(
            {
                "title": title,
                "url": url,
                "source": source,
                "time_published": published,
                "summary": summary,
                "overall_sentiment_score": score,
                "overall_sentiment_label": label,
                "ticker_sentiment": [
                    {
                        "ticker": symbol.upper(),
                        "ticker_sentiment_score": str(score),
                        "ticker_sentiment_label": label,
                    }
                ],
            }
        )
    return {
        "feed": feed,
        "sentiment_score_definition": (
            "Local VADER lexicon sentiment (yfinance fallback). "
            "Bullish ≥ 0.35, Somewhat-Bullish ≥ 0.15, Neutral, "
            "Somewhat-Bearish ≤ -0.15, Bearish ≤ -0.35."
        ),
        "_source": "yfinance",
    }


async def get_news_sentiment(tickers: str, limit: int = 50) -> dict[str, Any]:
    """Fetch news for the first ticker only (route only passes one symbol)."""
    symbol = tickers.split(",")[0].strip()
    return await asyncio.to_thread(_news_sync, symbol, limit)
