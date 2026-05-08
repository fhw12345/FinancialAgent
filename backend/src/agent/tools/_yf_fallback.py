"""yfinance fallback for fundamentals tools (W1.4).

When the Alpha Vantage primary path returns empty (rate-limit, missing
ticker coverage, network), these helpers use yfinance to fetch the
equivalent data and format it as markdown for ReAct consumption.

Why a separate module:
  - Keeps Alpha-Vantage tool code unchanged in the happy path.
  - Single owner of the yfinance schema mapping (small caps and IPOs
    return None for many fields — must be handled once, not in every
    tool).
  - The output markdown carries a visible source banner so the LLM
    knows the data is degraded; downstream consistency_gate (W1.10)
    will use this signal to refuse valuation claims when data is from
    a low-coverage source.

Each helper returns either a markdown string (success, possibly
partial) or None (fully unavailable — caller renders an explicit
"unavailable" message that downstream gates can reject).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


SOURCE_BANNER = (
    "> ⚠️ **Data source: yfinance** (Alpha Vantage unavailable). "
    "Coverage is best-effort and may be sparse for IPOs / small caps. "
    "**Asof:** {asof}\n\n"
)


def _banner() -> str:
    return SOURCE_BANNER.format(asof=datetime.now(UTC).isoformat(timespec="seconds"))


def _fmt_num(value: Any, prefix: str = "", suffix: str = "", precision: int = 2) -> str:
    """Format a number with thousands separators; return em-dash when missing."""
    if value is None or value == "" or (isinstance(value, float) and value != value):
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(v) >= 1e9:
        return f"{prefix}{v / 1e9:.{precision}f}B{suffix}"
    if abs(v) >= 1e6:
        return f"{prefix}{v / 1e6:.{precision}f}M{suffix}"
    return f"{prefix}{v:,.{precision}f}{suffix}"


def _fmt_pct(value: Any) -> str:
    """yfinance returns ratios (0.4153) for margins; render as 41.53%."""
    if value is None or value == "":
        return "—"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "—"


# ---------------------------------------------------------------------------
# Public async helpers (each runs blocking yfinance in a thread)
# ---------------------------------------------------------------------------


async def fetch_overview_yf(symbol: str) -> str | None:
    """Company overview via yfinance.Ticker.info. Returns markdown or None."""

    def _sync() -> dict[str, Any] | None:
        import yfinance as yf

        try:
            info = yf.Ticker(symbol).info or {}
        except Exception as e:
            logger.warning("yf_overview_fetch_failed", symbol=symbol, error=str(e))
            return None
        # yfinance returns a stub dict (just `symbol`/`underlyingSymbol`) for
        # tickers it doesn't cover. Treat that as unavailable.
        if not info or len(info) <= 3 or not info.get("longName"):
            return None
        return info

    info = await asyncio.to_thread(_sync)
    if info is None:
        return None

    rows = [
        ("Name", info.get("longName") or info.get("shortName")),
        ("Sector", info.get("sector")),
        ("Industry", info.get("industry")),
        ("Market Cap", _fmt_num(info.get("marketCap"), prefix="$")),
        ("P/E (trailing)", _fmt_num(info.get("trailingPE"), precision=2)),
        ("P/E (forward)", _fmt_num(info.get("forwardPE"), precision=2)),
        ("EPS (trailing)", _fmt_num(info.get("trailingEps"), prefix="$")),
        ("Profit Margin", _fmt_pct(info.get("profitMargins"))),
        ("Revenue (TTM)", _fmt_num(info.get("totalRevenue"), prefix="$")),
        ("Beta", _fmt_num(info.get("beta"), precision=2)),
        ("52W High", _fmt_num(info.get("fiftyTwoWeekHigh"), prefix="$")),
        ("52W Low", _fmt_num(info.get("fiftyTwoWeekLow"), prefix="$")),
        ("Held by Insiders", _fmt_pct(info.get("heldPercentInsiders"))),
        ("Held by Institutions", _fmt_pct(info.get("heldPercentInstitutions"))),
        ("Dividend Yield", _fmt_pct(info.get("dividendYield"))),
        ("Analyst Mean Target", _fmt_num(info.get("targetMeanPrice"), prefix="$")),
        ("Analyst Count", info.get("numberOfAnalystOpinions") or "—"),
    ]
    table = "\n".join(f"- **{k}:** {v}" for k, v in rows if v is not None)

    desc = (info.get("longBusinessSummary") or "").strip()
    desc_block = (
        f"\n\n**Description:** {desc[:500]}{'…' if len(desc) > 500 else ''}\n"
        if desc
        else ""
    )

    return f"{_banner()}# {symbol.upper()} — Company Overview (yfinance)\n\n{table}{desc_block}"


async def fetch_cash_flow_yf(
    symbol: str, count: int = 3, period: str = "quarter"
) -> str | None:
    """Cash flow via yfinance.Ticker.cashflow / quarterly_cashflow."""

    def _sync():
        import yfinance as yf

        try:
            t = yf.Ticker(symbol)
            df = t.quarterly_cashflow if period == "quarter" else t.cashflow
        except Exception as e:
            logger.warning("yf_cashflow_fetch_failed", symbol=symbol, error=str(e))
            return None
        if df is None or df.empty:
            return None
        return df

    df = await asyncio.to_thread(_sync)
    if df is None:
        return None

    cols = list(df.columns)[:count]
    keys = [
        (
            "Operating Cash Flow",
            ["Operating Cash Flow", "Total Cash From Operating Activities"],
        ),
        ("Capital Expenditure", ["Capital Expenditure", "Capital Expenditures"]),
        ("Free Cash Flow", ["Free Cash Flow"]),
        ("Net Income", ["Net Income From Continuing Operations", "Net Income"]),
        ("Cash Dividends Paid", ["Cash Dividends Paid"]),
    ]
    header = "| Metric | " + " | ".join(c.strftime("%Y-%m-%d") for c in cols) + " |"
    sep = "|" + "---|" * (len(cols) + 1)
    body_rows = []
    for label, candidates in keys:
        row_idx = next((k for k in candidates if k in df.index), None)
        if row_idx is None:
            cells = ["—"] * len(cols)
        else:
            cells = [_fmt_num(df.loc[row_idx, c], prefix="$") for c in cols]
        body_rows.append(f"| {label} | " + " | ".join(cells) + " |")

    return (
        f"{_banner()}# {symbol.upper()} — Cash Flow ({period}, yfinance)\n\n"
        f"{header}\n{sep}\n" + "\n".join(body_rows) + "\n"
    )


async def fetch_balance_sheet_yf(
    symbol: str, count: int = 3, period: str = "quarter"
) -> str | None:
    """Balance sheet via yfinance.Ticker.balance_sheet / quarterly_balance_sheet."""

    def _sync():
        import yfinance as yf

        try:
            t = yf.Ticker(symbol)
            df = t.quarterly_balance_sheet if period == "quarter" else t.balance_sheet
        except Exception as e:
            logger.warning("yf_balance_sheet_fetch_failed", symbol=symbol, error=str(e))
            return None
        if df is None or df.empty:
            return None
        return df

    df = await asyncio.to_thread(_sync)
    if df is None:
        return None

    cols = list(df.columns)[:count]
    keys = [
        ("Total Assets", ["Total Assets"]),
        (
            "Total Liabilities",
            ["Total Liabilities Net Minority Interest", "Total Liab"],
        ),
        ("Stockholders Equity", ["Stockholders Equity", "Total Stockholder Equity"]),
        ("Cash & Equivalents", ["Cash And Cash Equivalents", "Cash"]),
        ("Total Debt", ["Total Debt"]),
        ("Current Assets", ["Current Assets", "Total Current Assets"]),
        ("Current Liabilities", ["Current Liabilities", "Total Current Liabilities"]),
    ]
    header = "| Metric | " + " | ".join(c.strftime("%Y-%m-%d") for c in cols) + " |"
    sep = "|" + "---|" * (len(cols) + 1)
    body_rows = []
    for label, candidates in keys:
        row_idx = next((k for k in candidates if k in df.index), None)
        if row_idx is None:
            cells = ["—"] * len(cols)
        else:
            cells = [_fmt_num(df.loc[row_idx, c], prefix="$") for c in cols]
        body_rows.append(f"| {label} | " + " | ".join(cells) + " |")

    return (
        f"{_banner()}# {symbol.upper()} — Balance Sheet ({period}, yfinance)\n\n"
        f"{header}\n{sep}\n" + "\n".join(body_rows) + "\n"
    )


async def fetch_earnings_yf(symbol: str, limit: int = 8) -> str | None:
    """Earnings history via yfinance.Ticker.earnings_dates."""

    def _sync():
        import yfinance as yf

        try:
            df = yf.Ticker(symbol).earnings_dates
        except Exception as e:
            logger.warning("yf_earnings_fetch_failed", symbol=symbol, error=str(e))
            return None
        if df is None or df.empty:
            return None
        return df

    df = await asyncio.to_thread(_sync)
    if df is None:
        return None

    df = df.head(limit)
    rows = []
    for ts, row in df.iterrows():
        eps_est = row.get("EPS Estimate")
        eps_act = row.get("Reported EPS")
        surprise = row.get("Surprise(%)")
        rows.append(
            f"| {ts.strftime('%Y-%m-%d')} | "
            f"{_fmt_num(eps_est, prefix='$', precision=2)} | "
            f"{_fmt_num(eps_act, prefix='$', precision=2)} | "
            f"{_fmt_pct(surprise / 100 if isinstance(surprise, (int, float)) else None)} |"
        )

    return (
        f"{_banner()}# {symbol.upper()} — Earnings History (yfinance)\n\n"
        "| Date | EPS Est | EPS Reported | Surprise |\n|---|---|---|---|\n"
        + "\n".join(rows)
        + "\n"
    )


async def fetch_insider_yf(symbol: str, limit: int = 50) -> str | None:
    """Insider transactions via yfinance.Ticker.insider_transactions.

    Returns a brief markdown table. NOTE: this fallback does NOT
    distinguish 10b5-1 vs discretionary — that distinction requires
    SEC EDGAR Form 4 footnote parsing, which is W3.8/W3.9.
    """

    def _sync():
        import yfinance as yf

        try:
            df = yf.Ticker(symbol).insider_transactions
        except Exception as e:
            logger.warning("yf_insider_fetch_failed", symbol=symbol, error=str(e))
            return None
        if df is None or df.empty:
            return None
        return df

    df = await asyncio.to_thread(_sync)
    if df is None:
        return None

    df = df.head(limit)
    rows = []
    for _, row in df.iterrows():
        date = row.get("Start Date") or row.get("Date") or ""
        date_s = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)
        rows.append(
            f"| {date_s} | {row.get('Insider', '')} | {row.get('Position', '')} | "
            f"{row.get('Transaction', '')} | {_fmt_num(row.get('Shares'))} | "
            f"{_fmt_num(row.get('Value'), prefix='$')} |"
        )

    note = (
        "\n\n> Note: 10b5-1 vs discretionary classification not available in "
        "yfinance fallback. Treat all transactions as `plan_type=unknown` "
        "until SEC EDGAR Form 4 parsing is wired (W3.8/W3.9).\n"
    )
    return (
        f"{_banner()}# {symbol.upper()} — Insider Transactions (yfinance)\n\n"
        "| Date | Insider | Role | Transaction | Shares | Value |\n"
        "|---|---|---|---|---|---|\n" + "\n".join(rows) + note
    )


def unavailable_message(symbol: str, what: str, *, av_error: str | None = None) -> str:
    """Render a final 'data unavailable' message after both providers fail.

    The wording is intentionally explicit so the consistency gate (W1.10)
    can pattern-match and refuse downstream valuation claims that depend
    on the missing field.
    """
    av_part = f" Alpha Vantage error: {av_error}." if av_error else ""
    return (
        f"⚠️ **{what} unavailable for {symbol}.**{av_part} "
        f"yfinance fallback also returned no data. Treat any downstream "
        f"claim that references {what.lower()} for {symbol} as "
        f"unsubstantiated."
    )
