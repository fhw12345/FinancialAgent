"""User-target paper-review contracts. Readiness/approval never grant execution authority."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StrictBool, model_validator

from .portfolio_risk import Number, PortfolioRiskReview, Record, Symbol, Weight

Revision = Annotated[int, Field(strict=True, ge=0)]
RequestId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{8,80}$")]


def _confirmed(value: bool) -> bool:
    if not value:
        raise ValueError("Explicit confirmation required")
    return value


Confirmed = Annotated[StrictBool, AfterValidator(_confirmed)]
Readiness = Literal[
    "ready", "research_only", "insufficient_evidence", "needs_review", "blocked"
]


class ReviewPolicyInput(Record):
    risk_policy_revision: Annotated[Revision, Field(ge=1)]
    strategy_version: str = Field(pattern=r"^strategy_[a-f0-9]{64}$")
    allowed_symbols: list[Symbol] = Field(min_length=1, max_length=100)
    max_account_sigma: Annotated[Number, Field(gt=0, le=3)]
    lifetime_minutes: Annotated[int, Field(strict=True, ge=1, le=1440)]
    acknowledged_contract: Literal["manual-target-paper-review@1"]
    instrument_attestation: Literal["USD-US-nonfinancial-common-equities"]
    evidence_acknowledgment: Literal["forward-close-not-truth-or-historical-PIT"]

    @model_validator(mode="after")
    def unique_symbols(self) -> "ReviewPolicyInput":
        if len(set(self.allowed_symbols)) != len(self.allowed_symbols):
            raise ValueError("Duplicate allowed symbol")
        return self


class RevisionRequest(Record):
    expected_revision: Revision
    expected_generation: Revision
    request_id: RequestId


class ConfirmReviewPolicy(RevisionRequest):
    policy: ReviewPolicyInput
    confirm: Confirmed


class ReviewPolicyVersion(Record):
    version_id: str
    policy: ReviewPolicyInput
    request_id: str
    request_hash: str
    confirmed_at: datetime
    revision: int
    account_scope: Literal["local_holdings"] = "local_holdings"
    sizing: Literal["user_targets@1"] = "user_targets@1"
    reference_basis: Literal["completed-XNYS-daily-close"] = (
        "completed-XNYS-daily-close"
    )
    long_only: Literal[True] = True
    borrowing: Literal[False] = False
    stop_risk_basis: Literal["not_applicable_target_only_no_max_loss_bound"] = (
        "not_applicable_target_only_no_max_loss_bound"
    )
    unfilled_sales_are_buying_power: Literal[False] = False


class ReviewTarget(Record):
    symbol: Symbol
    target_weight: Weight


class ProposeReview(RevisionRequest):
    assessment_id: str = Field(pattern=r"^assessment_[a-f0-9]{32}$")
    targets: list[ReviewTarget] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_targets(self) -> "ProposeReview":
        if len({t.symbol for t in self.targets}) != len(self.targets):
            raise ValueError("Duplicate target")
        return self


class ApproveReview(RevisionRequest):
    symbols: list[Symbol] = Field(min_length=1, max_length=20)
    confirm: Confirmed
    acknowledgment: Literal["review-only-no-real-or-paper-fill"]

    @model_validator(mode="after")
    def unique_symbols(self) -> "ApproveReview":
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("Duplicate approved symbol")
        return self


class ReconcileReview(RevisionRequest):
    account_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    acknowledgment: Literal["declared-account-inspected-no-writers-in-flight"]


class GateReason(Record):
    code: str = Field(max_length=200)
    severity: Literal[
        "research_only", "insufficient_evidence", "needs_review", "blocked"
    ]
    symbol: Symbol | None = None


class ReviewTrade(Record):
    symbol: Symbol
    action: Literal["BUY", "SELL", "HOLD"]
    intent: Literal["open_long", "add_long", "reduce_long", "close_long", "hold"]
    exposure: Literal["held", "flat"]
    delta_quantity: Number
    reference_price: Number
    execution_price: None = None


class SymbolProof(Record):
    symbol: Symbol
    snapshot_id: str
    manifest_hash: str
    dossier_id: str
    strategy_review_id: str
    monitoring: dict[str, str]
    unverified_context: list[str]


class PreparedReview(Record):
    """Immutable candidate, NOT authoritative until its control pointer is published."""

    schema_version: Literal[1] = 1
    gate_version: Literal["idq-001-b@1"] = "idq-001-b@1"
    batch_id: str
    request: ProposeReview
    request_hash: str
    receipt_hash: str
    source_hash: str | None
    run_id: str | None
    created_at: datetime
    expires_at: datetime
    policy: ReviewPolicyVersion | None
    risk: PortfolioRiskReview | None
    reasons: list[GateReason]
    trades: list[ReviewTrade]
    proofs: list[SymbolProof]
    executable: Literal[False] = False


class ReviewPointer(Record):
    batch_id: str
    receipt_hash: str
    world_revision: int
    state: Literal["published", "approved", "cancelled"] = "published"
    approval_id: str | None = None
    cancellation_request: str | None = None


class ApprovalEvent(Record):
    approval_id: str
    batch_id: str
    request: ApproveReview
    request_hash: str
    receipt_hash: str
    approved_at: datetime
    world_revision: int
    generation: int
    executable: Literal[False] = False


class ControlEvent(Record):
    request_id: str
    request_hash: str
    kind: Literal["deactivate", "reconcile", "cancel"]
    batch_id: str | None = None


class ReviewControl(Record):
    revision: int = 0
    generation: int = 0
    policies: list[ReviewPolicyVersion] = Field(default_factory=list, max_length=100)
    active_policy: str | None = None
    mutations: dict[str, str] = Field(default_factory=dict)
    uncertain: bool = False
    current: ReviewPointer | None = None
    published: list[ReviewPointer] = Field(default_factory=list, max_length=200)
    approvals: list[ApprovalEvent] = Field(default_factory=list, max_length=200)
    events: list[ControlEvent] = Field(default_factory=list, max_length=200)


class ReviewSettings(Record):
    revision: int
    generation: int
    policy: ReviewPolicyVersion | None
    versions: list[ReviewPolicyVersion]
    account_revision: str
    risk_policy_revision: int
    strategy_version: str | None
    uncertain: bool
    in_flight: int
    current_batch_id: str | None
    reasons: list[str]
    approval_available: Literal[True] = True
    execution_available: Literal[False] = False


class ApprovalReceipt(Record):
    approval_id: str
    request_hash: str
    receipt_hash: str
    batch_id: str
    evaluation: PreparedReview


class ReviewView(Record):
    batch: PreparedReview
    readiness: Readiness
    reasons: list[GateReason]
    lifecycle: Literal["unpublished", "current", "superseded", "cancelled", "approved"]
    approvable: bool
    approval: ApprovalEvent | None = None
    approval_receipt: ApprovalReceipt | None = None
    approval_current: bool = False
    control_revision: int
    control_generation: int
    executable: Literal[False] = False
