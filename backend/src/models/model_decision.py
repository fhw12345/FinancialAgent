"""Model-proposed decisions: explicit recommendations with no readiness/approval authority."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .portfolio_risk import Record, Symbol, Weight

ModelAction = Literal["BUY", "ADD", "REDUCE", "SELL", "HOLD"]
Text = Annotated[str, Field(min_length=1, max_length=300)]


class ModelDecision(Record):
    symbol: Symbol
    action: ModelAction
    target_weight: Weight | None = None
    rationale: str = Field(min_length=1, max_length=1500)
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)
    key_risks: list[Text] = Field(default_factory=list, max_length=5)
    review_triggers: list[Text] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def target_matches_action(self) -> "ModelDecision":
        if self.action == "HOLD" and self.target_weight is not None:
            raise ValueError("HOLD keeps the current position; no target weight")
        if self.action != "HOLD" and self.target_weight is None:
            raise ValueError("Position changes require an explicit target weight")
        if self.action == "SELL" and self.target_weight != 0:
            raise ValueError("SELL exits the position; use REDUCE for partial sales")
        if self.action in ("BUY", "ADD", "REDUCE") and not self.target_weight:
            raise ValueError("Non-exit changes require a positive target weight")
        return self


class ModelDecisionSet(Record):
    decisions: list[ModelDecision] = Field(min_length=1, max_length=20)
    portfolio_summary: str = Field(min_length=1, max_length=1500)


class ModelProvenance(Record):
    prompt: Literal["portfolio-model-decision@1"] = "portfolio-model-decision@1"
    role: Literal["portfolio_decisions"] = "portfolio_decisions"
    provider: str
    model: str
    api: str | None = None
    routing_revision: int | None = None


class ModelDecisionRecord(Record):
    """Durable claim and immutable model output. Never itself ready or approved."""

    schema_version: Literal[1] = 1
    decision_id: str
    request_id: str
    request_hash: str
    assessment_id: str
    source_hash: str
    policy_version_id: str
    scope: list[Symbol] = Field(min_length=1, max_length=20)
    status: Literal["running", "completed", "failed"]
    owner: str
    lease_until: datetime
    created_at: datetime
    completed_at: datetime | None = None
    provenance: ModelProvenance | None = None
    output: ModelDecisionSet | None = None
    error_code: str | None = None
    executable: Literal[False] = False
