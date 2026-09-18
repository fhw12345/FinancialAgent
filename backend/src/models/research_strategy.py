"""Confirmed research contracts and model-estimate receipts; never approval/execution."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .portfolio_risk import Number, Record, RiskPolicy, Symbol

Method = Literal["peer_pe_annual@1", "fcff_proxy_dcf@1"]


class StrategyParameters(Record):
    methods: list[Method] = Field(min_length=1, max_length=2)
    peer_symbols: list[Symbol] = Field(max_length=10)
    peer_rationale: str = Field(min_length=1, max_length=500)
    discount_rate: Annotated[Number, Field(gt=0, le=1)]
    growth_rate: Annotated[Number, Field(gt=-1, le=1)]
    terminal_growth: Annotated[Number, Field(gt=-1, lt=1)]
    tax_rate: Annotated[Number, Field(ge=0, le=1)]
    projection_years: int = Field(ge=1, le=20, strict=True)
    valuation_discount: Annotated[Number, Field(ge=0, lt=1)]
    earnings_decline_fraction: Annotated[Number, Field(gt=0, le=1)]
    debt_to_fcf_limit: Annotated[Number, Field(gt=0)]
    max_financial_age_days: int = Field(ge=1, le=730, strict=True)
    max_price_lag_sessions: int = Field(ge=0, le=5, strict=True)
    fcff_proxy_acknowledged: Literal[True]

    @model_validator(mode="after")
    def validate_definition(self) -> "StrategyParameters":
        if self.terminal_growth >= self.discount_rate:
            raise ValueError("Terminal growth must be below discount rate")
        if len(set(self.methods)) != len(self.methods):
            raise ValueError("Duplicate valuation methods are not triangulation")
        if len(set(self.peer_symbols)) != len(self.peer_symbols):
            raise ValueError("Duplicate peer instruments")
        return self


class StrategyVersion(Record):
    strategy_id: Literal["fundamental-252@1"] = "fundamental-252@1"
    version_id: str
    revision: int
    horizon: Literal[252] = 252
    horizon_unit: Literal["XNYS_sessions"] = "XNYS_sessions"
    benchmark: Literal["SPY_total_return@1"] = "SPY_total_return@1"
    universe: Literal["US_USD_nonfinancial_common_equity"] = (
        "US_USD_nonfinancial_common_equity"
    )
    parameters: StrategyParameters
    cost_policy_revision: int
    cost_policy: RiskPolicy
    confirmed_at: datetime
    request_id: str
    input_hash: str


class StrategyState(Record):
    revision: int = 0
    active_version: str | None = None
    versions: list[StrategyVersion] = Field(default_factory=list, max_length=100)


class ValuationInput(Record):
    snapshot_id: str
    evidence_id: str
    symbol: str
    metric: str
    value: Number
    unit: str
    period: str
    period_end: date


class ValuationResult(Record):
    method: Method
    status: Literal["available", "unavailable", "inapplicable"]
    reasons: list[str] = Field(default_factory=list)
    inputs: list[ValuationInput] = Field(default_factory=list)
    assumptions: dict[str, Number | str] = Field(default_factory=dict)
    peer_multiple: Number | None = None
    enterprise_value: Number | None = None
    equity_value: Number | None = None
    per_share_usd: Number | None = None
    interpretation: Literal["conditional_model_estimate_not_verified_fair_value"] = (
        "conditional_model_estimate_not_verified_fair_value"
    )


class Thesis(Record):
    text: str = Field(min_length=1, max_length=1200)
    evidence_ids: list[str] = Field(min_length=1, max_length=10)
    monitoring_rule: Literal["earnings_decline", "debt_to_fcf", "valuation_discount"]


class Forecast(Record):
    scenario: Literal["bull", "base", "bear"]
    condition: str = Field(min_length=1, max_length=1000)
    probability: None = None
    probability_basis: Literal["not_estimated"] = "not_estimated"


class StrategyConclusion(Record):
    kind: Literal["strategy_research"] = "strategy_research"
    symbol: Symbol
    stance: Literal["bullish", "neutral", "bearish", "unknown"]
    theses: list[Thesis] = Field(max_length=6)
    scenarios: list[Forecast] = Field(max_length=3)
    report_markdown: str = Field(min_length=1, max_length=20000)
    portfolio_action: None = None
    execution_intent: None = None
    prose_verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def unique_scenarios(self) -> "StrategyConclusion":
        if len({s.scenario for s in self.scenarios}) != len(self.scenarios):
            raise ValueError("Duplicate conditional scenarios")
        return self


class StrategyConclusions(Record):
    conclusions: list[StrategyConclusion] = Field(max_length=100)


class MonitoringCheck(Record):
    rule: str
    status: Literal["triggered", "not_triggered", "unavailable"]
    value: Number | None
    threshold: Number
    unit: Literal["ratio"] = "ratio"
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str


class StrategyReview(Record):
    review_id: str
    contract: StrategyVersion
    symbol: str
    snapshot_id: str
    as_of: datetime
    purpose: Literal["research"] = "research"
    status: Literal["research_only", "insufficient_evidence", "inapplicable"]
    errors: list[str]
    valuations: list[ValuationResult]
    monitoring: list[str]
    checks: list[MonitoringCheck] = Field(default_factory=list)
    conclusion: StrategyConclusion | None = None
    stale: bool = False
    actionable: Literal[False] = False
    prompt_versions: dict[str, str] = Field(default_factory=dict)


class StrategySummary(Record):
    reviews: list[StrategyReview]
    errors: list[str]
    legacy_strategy: Literal[False] = False
    actionable: Literal[False] = False
