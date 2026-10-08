"""Explicit current-session closing marks; reads only replay last-known receipts."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext

from ...models.paper_ledger import (
    ClosingMark,
    PaperEvent,
    PaperProjection,
    PaperValuation,
    ValuationInput,
)
from ..portfolio_risk import provider
from ..portfolio_risk.calendar import completed_session
from .accounting import PaperInvalid, cash_round, replay


async def mark(symbol: str, session: date) -> ClosingMark:
    asset = await provider.fetch_asset(symbol, session)
    error = None
    if asset.errors:
        error = "MARK_PROVIDER_UNAVAILABLE"
    elif asset.currency != "USD":
        error = "MARK_CURRENCY_UNSUPPORTED"
    elif asset.mark is None or asset.mark_session != session:
        error = "MARK_SESSION_UNAVAILABLE"
    price = None if error else format(Decimal(str(asset.mark)), "f")
    try:
        return ClosingMark(
            symbol=symbol,
            session_date=session,
            price=price,
            currency="USD" if not error else None,
            source=asset.source,
            error=error,
        )
    except ValueError:
        return ClosingMark(
            symbol=symbol,
            session_date=session,
            price=None,
            currency=None,
            source=asset.source,
            error="MARK_INVALID_PRECISION_OR_VALUE",
        )


async def capture(
    state: PaperProjection, sequence: int, session: date
) -> ValuationInput:
    semaphore = asyncio.Semaphore(4)

    async def fetch(symbol: str) -> ClosingMark:
        async with semaphore:
            return await mark(symbol, session)

    marks = await asyncio.gather(*(fetch(p.symbol) for p in state.positions))
    return ValuationInput(
        session_date=session,
        ledger_sequence=sequence,
        fetched_at=datetime.now(UTC),
        reconciliation="corporate-actions-inspected-through-this-session",
        marks=marks,
    )


def receipt(events: list[PaperEvent]) -> PaperValuation | None:
    entry = next(
        (e for e in reversed(events) if isinstance(e.payload, ValuationInput)), None
    )
    if entry is None or not isinstance(entry.payload, ValuationInput):
        return None
    payload = entry.payload
    settings, at_mark = replay(events[: entry.sequence - 1])
    _, current = replay(events)
    expected = {p.symbol for p in at_mark.positions}
    marks = {m.symbol: m for m in payload.marks}
    errors = []
    if len(marks) != len(payload.marks) or set(marks) != expected:
        errors.append("VALUATION_POSITION_SCOPE_MISMATCH")
    marked = 0
    market = Decimal(0)
    with localcontext() as context:
        context.prec = 50
        for position in at_mark.positions:
            row = marks.get(position.symbol)
            if (
                row is None
                or row.error
                or row.price is None
                or row.currency != "USD"
                or row.session_date != payload.session_date
            ):
                errors.append(
                    (row.error if row and row.error else "MARK_UNAVAILABLE")
                    + ":"
                    + position.symbol
                )
            else:
                marked += 1
                try:
                    market += cash_round(row.price * position.quantity)
                except PaperInvalid:
                    errors.append("VALUATION_MONEY_RANGE_EXCEEDED:" + position.symbol)
        try:
            nav = cash_round(at_mark.cash + market) if not errors else None
            pnl = cash_round(nav - settings.initial_cash) if nav is not None else None
        except PaperInvalid:
            errors.append("VALUATION_MONEY_RANGE_EXCEEDED")
            nav, pnl = None, None
    stale = []
    if current.last_ledger_sequence > payload.ledger_sequence:
        stale.append("PAPER_LEDGER_CHANGED")
    if completed_session(datetime.now(UTC)) != payload.session_date:
        stale.append("VALUATION_SESSION_CHANGED")
    return PaperValuation(
        session_date=payload.session_date,
        recorded_at=entry.recorded_at,
        status="unavailable" if errors else "complete",
        nav=nav,
        scenario_pnl=pnl,
        marked_positions=marked,
        total_positions=len(expected),
        errors=sorted(set(errors)),
        stale=bool(stale),
        stale_reasons=stale,
        marks=payload.marks,
    )
