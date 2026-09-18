"""Read-side validity is projected, never written over immutable historical receipts."""

from datetime import UTC, datetime

from ...database.repositories.evidence_repository import EvidenceStorage
from ...models.decision_review import GateReason, PreparedReview, Readiness, ReviewView
from ..portfolio_risk.calendar import completed_session
from ..portfolio_risk.service import account, policy_state
from ..research_strategy.store import active as active_strategy
from . import control, policies, review_storage

PRIORITY: dict[Readiness, int] = {
    "ready": -1,
    "research_only": 0,
    "needs_review": 1,
    "insufficient_evidence": 2,
    "blocked": 3,
}


def readiness(reasons: list[GateReason]) -> Readiness:
    return max((r.severity for r in reasons), key=PRIORITY.__getitem__, default="ready")


async def project(db: EvidenceStorage, batch: PreparedReview) -> ReviewView:
    state = await control.read(db)
    reasons = list(batch.reasons)
    published = next((p for p in state.published if p.batch_id == batch.batch_id), None)
    current = state.current
    is_current = current is not None and current.batch_id == batch.batch_id
    lifecycle = (
        "current" if is_current else "superseded" if published else "unpublished"
    )

    def stale(code: str) -> None:
        reasons.append(GateReason(code=code, severity="needs_review"))

    if published is None:
        stale("REVIEW_NOT_PUBLISHED")
    elif published.receipt_hash != batch.receipt_hash:
        raise control.ReviewConflict("Published review hash mismatch")
    elif published.world_revision != state.revision:
        stale("INPUT_REVISION_CHANGED")
    if not is_current and published:
        stale("REVIEW_SUPERSEDED")
    if is_current and current:
        if current.receipt_hash != batch.receipt_hash:
            raise control.ReviewConflict("Current review hash mismatch")
        if current.state == "cancelled":
            lifecycle = "cancelled"
            stale("REVIEW_CANCELLED")
        elif current.state == "approved":
            lifecycle = "approved"
    if state.mutations:
        stale("INPUT_MUTATION_IN_FLIGHT")
    if state.uncertain:
        stale("ACCOUNT_RECONCILIATION_REQUIRED")
    policy = policies.active(state)
    if policy is None or batch.policy != policy:
        stale("REVIEW_POLICY_CHANGED")
    costs = await policy_state(db)
    strategy = await active_strategy(db)
    if batch.policy and (
        costs.revision != batch.policy.policy.risk_policy_revision
        or strategy is None
        or strategy.version_id != batch.policy.policy.strategy_version
    ):
        stale("RISK_OR_STRATEGY_POLICY_CHANGED")
    now = datetime.now(UTC)
    if now >= batch.expires_at:
        stale("PROPOSAL_EXPIRED")
    if batch.risk:
        _, _, fingerprint = await account(db)
        if fingerprint != batch.risk.snapshot.account_revision:
            stale("ACCOUNT_CHANGED")
        if completed_session(now) != batch.risk.snapshot.session_date:
            stale("SESSION_CHANGED")
    run = (
        await db.get_collection("agent_runs").find_one({"run_id": batch.run_id})
        if batch.run_id
        else None
    )
    if run is None or run.get("status") != "completed":
        stale("SOURCE_RUN_NOT_COMPLETED")
    event = next((e for e in state.approvals if e.batch_id == batch.batch_id), None)
    receipt = await review_storage.approval(db, event.approval_id) if event else None
    if event and (receipt is None or receipt.receipt_hash != event.receipt_hash):
        raise control.ReviewConflict("Approved receipt hash mismatch")
    after = await control.read(db)
    if after != state:
        stale("INPUTS_CHANGED_DURING_READ")
    status = readiness(reasons)
    return ReviewView(
        batch=batch,
        readiness=status,
        reasons=reasons,
        lifecycle=lifecycle,
        approvable=status == "ready" and is_current and lifecycle == "current",
        approval=event,
        approval_receipt=receipt,
        approval_current=(
            status == "ready"
            and lifecycle == "approved"
            and event is not None
            and event.world_revision == state.revision
        ),
        control_revision=after.revision,
        control_generation=after.generation,
    )
