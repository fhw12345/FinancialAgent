"""Versioned, reproducible daily-close risk and non-actionable allocation receipts."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Weight = Annotated[Number, Field(ge=0, le=1)]
Positive = Annotated[Number, Field(gt=0)]
Symbol = Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9.-]{0,14}$")]


class Record(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        revalidate_instances="always",
        validate_assignment=True,
    )


class RiskPolicy(Record):
    """User-confirmed preview constraints, not the full IDQ-001-B investment policy."""

    max_position_weight: Annotated[Weight, Field(gt=0)]
    max_sector_weight: Annotated[Weight, Field(gt=0)]
    min_cash_weight: Weight
    max_turnover: Annotated[Number, Field(gt=0, le=2)]
    risk_per_trade_weight: Annotated[Weight, Field(gt=0)]
    lot_size: Annotated[Positive, Field(ge=0.000001, le=1)]
    fee_bps: Annotated[Number, Field(ge=0, le=1000)]
    slippage_bps: Annotated[Number, Field(ge=0, le=1000)]


class PolicyState(Record):
    revision: int = 0
    policy: RiskPolicy | None = None
    confirmed_at: datetime | None = None


class RiskPosition(Record):
    symbol: Symbol
    quantity: Positive
    cost_basis: Annotated[Number, Field(ge=0)]


class SessionReturn(Record):
    session_date: date
    total_return: Annotated[Number, Field(ge=-1)]


class RiskAsset(Record):
    symbol: Symbol
    currency: str | None = None
    mark: Positive | None = None
    mark_session: date | None = None
    sector: str = "Unknown"
    beta: Number | None = None
    source: str = "yfinance"
    adjustment: Literal["adjusted_close_total_return"] = "adjusted_close_total_return"
    returns: list[SessionReturn] = Field(default_factory=list, max_length=300)
    errors: list[str] = Field(default_factory=list)


class PortfolioRiskSnapshot(Record):
    schema_version: Literal[1] = 1
    calculator_version: Literal["idq-002@1"] = "idq-002@1"
    account_scope: Literal["local_holdings"] = "local_holdings"
    account_id: Literal["local"] = "local"
    account_revision: str
    snapshot_id: str = ""
    captured_at: datetime
    session_date: date
    cash: Annotated[Number, Field(ge=0)] | None
    positions: list[RiskPosition] = Field(max_length=100)
    assets: list[RiskAsset] = Field(max_length=200)
    policy: PolicyState = Field(default_factory=PolicyState)
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_instruments(self) -> "PortfolioRiskSnapshot":
        for rows in (self.positions, self.assets):
            symbols = [p.symbol for p in rows]
            if len(set(symbols)) != len(symbols):
                raise ValueError("Duplicate instrument")
        return self


class RiskMetrics(Record):
    status: Literal["complete", "unavailable"]
    equity: Number | None = None
    cash_weight: Number | None = None
    invested_value: Number | None = None
    account_sigma_annualized: Number | None = None
    invested_sigma_annualized: Number | None = None
    invested_hhi: Number | None = None
    beta_exposure: Number | None = None
    position_weights: dict[str, Number] = Field(default_factory=dict)
    sector_weights: dict[str, Number] = Field(default_factory=dict)
    correlations: dict[str, dict[str, Number | None]] = Field(default_factory=dict)
    common_sessions: list[date] = Field(default_factory=list)
    history_equity_coverage: Number | None = None
    exclusions: dict[str, list[str]] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(
        default_factory=lambda: [
            "Cash volatility assumed zero; interest is not modeled.",
            "60 completed XNYS sessions, minimum 30 common returns; sample covariance, annualization 252.",
            "Provider-adjusted history is not point-in-time evidence or a maximum-loss guarantee.",
        ]
    )


class TargetProposal(Record):
    symbol: Symbol
    target_weight: Weight
    stop: Positive | None = None


class SizedChange(Record):
    symbol: Symbol
    requested_target_weight: Weight
    current_quantity: Number
    proposed_quantity: Number
    delta_quantity: Number
    mark: Positive
    estimated_cost_buffer: Number
    stop_risk_quantity_cap: Number | None = None


class AllocationReceipt(Record):
    allocation_id: str = ""
    calculator_version: Literal["idq-002@1"] = "idq-002@1"
    actionable: Literal[False] = False
    status: Literal["feasible_preview", "blocked"]
    constraints: list[str]
    changes: list[SizedChange] = Field(default_factory=list)
    proposed: RiskMetrics | None = None
    turnover: Number | None = None
    posttrade_cash: Number | None = None
    cash_without_unfilled_sales: Number | None = None


class PortfolioRiskReview(Record):
    snapshot: PortfolioRiskSnapshot
    current: RiskMetrics
    allocation: AllocationReceipt | None = None
    stale: bool = False
    stale_reasons: list[str] = Field(default_factory=list)
