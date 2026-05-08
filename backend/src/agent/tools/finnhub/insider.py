"""Finnhub-backed insider trades tool."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from langchain_core.tools import tool

logger = structlog.get_logger()


_DATE_KEYS = ("transactionDate", "filingDate", "Date", "Start Date")
_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ")


def _row_date_str(row: dict[str, Any]) -> str:
    for k in _DATE_KEYS:
        v = row.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def _parse_row_date(raw: str) -> datetime | None:
    """Best-effort parse of mixed-shape provider date strings.

    Finnhub returns ``YYYY-MM-DD``; AV's premium INSIDER_TRANSACTIONS
    endpoint can return either ``YYYY-MM-DD`` or ISO with seconds;
    yfinance renders datetimes via ``DataFrame.to_dict()`` which can
    yield ``YYYY-MM-DDTHH:MM:SS``. Bad / empty values yield ``None`` so
    a single bad row never kills the footnote.
    """
    if not raw:
        return None
    raw = raw.strip()
    if raw.endswith("Z"):
        raw = raw[:-1]
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw[: len(fmt) + 5], fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _insider_latest_asof(rows: list[dict[str, Any]]) -> datetime | None:
    latest: datetime | None = None
    for r in rows:
        dt = _parse_row_date(_row_date_str(r))
        if dt is None:
            continue
        if latest is None or dt > latest:
            latest = dt
    return latest


def _insider_source_id(provider: str, symbol: str, asof: datetime | None) -> str:
    """W3.5 stable footnote ID — ``{PREFIX}-INS-{SYMBOL}-{YYYY-MM-DD}``.

    Mirrors W3.4's news helper: ``asof`` is the latest *transaction*
    date, not when the tool ran, so a stale insider bucket is still
    recognizable as stale at citation time. Provider attribution
    defaults to "finnhub" (the primary in DataManager._fetch_insider_trades);
    finer post-fallback attribution is a follow-up.
    """
    prefix = {"finnhub": "FH", "alphavantage": "AV", "yfinance": "YF"}.get(
        provider.lower(), provider.upper()
    )
    asof_day = (asof or datetime.now(UTC)).strftime("%Y-%m-%d")
    return f"{prefix}-INS-{symbol.upper()}-{asof_day}"


def create_finnhub_insider_tool(data_manager: object) -> list:
    """Build the finnhub_insider_trades LangChain tool."""

    @tool
    async def finnhub_insider_trades(symbol: str) -> str:
        """
        Get recent insider transactions for a US-listed symbol.

        Provider chain: Finnhub (primary) → Alpha Vantage (premium endpoint, may 403) → yfinance.
        Returns insider name, share count, transaction code, and date.
        Use to check whether company insiders are buying or selling.
        """
        try:
            rows = await data_manager.get_insider_trades(symbol)  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("finnhub_insider_tool_failed", symbol=symbol, error=str(e))
            return f"Failed to fetch insider trades for {symbol}: {e}"

        if not rows:
            return f"No recent insider transactions found for {symbol}."

        lines = [f"{symbol} recent insider transactions ({len(rows)} rows):"]
        for r in rows[:10]:
            name = r.get("name") or r.get("Insider") or "?"
            share = r.get("share") or r.get("Shares") or r.get("change") or "?"
            code = (
                r.get("transactionCode")
                or r.get("Transaction")
                or r.get("transaction_code")
                or ""
            )
            date = _row_date_str(r)
            lines.append(f"- [{date}] {name}: {share} shares ({code})")

        # W3.5 provenance footnote. Provider attribution defaults to
        # "finnhub" (the primary in DataManager._fetch_insider_trades);
        # finer-grained AV/yfinance attribution after fallback is a
        # follow-up. asof is the latest transaction date so a stale
        # bucket is still recognizable as stale at citation time.
        latest_dt = _insider_latest_asof(rows) or datetime.now(UTC)
        sid = _insider_source_id("finnhub", symbol, latest_dt)
        asof_repr = latest_dt.strftime("%Y-%m-%dT%H:%MZ")
        lines.append("")
        lines.append(f"Source: finnhub [{sid}] asof {asof_repr}")
        return "\n".join(lines)

    return [finnhub_insider_trades]
