"""Stage-A strict writes: research artifacts cannot represent approved trades."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from .evidence import EvidenceSummary
from .portfolio_risk import PortfolioRiskReview
from .research_strategy import StrategySummary

Readiness = Literal["research_only", "insufficient_evidence", "needs_review", "blocked"]


class StrictRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid", revalidate_instances="always", strict=True
    )


class DraftProposal(StrictRecord):
    symbol: str = Field(pattern=r"^[A-Z0-9][A-Z0-9.-]{0,14}$")
    proposed_action: Literal["BUY", "SELL", "HOLD"]
    intent: Literal["open_long", "close_long", "hold"]
    size_percent: FiniteFloat | None = Field(default=None, gt=0, le=100)
    entry: FiniteFloat | None = Field(default=None, gt=0)
    stop: FiniteFloat | None = Field(default=None, gt=0)
    target: FiniteFloat | None = Field(default=None, gt=0)
    reasoning: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_draft(self) -> "DraftProposal":
        if (
            self.intent
            != {"BUY": "open_long", "SELL": "close_long", "HOLD": "hold"}[
                self.proposed_action
            ]
        ):
            raise ValueError("Unsupported action/intent combination")
        if self.proposed_action != "HOLD":
            if (
                self.size_percent is None
                or self.entry is None
                or self.stop is None
                or self.target is None
            ):
                raise ValueError("Trade draft requires size and all price levels")
            if not self.stop < self.entry < self.target:
                raise ValueError("Invalid long-side price geometry")
        elif any(
            value is not None
            for value in (self.size_percent, self.entry, self.stop, self.target)
        ):
            raise ValueError("HOLD cannot carry an execution plan")
        return self


class AssessmentReason(StrictRecord):
    code: Literal[
        "STAGE_A_ONLY",
        "RESEARCH_MISSING",
        "CHECK_UNAVAILABLE",
        "CONSISTENCY_VIOLATION",
        "DATA_DEGRADED",
        "QUOTE_UNAVAILABLE",
        "INVALID_PROPOSAL",
        "SYMBOL_NOT_AUTHORIZED",
        "DUPLICATE_PROPOSAL",
        "UNSUPPORTED_EXPOSURE",
        "DECISION_UNAVAILABLE",
        "RUN_CANCELLED",
        "RUN_FAILED",
        "RUN_IN_PROGRESS",
        "RUN_UNVERIFIED",
        "PORTFOLIO_RISK_UNAVAILABLE",
        "ALLOCATION_BLOCKED",
        "EVIDENCE_UNVERIFIED",
        "STRATEGY_UNAVAILABLE",
    ]
    message: str = Field(max_length=500)


class SymbolAssessment(StrictRecord):
    symbol: str = Field(pattern=r"^[A-Z0-9][A-Z0-9.-]{0,14}$")
    readiness: Readiness
    actionable: Literal[False] = False
    action: None = None
    proposal: DraftProposal | None = None
    research: str = Field(default="", max_length=100000)
    research_truncated: bool = False
    exposure_context: Literal["held", "flat", "unknown"] = "unknown"
    reasons: list[AssessmentReason] = Field(min_length=1)


class DecisionAssessment(StrictRecord):
    schema_version: Literal[1] = 1
    policy_version: Literal["idq-001-a@1"] = "idq-001-a@1"
    assessment_id: str
    request_key: str = Field(min_length=1, max_length=200)
    input_hash: str
    run_id: str | None = None
    source: str = Field(min_length=1, max_length=40)
    created_at: datetime
    backend_version: str
    readiness: Readiness
    actionable: Literal[False] = False
    action: None = None
    results: list[SymbolAssessment] = Field(min_length=1, max_length=100)
    run_status: str | None = None
    portfolio_risk: PortfolioRiskReview | None = None
    evidence: EvidenceSummary | None = None
    strategy: StrategySummary | None = None
    legacy_strategy: bool = True
