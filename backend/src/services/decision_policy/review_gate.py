"""Deterministic review gate from server-owned research plus explicit user target weights."""

from datetime import UTC, datetime, timedelta

from ...database.repositories.evidence_repository import EvidenceStorage
from ...models.decision_assessment import DecisionAssessment
from ...models.decision_review import (
    GateReason,
    PreparedReview,
    ProposeReview,
    ReviewPolicyVersion,
    ReviewTrade,
)
from ...models.portfolio_risk import PortfolioRiskReview, TargetProposal
from ..evidence.identity import digest
from ..portfolio_risk import service as risk
from ..portfolio_risk.allocation import allocate
from ..portfolio_risk.calendar import next_close
from ..portfolio_risk.estimator import estimate
from ..research_strategy import store as strategy
from . import evidence_gate
from .review_storage import receipt_hash

SOURCE_FAILURES = {
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
}


async def source_record(
    db: EvidenceStorage, identifier: str
) -> DecisionAssessment | None:
    row = await db.get_collection("decision_assessments").find_one({"_id": identifier})
    if row is None:
        return None
    row.pop("_id", None)
    return DecisionAssessment.model_validate(row)


def clock(value: datetime) -> datetime:
    # Legacy Mongo datetimes can be naive UTC, never reinterpret them as local time.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def evaluate(
    db: EvidenceStorage,
    request: ProposeReview,
    policy: ReviewPolicyVersion | None,
) -> PreparedReview:
    now = datetime.now(UTC)
    source = await source_record(db, request.assessment_id)
    result = PreparedReview(
        batch_id="review_" + digest(request.request_id),
        request=request,
        request_hash=digest(request.model_dump(mode="json")),
        receipt_hash="",
        source_hash=source.input_hash if source else None,
        run_id=source.run_id if source else None,
        created_at=now,
        expires_at=now,
        policy=policy,
        risk=None,
        reasons=[],
        trades=[],
        proofs=[],
    )
    if source is None:
        result.reasons.append(evidence_gate.failure("SOURCE_ASSESSMENT_REQUIRED"))
    if policy is None:
        result.reasons.append(
            GateReason(code="REVIEW_POLICY_UNCONFIRMED", severity="research_only")
        )
    if source is not None and policy is not None:
        await _assess(db, source, result, now)
    result.receipt_hash = receipt_hash(result)
    return result


async def _assess(
    db: EvidenceStorage,
    source: DecisionAssessment,
    result: PreparedReview,
    now: datetime,
) -> None:
    policy = result.policy
    if policy is None:
        raise ValueError("Policy required")
    lifetime = timedelta(minutes=policy.policy.lifetime_minutes)
    result.expires_at = min(clock(source.created_at) + lifetime, now + lifetime)
    run = (
        await db.get_collection("agent_runs").find_one({"run_id": source.run_id})
        if source.run_id
        else None
    )
    if run is None or run.get("status") != "completed":
        result.reasons.append(
            GateReason(code="SOURCE_RUN_NOT_COMPLETED", severity="needs_review")
        )
    if source.legacy_strategy or source.strategy is None:
        result.reasons.append(
            evidence_gate.failure("CONFIRMED_STRATEGY_SOURCE_REQUIRED")
        )
    if source.evidence is None or source.evidence.errors:
        result.reasons.append(evidence_gate.failure("SOURCE_EVIDENCE_UNVERIFIED"))
    if source.strategy and source.strategy.errors:
        result.reasons.append(evidence_gate.failure("SOURCE_STRATEGY_UNAVAILABLE"))
    for row in source.results:
        if (
            row.consistency_status != "passed"
            or row.research_truncated
            or not row.research.strip()
            or any(r.code in SOURCE_FAILURES for r in row.reasons)
        ):
            result.reasons.append(
                evidence_gate.failure("SOURCE_RESEARCH_CHECK_NOT_PASSED", row.symbol)
            )
    allowed = set(policy.policy.allowed_symbols)
    requested = {t.symbol for t in result.request.targets}
    researched = {r.symbol for r in source.results}
    if not requested <= allowed or not requested <= researched:
        result.reasons.append(
            GateReason(code="TARGET_SYMBOL_NOT_AUTHORIZED", severity="blocked")
        )
    costs = await risk.policy_state(db)
    contract = await strategy.active(db)
    if (
        costs.policy is None
        or costs.confirmed_at is None
        or costs.revision != policy.policy.risk_policy_revision
    ):
        result.reasons.append(
            GateReason(code="RISK_POLICY_CHANGED", severity="needs_review")
        )
    if (
        contract is None
        or contract.version_id != policy.policy.strategy_version
        or contract.cost_policy_revision != costs.revision
    ):
        result.reasons.append(
            GateReason(code="STRATEGY_CHANGED", severity="needs_review")
        )
    original = source.portfolio_risk
    if original is None or original.snapshot.errors:
        result.reasons.append(evidence_gate.failure("SOURCE_ACCOUNT_RISK_REQUIRED"))
        return
    result.expires_at = min(
        result.expires_at, next_close(original.snapshot.session_date)
    )
    # No market/model calls for unconfirmed/mismatched configuration or unauthorized scope.
    if not requested <= allowed & researched or any(
        r.code in {"RISK_POLICY_CHANGED", "STRATEGY_CHANGED"} for r in result.reasons
    ):
        return
    for symbol in sorted(requested):
        proof, reasons, as_of = await evidence_gate.validate(
            db, source, symbol, policy, now
        )
        result.reasons.extend(reasons)
        if proof:
            result.proofs.append(proof)
        if as_of:
            result.expires_at = min(result.expires_at, clock(as_of) + lifetime)
    snapshot = await risk.capture(db, [a.symbol for a in original.snapshot.assets])
    result.risk = PortfolioRiskReview(snapshot=snapshot, current=estimate(snapshot))
    if (
        snapshot.account_revision != original.snapshot.account_revision
        or snapshot.session_date != original.snapshot.session_date
        or snapshot.policy != original.snapshot.policy
    ):
        result.reasons.append(
            GateReason(
                code="SOURCE_ACCOUNT_POLICY_SESSION_CHANGED", severity="needs_review"
            )
        )
    if {a.symbol: a for a in snapshot.assets} != {
        a.symbol: a for a in original.snapshot.assets
    }:
        result.reasons.append(
            GateReason(code="SOURCE_MARKET_INPUTS_CHANGED", severity="needs_review")
        )
    allocation = allocate(
        snapshot, [TargetProposal(**t.model_dump()) for t in result.request.targets]
    )
    allocation.allocation_id = "review_allocation_" + digest(
        [snapshot.snapshot_id, allocation.model_dump(mode="json")]
    )
    result.risk.allocation = allocation
    for constraint in allocation.constraints:
        result.reasons.append(GateReason(code=constraint, severity="blocked"))
    sigma = (
        allocation.proposed.account_sigma_annualized if allocation.proposed else None
    )
    if sigma is None:
        result.reasons.append(
            evidence_gate.failure("PROPOSED_ACCOUNT_SIGMA_UNAVAILABLE")
        )
    elif sigma > policy.policy.max_account_sigma:
        result.reasons.append(
            GateReason(code="ACCOUNT_SIGMA_LIMIT", severity="blocked")
        )
    for change in allocation.changes:
        delta = change.delta_quantity
        held = change.current_quantity > 0
        result.trades.append(
            ReviewTrade(
                symbol=change.symbol,
                action="BUY" if delta > 0 else "SELL" if delta < 0 else "HOLD",
                intent=(
                    ("add_long" if held else "open_long")
                    if delta > 0
                    else (
                        (
                            "reduce_long"
                            if change.proposed_quantity > 0
                            else "close_long"
                        )
                        if delta < 0
                        else "hold"
                    )
                ),
                exposure="held" if held else "flat",
                delta_quantity=delta,
                reference_price=change.mark,
            )
        )
        if delta > 0:
            proof = next((p for p in result.proofs if p.symbol == change.symbol), None)
            if (
                proof is None
                or not proof.monitoring
                or any(v != "not_triggered" for v in proof.monitoring.values())
            ):
                result.reasons.append(
                    GateReason(
                        code="BUY_MONITORING_REQUIRES_REVIEW",
                        severity="needs_review",
                        symbol=change.symbol,
                    )
                )
    if not any(t.delta_quantity != 0 for t in result.trades):
        result.reasons.append(
            GateReason(code="NO_POSITION_CHANGE", severity="research_only")
        )
    if datetime.now(UTC) >= result.expires_at:
        result.reasons.append(
            GateReason(code="PROPOSAL_EXPIRED", severity="needs_review")
        )
