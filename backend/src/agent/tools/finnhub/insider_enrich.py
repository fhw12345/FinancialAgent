"""W3.10 insider-tool schema upgrade — Form 4 enrichment helpers.

This module is the pure-function bridge between the existing
``finnhub_insider_trades`` provider rows (Finnhub → AV → yfinance,
each in its own dict shape) and the W3.9 ``Form4Transaction`` records.
Three deliverables:

1. ``enrich_insider_rows(rows, form4_txs)`` — best-effort merges the
   Form 4 ``plan_type`` and ``shares_owned_after`` into each provider
   row by matching transaction date + shares.
2. ``compute_pct_of_holdings_after(row)`` — derived value: tx shares
   over post-tx total holdings, when both are present.
3. ``build_last_12mo_summary(form4_txs, anchor_date)`` — symbol-level
   12-month aggregate: total transactions, total shares, plan_type
   breakdown. Phase1 prompt's W3.11 discretionary-cluster rule reads
   this aggregate to decide bearish framing.

All helpers are sync, side-effect-free, and tolerant of missing /
malformed inputs — a single bad row never kills the enrichment pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Iterable

from src.agent.tools.sec_edgar.form4 import (
    PLAN_TYPE_10B5_1,
    PLAN_TYPE_DISCRETIONARY,
    PLAN_TYPE_UNKNOWN,
    Form4Transaction,
)


_DATE_KEYS = ("transactionDate", "filingDate", "Date", "Start Date")


def _row_date(row: dict[str, Any]) -> date | None:
    for k in _DATE_KEYS:
        v = row.get(k)
        if isinstance(v, str) and v:
            try:
                return date.fromisoformat(v[:10])
            except ValueError:
                continue
    return None


def _row_shares(row: dict[str, Any]) -> float | None:
    raw = row.get("share") or row.get("Shares") or row.get("change")
    if raw is None or raw == "":
        return None
    try:
        return float(str(raw).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _shares_match(a: float | None, b: float | None, tol: float = 1.0) -> bool:
    """A and B refer to the same transaction if their share counts
    agree within ``tol`` shares — Finnhub sometimes rounds to ints
    while Form 4 carries fractional shares for restricted-stock-unit
    vests."""
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def enrich_insider_rows(
    rows: list[dict[str, Any]], form4_txs: Iterable[Form4Transaction] | None
) -> list[dict[str, Any]]:
    """Return a NEW list with ``plan_type`` / ``shares_owned_after`` /
    ``pct_of_holdings_after`` keys merged in where matching Form 4 data
    exists. Rows without a match are returned unchanged. The input
    list is never mutated.

    Match heuristic: same transaction date AND share count within 1
    share. We intentionally don't match on transaction code because
    Finnhub uses different codes for sales (``S`` vs. ``Sale`` vs.
    plain ``"sell"``); the date+shares combo is enough in practice.
    """
    if not form4_txs:
        return [dict(r) for r in rows]
    by_date: dict[date, list[Form4Transaction]] = {}
    for tx in form4_txs:
        if tx.transaction_date is None:
            continue
        by_date.setdefault(tx.transaction_date, []).append(tx)

    enriched: list[dict[str, Any]] = []
    for r in rows:
        out = dict(r)
        d = _row_date(r)
        s = _row_shares(r)
        if d is not None and s is not None:
            for tx in by_date.get(d, []):
                if _shares_match(tx.shares, s):
                    out["plan_type"] = tx.plan_type
                    if tx.plan_adopted_date is not None:
                        out["plan_adopted_date"] = tx.plan_adopted_date.isoformat()
                    if tx.shares_owned_after is not None:
                        out["shares_owned_after"] = tx.shares_owned_after
                    pct = compute_pct_of_holdings_after(out)
                    if pct is not None:
                        out["pct_of_holdings_after"] = pct
                    break
        enriched.append(out)
    return enriched


def compute_pct_of_holdings_after(row: dict[str, Any]) -> float | None:
    """Tx shares over post-tx total holdings, expressed as 0..1 ratio.

    A SELL where pct_of_holdings_after = 0.05 means the insider sold
    5% of their *remaining* position. Returns ``None`` when either
    leg is missing — the prompt rule treats absence as "unknown" and
    skips the bearish framing.
    """
    shares = _row_shares(row)
    after = row.get("shares_owned_after")
    if shares is None or after is None:
        return None
    try:
        a = float(after)
    except (TypeError, ValueError):
        return None
    if a <= 0:
        return None
    return shares / a


@dataclass
class Last12moSummary:
    transaction_count: int
    plan_breakdown: dict[str, int]  # plan_type -> count
    total_shares: float

    def render(self) -> str:
        if self.transaction_count == 0:
            return "no insider transactions in last 12mo"
        parts = [f"{self.transaction_count} tx"]
        for plan in (PLAN_TYPE_10B5_1, PLAN_TYPE_DISCRETIONARY, PLAN_TYPE_UNKNOWN):
            n = self.plan_breakdown.get(plan, 0)
            if n:
                parts.append(f"{n} {plan}")
        if self.total_shares:
            parts.append(f"~{int(self.total_shares):,} shares total")
        return " · ".join(parts)


def build_last_12mo_summary(
    form4_txs: Iterable[Form4Transaction],
    anchor_date: date | None = None,
) -> Last12moSummary:
    """Symbol-level 12-month aggregate of insider transactions.

    ``anchor_date`` is the "today" reference; the window is the 365
    days immediately preceding it. Defaults to ``datetime.now(UTC)``
    when not supplied.
    """
    if anchor_date is None:
        anchor_date = datetime.now(UTC).date()
    cutoff = anchor_date - timedelta(days=365)
    plan_breakdown: dict[str, int] = {}
    count = 0
    total_shares = 0.0
    for tx in form4_txs:
        if tx.transaction_date is None:
            continue
        if tx.transaction_date < cutoff or tx.transaction_date > anchor_date:
            continue
        count += 1
        plan_breakdown[tx.plan_type] = plan_breakdown.get(tx.plan_type, 0) + 1
        if tx.shares is not None:
            total_shares += tx.shares
    return Last12moSummary(
        transaction_count=count,
        plan_breakdown=plan_breakdown,
        total_shares=total_shares,
    )


def render_enriched_row(row: dict[str, Any]) -> str:
    """Markdown line for a single enriched provider row.

    Shape: ``- [date] name: N shares (CODE) [plan_type] [pct]``. The
    last two segments only appear when the W3.10 enrichment populated
    them. Pre-enrichment rows render exactly as W3.5 did, preserving
    full back-compat.
    """
    name = row.get("name") or row.get("Insider") or "?"
    shares = row.get("share") or row.get("Shares") or row.get("change") or "?"
    code = (
        row.get("transactionCode")
        or row.get("Transaction")
        or row.get("transaction_code")
        or ""
    )
    d = _row_date(row)
    date_str = d.isoformat() if d else (row.get("transactionDate") or "")
    parts = [f"- [{date_str}] {name}: {shares} shares ({code})"]
    plan = row.get("plan_type")
    if plan and plan != PLAN_TYPE_UNKNOWN:
        parts.append(f"plan={plan}")
    pct = row.get("pct_of_holdings_after")
    if pct is not None:
        parts.append(f"{pct * 100:.1f}% of holdings after")
    return " · ".join(parts)
