"""Explicit bounded policy history. No numeric defaults, model calls or implicit activation."""

from datetime import UTC, datetime

from ...database.repositories.evidence_repository import EvidenceStorage
from ...models.decision_review import (
    ConfirmReviewPolicy,
    ControlEvent,
    ReconcileReview,
    ReviewControl,
    ReviewPolicyVersion,
    ReviewSettings,
    RevisionRequest,
)
from ..evidence.identity import digest
from ..portfolio_risk import service as risk
from ..research_strategy import store as strategy
from . import control


def active(state: ReviewControl) -> ReviewPolicyVersion | None:
    if state.active_policy is None:
        return None
    version = next(
        (p for p in state.policies if p.version_id == state.active_policy), None
    )
    if version is None:
        raise control.ReviewConflict("Active review policy is missing")
    return version


async def settings(db: EvidenceStorage) -> ReviewSettings:
    current = await control.read(db)
    policy = active(current)
    costs = await risk.policy_state(db)
    contract = await strategy.active(db)
    _, _, account_revision = await risk.account(db)
    reasons = []
    if policy is None:
        reasons.append("REVIEW_POLICY_UNCONFIRMED")
    else:
        if costs.revision != policy.policy.risk_policy_revision:
            reasons.append("RISK_POLICY_CHANGED")
        if contract is None or contract.version_id != policy.policy.strategy_version:
            reasons.append("STRATEGY_CHANGED")
    if current.uncertain:
        reasons.append("ACCOUNT_RECONCILIATION_REQUIRED")
    if current.mutations:
        reasons.append("INPUT_MUTATION_IN_FLIGHT")
    return ReviewSettings(
        revision=current.revision,
        generation=current.generation,
        policy=policy,
        versions=current.policies,
        account_revision=account_revision,
        risk_policy_revision=costs.revision,
        strategy_version=contract.version_id if contract else None,
        uncertain=current.uncertain,
        in_flight=len(current.mutations),
        current_batch_id=current.current.batch_id if current.current else None,
        reasons=reasons,
    )


async def confirm(db: EvidenceStorage, request: ConfirmReviewPolicy) -> ReviewSettings:
    current = await control.read(db)
    fingerprint = digest(request.model_dump(mode="json"))
    replay = next(
        (v for v in current.policies if v.request_id == request.request_id), None
    )
    if replay:
        if replay.request_hash != fingerprint:
            raise control.ReviewConflict("Policy request ID has different inputs")
        return await settings(db)
    control.check(current, request)
    if len(current.policies) >= 100:
        raise control.ReviewConflict(
            "Policy history budget exhausted; history is retained"
        )
    costs = await risk.policy_state(db)
    contract = await strategy.active(db)
    if (
        costs.policy is None
        or costs.confirmed_at is None
        or costs.revision != request.policy.risk_policy_revision
        or contract is None
        or contract.version_id != request.policy.strategy_version
        or contract.cost_policy_revision != costs.revision
        or contract.cost_policy != costs.policy
        or not set(contract.parameters.peer_symbols)
        <= set(request.policy.allowed_symbols)
    ):
        raise control.ReviewConflict(
            "Confirm matching risk/cost and strategy versions first"
        )
    version = ReviewPolicyVersion(
        version_id="review_policy_" + digest([current.revision + 1, fingerprint]),
        policy=request.policy,
        request_id=request.request_id,
        request_hash=fingerprint,
        confirmed_at=datetime.now(UTC),
        revision=current.revision + 1,
        sizing=(
            "user_or_model_targets@1"
            if request.policy.model_decisions == "propose_for_human_review"
            else "user_targets@1"
        ),
    )
    await control.commit(
        db,
        current,
        current.model_copy(
            update={
                "revision": current.revision + 1,
                "generation": current.generation + 1,
                "policies": [*current.policies, version],
                "active_policy": version.version_id,
            }
        ),
    )
    return await settings(db)


def event_replay(current: ReviewControl, event: ControlEvent) -> bool:
    previous = next(
        (e for e in current.events if e.request_id == event.request_id), None
    )
    if previous is None:
        if len(current.events) >= 200:
            raise control.ReviewConflict(
                "Control event budget exhausted; history is retained"
            )
        return False
    if previous != event:
        raise control.ReviewConflict("Control request ID has different inputs")
    return True


async def deactivate(db: EvidenceStorage, request: RevisionRequest) -> ReviewSettings:
    current = await control.read(db)
    event = ControlEvent(
        request_id=request.request_id,
        request_hash=digest(request.model_dump(mode="json")),
        kind="deactivate",
    )
    if event_replay(current, event):
        return await settings(db)
    control.check(current, request, clean=False)
    await control.commit(
        db,
        current,
        current.model_copy(
            update={
                "revision": current.revision + 1,
                "generation": current.generation + 1,
                "active_policy": None,
                "events": [*current.events, event],
            }
        ),
    )
    return await settings(db)


async def reconcile(db: EvidenceStorage, request: ReconcileReview) -> ReviewSettings:
    current = await control.read(db)
    event = ControlEvent(
        request_id=request.request_id,
        request_hash=digest(request.model_dump(mode="json")),
        kind="reconcile",
    )
    if event_replay(current, event):
        return await settings(db)
    control.check(current, request, clean=False)
    _, _, fingerprint = await risk.account(db)
    if fingerprint != request.account_revision:
        raise control.ReviewConflict("Declared account changed; inspect it again")
    await control.commit(
        db,
        current,
        current.model_copy(
            update={
                "revision": current.revision + 1,
                "generation": current.generation + 1,
                "uncertain": False,
                "events": [*current.events, event],
            }
        ),
    )
    return await settings(db)
