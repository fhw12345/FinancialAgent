"""Strict manual PAPER contracts. Monetary wire values are bounded decimal strings."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, model_validator

from .decision_review import Confirmed, RequestId, Revision
from .portfolio_risk import Record, Symbol


def decimal_string(value: object, places: int, maximum: str) -> Decimal:
    if isinstance(value, Decimal):
        value = format(
            value, "f"
        )  # Internal revalidation; JSON numbers are still rejected.
    if not isinstance(value, str) or not re.fullmatch(
        rf"(?:0|[1-9][0-9]{{0,15}})(?:\.[0-9]{{1,{places}}})?", value
    ):
        raise ValueError(
            "Use a plain nonnegative decimal string with supported precision"
        )
    result = Decimal(value)
    if result > Decimal(maximum):
        raise ValueError("Decimal exceeds supported range")
    return result


def money(value: object) -> Decimal:
    return decimal_string(value, 2, "1000000000000000")


def price(value: object) -> Decimal:
    return decimal_string(value, 6, "1000000000")


def bps(value: object) -> Decimal:
    return decimal_string(value, 6, "1000")


Money = Annotated[Decimal, BeforeValidator(money)]
Price = Annotated[Decimal, BeforeValidator(price)]
Quantity = Annotated[Price, Field(gt=0)]
PositivePrice = Annotated[Price, Field(gt=0)]
Bps = Annotated[Decimal, BeforeValidator(bps)]
Origin = Literal["manual_unverified_scenario"]


class PaperSettings(Record):
    name: str = Field(min_length=1, max_length=80)
    initial_cash: Money
    symbols: list[Symbol] = Field(min_length=1, max_length=50)
    commission_bps: Bps
    slippage_bps: Bps
    currency: Literal["USD"] = "USD"
    basis: Literal["FIFO-inclusive-buy-fees@1"] = "FIFO-inclusive-buy-fees@1"
    arithmetic: Literal["decimal-half-even-cents@1"] = "decimal-half-even-cents@1"
    corporate_actions: Literal["manual-reconciliation@1"] = "manual-reconciliation@1"

    @model_validator(mode="after")
    def distinct(self) -> "PaperSettings":
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("Duplicate paper symbol")
        return self


class CreatePaper(Record):
    request_id: RequestId
    confirm: Confirmed
    acknowledgment: Literal["manual-paper-only-no-real-account-or-ai-approval"]
    settings: PaperSettings


class PaperRequest(Record):
    request_id: RequestId
    expected_sequence: Revision
    confirm: Confirmed
    acknowledgment: Literal["manual-scenario-not-ai-approved-or-market-fill"]


class TradeInput(Record):
    kind: Literal["trade"] = "trade"
    symbol: Symbol
    side: Literal["buy", "sell"]
    quantity: Quantity
    reference_price: PositivePrice
    origin: Origin = "manual_unverified_scenario"


class SplitInput(Record):
    kind: Literal["split"] = "split"
    symbol: Symbol
    numerator: int = Field(strict=True, ge=1, le=10000)
    denominator: int = Field(strict=True, ge=1, le=10000)
    origin: Origin = "manual_unverified_scenario"


class DividendInput(Record):
    kind: Literal["dividend"] = "dividend"
    symbol: Symbol
    gross_per_share: PositivePrice
    withholding: Money
    origin: Origin = "manual_unverified_scenario"


class CloseInput(Record):
    kind: Literal["close"] = "close"


ManualInput = Annotated[
    TradeInput | SplitInput | DividendInput | CloseInput, Field(discriminator="kind")
]


class JournalPaper(PaperRequest):
    entry: ManualInput


class RefreshPaper(PaperRequest):
    session_date: date
    reconciliation: Literal["corporate-actions-inspected-through-this-session"]


class ClosingMark(Record):
    symbol: Symbol
    session_date: date
    price: PositivePrice | None
    currency: Literal["USD"] | None
    source: str
    error: str | None = None


class ValuationInput(Record):
    kind: Literal["valuation"] = "valuation"
    session_date: date
    ledger_sequence: int
    fetched_at: datetime
    reconciliation: Literal["corporate-actions-inspected-through-this-session"]
    marks: list[ClosingMark] = Field(max_length=50)


class InitialInput(Record):
    kind: Literal["created"] = "created"
    settings: PaperSettings


Payload = Annotated[
    InitialInput
    | TradeInput
    | SplitInput
    | DividendInput
    | CloseInput
    | ValuationInput,
    Field(discriminator="kind"),
]


class PaperEvent(Record):
    event_id: str
    sequence: int
    request_id: str
    request_hash: str
    recorded_at: datetime
    payload: Payload
    previous_hash: str
    event_hash: str


class PaperExperiment(Record):
    schema_version: Literal[1] = 1
    experiment_id: str
    sequence: int
    events: list[PaperEvent] = Field(min_length=1, max_length=500)


class PaperLot(Record):
    event_id: str
    symbol: Symbol
    quantity: Quantity
    cost_basis: Money


class PaperPosition(Record):
    symbol: Symbol
    quantity: Quantity
    cost_basis: Money


class PaperProjection(Record):
    cash: Money
    realized_pnl: Decimal
    commissions: Money
    dividend_income: Money
    positions: list[PaperPosition]
    lots: list[PaperLot]
    closed: bool
    last_ledger_sequence: int


class PaperValuation(Record):
    basis: Literal["current-scenario-quantities-at-last-completed-close"] = (
        "current-scenario-quantities-at-last-completed-close"
    )
    session_date: date
    recorded_at: datetime
    status: Literal["complete", "unavailable"]
    nav: Money | None
    scenario_pnl: Decimal | None
    marked_positions: int
    total_positions: int
    errors: list[str]
    stale: bool
    stale_reasons: list[str]
    marks: list[ClosingMark]


class PaperTradeReceipt(Record):
    event_id: str
    effective_price: Decimal
    principal: Money
    commission: Money


class PaperView(Record):
    experiment: PaperExperiment
    settings: PaperSettings
    projection: PaperProjection
    valuation: PaperValuation | None
    current_session: date
    trade_receipts: list[PaperTradeReceipt]
    provenance: Origin = "manual_unverified_scenario"
    ai_validated: Literal[False] = False
    broker_execution: Literal[False] = False
