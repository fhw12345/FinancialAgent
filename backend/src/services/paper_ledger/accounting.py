"""Pure event replay and FIFO bookkeeping. No real ledger, provider, model or clock I/O."""

from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from ...models.paper_ledger import (
    CloseInput,
    DividendInput,
    InitialInput,
    PaperEvent,
    PaperLot,
    PaperPosition,
    PaperProjection,
    PaperSettings,
    SplitInput,
    TradeInput,
)

CENT = Decimal("0.01")
MICRO = Decimal("0.000001")
MAX = Decimal("1000000000000000")


class PaperInvalid(ValueError):
    """Bounded user/accounting reason, never raw provider text."""


def cash_round(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        result = value.quantize(CENT, rounding=ROUND_HALF_EVEN)
    if not result.is_finite() or abs(result) > MAX:
        raise PaperInvalid("MONEY_RANGE_EXCEEDED")
    return result


def trade_amounts(
    settings: PaperSettings, trade: TradeInput
) -> tuple[Decimal, Decimal, Decimal]:
    with localcontext() as context:
        context.prec = 50
        direction = 1 if trade.side == "buy" else -1
        effective = trade.reference_price * (
            1 + direction * settings.slippage_bps / Decimal(10000)
        )
        principal = cash_round(trade.quantity * effective)
        fee = cash_round(principal * settings.commission_bps / Decimal(10000))
    if principal <= 0:
        raise PaperInvalid("TRADE_BELOW_CENT")
    return effective, principal, fee


def _trade(
    state: PaperProjection,
    settings: PaperSettings,
    event: PaperEvent,
    trade: TradeInput,
) -> None:
    _, principal, fee = trade_amounts(settings, trade)
    if trade.side == "buy":
        total = cash_round(principal + fee)
        if total > state.cash:
            raise PaperInvalid("PAPER_CASH_INSUFFICIENT")
        state.cash = cash_round(state.cash - total)
        state.lots.append(
            PaperLot(
                event_id=event.event_id,
                symbol=trade.symbol,
                quantity=trade.quantity,
                cost_basis=total,
            )
        )
    else:
        quantity = sum(
            (lot.quantity for lot in state.lots if lot.symbol == trade.symbol),
            Decimal(0),
        )
        if quantity < trade.quantity:
            raise PaperInvalid("PAPER_OVERSELL")
        remaining = trade.quantity
        basis = Decimal(0)
        kept = []
        for lot in state.lots:
            if lot.symbol != trade.symbol or remaining == 0:
                kept.append(lot)
                continue
            used = min(remaining, lot.quantity)
            # The final depletion takes the full residual cents, not another fraction.
            cost = (
                lot.cost_basis
                if used == lot.quantity
                else cash_round(lot.cost_basis * used / lot.quantity)
            )
            basis += cost
            remaining -= used
            if used < lot.quantity:
                kept.append(
                    PaperLot(
                        event_id=lot.event_id,
                        symbol=lot.symbol,
                        quantity=lot.quantity - used,
                        cost_basis=cash_round(lot.cost_basis - cost),
                    )
                )
        state.lots = kept
        state.cash = cash_round(state.cash + principal - fee)
        state.realized_pnl = cash_round(state.realized_pnl + principal - fee - basis)
    state.commissions = cash_round(state.commissions + fee)


def _split(state: PaperProjection, split: SplitInput) -> None:
    found = False
    for lot in state.lots:
        if lot.symbol != split.symbol:
            continue
        found = True
        quantity = lot.quantity * split.numerator / split.denominator
        if quantity != quantity.quantize(MICRO) or not 0 < quantity <= Decimal(
            "1000000000"
        ):
            raise PaperInvalid("SPLIT_QUANTITY_PRECISION_OR_RANGE")
        lot.quantity = quantity
    if not found:
        raise PaperInvalid("PAPER_HOLDING_REQUIRED")


def replay(events: list[PaperEvent]) -> tuple[PaperSettings, PaperProjection]:
    if not events or not isinstance(events[0].payload, InitialInput):
        raise PaperInvalid("PAPER_INITIAL_STATE_REQUIRED")
    settings = events[0].payload.settings
    state = PaperProjection(
        cash=settings.initial_cash,
        realized_pnl=Decimal(0),
        commissions=Decimal("0.00"),
        dividend_income=Decimal("0.00"),
        positions=[],
        lots=[],
        closed=False,
        last_ledger_sequence=1,
    )
    with localcontext() as context:
        context.prec = 50
        for event in events[1:]:
            entry = event.payload
            if state.closed:
                raise PaperInvalid("PAPER_EXPERIMENT_CLOSED")
            if isinstance(entry, InitialInput):
                raise PaperInvalid("DUPLICATE_INITIAL_STATE")
            if isinstance(entry, (TradeInput, SplitInput, DividendInput)):
                if entry.symbol not in settings.symbols:
                    raise PaperInvalid("PAPER_SYMBOL_NOT_ALLOWED")
                if isinstance(entry, TradeInput):
                    _trade(state, settings, event, entry)
                elif isinstance(entry, SplitInput):
                    _split(state, entry)
                else:
                    quantity = sum(
                        (
                            lot.quantity
                            for lot in state.lots
                            if lot.symbol == entry.symbol
                        ),
                        Decimal(0),
                    )
                    if quantity <= 0:
                        raise PaperInvalid("PAPER_HOLDING_REQUIRED")
                    gross = cash_round(quantity * entry.gross_per_share)
                    if entry.withholding > gross:
                        raise PaperInvalid("DIVIDEND_WITHHOLDING_EXCEEDS_GROSS")
                    income = cash_round(gross - entry.withholding)
                    state.cash = cash_round(state.cash + income)
                    state.dividend_income = cash_round(state.dividend_income + income)
                state.last_ledger_sequence = event.sequence
            elif isinstance(entry, CloseInput):
                state.closed = True
                state.last_ledger_sequence = event.sequence
        symbols = sorted({lot.symbol for lot in state.lots})
        state.positions = [
            PaperPosition(
                symbol=symbol,
                quantity=sum(
                    (lot.quantity for lot in state.lots if lot.symbol == symbol),
                    Decimal(0),
                ),
                cost_basis=cash_round(
                    sum(
                        (lot.cost_basis for lot in state.lots if lot.symbol == symbol),
                        Decimal(0),
                    )
                ),
            )
            for symbol in symbols
        ]
    return settings, state
