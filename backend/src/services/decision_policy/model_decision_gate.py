"""Deterministic checks of an explicit model decision; never resizes or rewrites it."""

from ...database.repositories.evidence_repository import (
    EvidenceConflict,
    EvidenceRepository,
    EvidenceStorage,
)
from ...models.decision_assessment import DecisionAssessment
from ...models.decision_review import GateReason, PreparedReview, ReviewPolicyVersion
from ...models.model_decision import ModelDecision, ModelDecisionRecord


def reason(code: str, severity: str, symbol: str | None = None) -> GateReason:
    return GateReason.model_validate(
        {"code": code, "severity": severity, "symbol": symbol}
    )


def scope(source: DecisionAssessment, policy: ReviewPolicyVersion) -> list[str]:
    allowed = set(policy.policy.allowed_symbols)
    return sorted({r.symbol for r in source.results} & allowed)


async def allowed_evidence(
    db: EvidenceStorage, source: DecisionAssessment, symbol: str
) -> set[str]:
    reviews = source.strategy.reviews if source.strategy else []
    review = next((r for r in reviews if r.symbol == symbol), None)
    if review is None:
        return set()
    try:
        snapshot = await EvidenceRepository(db).get(review.snapshot_id)
    except EvidenceConflict:
        return set()
    conflicted = {e for ids in snapshot.conflicts.values() for e in ids}
    return {
        r.evidence_id
        for r in snapshot.records
        if r.symbol == symbol
        and r.quality == "available"
        and r.evidence_id not in conflicted
    }


def stance(source: DecisionAssessment, symbol: str) -> str:
    for review in source.strategy.reviews if source.strategy else []:
        if review.symbol == symbol and review.conclusion:
            return review.conclusion.stance
    return "unknown"


async def check(
    db: EvidenceStorage,
    model: ModelDecisionRecord,
    source: DecisionAssessment,
    result: PreparedReview,
    policy: ReviewPolicyVersion,
) -> list[GateReason]:
    out: list[GateReason] = []
    if model.status != "completed" or model.output is None:
        return [reason("MODEL_DECISION_UNAVAILABLE", "blocked")]
    if (
        model.assessment_id != source.assessment_id
        or model.source_hash != source.input_hash
    ):
        out.append(reason("MODEL_DECISION_SOURCE_MISMATCH", "blocked"))
    if model.policy_version_id != policy.version_id:
        out.append(reason("MODEL_DECISION_POLICY_CHANGED", "needs_review"))
    if policy.policy.model_decisions != "propose_for_human_review":
        out.append(reason("MODEL_DECISIONS_DISABLED", "blocked"))
    decisions = model.output.decisions
    symbols = [d.symbol for d in decisions]
    if len(set(symbols)) != len(symbols):
        out.append(reason("MODEL_DECISION_DUPLICATE", "blocked"))
    if set(symbols) != set(model.scope) or set(model.scope) != set(
        scope(source, policy)
    ):
        out.append(reason("MODEL_DECISION_SCOPE_MISMATCH", "blocked"))
    targeted = {t.symbol for t in result.request.targets}
    by_symbol = {d.symbol: d for d in decisions}
    for symbol in sorted(targeted):
        decision = by_symbol.get(symbol)
        if decision is None or decision.action == "HOLD":
            out.append(reason("MODEL_DECISION_TARGET_MISMATCH", "blocked", symbol))
            continue
        if not any(
            t.symbol == symbol and t.target_weight == decision.target_weight
            for t in result.request.targets
        ):
            out.append(reason("MODEL_DECISION_TARGET_MISMATCH", "blocked", symbol))
        out.extend(await _decision(db, decision, source, result, policy))
    return out


async def _decision(
    db: EvidenceStorage,
    decision: ModelDecision,
    source: DecisionAssessment,
    result: PreparedReview,
    policy: ReviewPolicyVersion,
) -> list[GateReason]:
    symbol = decision.symbol
    out: list[GateReason] = []
    risk = result.risk or source.portfolio_risk
    held = bool(
        risk
        and any(p.symbol == symbol and p.quantity > 0 for p in risk.snapshot.positions)
    )
    if (decision.action == "BUY") == held:
        out.append(reason("MODEL_ACTION_EXPOSURE_CONFLICT", "blocked", symbol))
    if decision.action == "BUY" and not policy.policy.model_may_open:
        out.append(reason("MODEL_NEW_POSITION_NOT_PERMITTED", "blocked", symbol))
    if decision.action == "SELL" and not policy.policy.model_may_exit:
        out.append(reason("MODEL_EXIT_NOT_PERMITTED", "blocked", symbol))
    allowed = await allowed_evidence(db, source, symbol)
    if not decision.evidence_ids or not set(decision.evidence_ids) <= allowed:
        out.append(reason("MODEL_EVIDENCE_UNVERIFIED", "insufficient_evidence", symbol))
    view = stance(source, symbol)
    if decision.action in ("BUY", "ADD") and view != "bullish":
        out.append(reason("MODEL_ACTION_STANCE_CONFLICT", "needs_review", symbol))
    if decision.action == "SELL" and view == "bullish":
        out.append(reason("MODEL_ACTION_STANCE_CONFLICT", "needs_review", symbol))
    allocation = result.risk.allocation if result.risk else None
    change = next(
        (c for c in (allocation.changes if allocation else []) if c.symbol == symbol),
        None,
    )
    if change is None:
        return out
    delta, after = change.delta_quantity, change.proposed_quantity
    if delta == 0:
        out.append(reason("MODEL_TARGET_BELOW_LOT", "research_only", symbol))
    elif not {
        "BUY": delta > 0,
        "ADD": delta > 0,
        "REDUCE": delta < 0 and after > 0,
        "SELL": delta < 0 and after == 0,
    }[decision.action]:
        out.append(reason("MODEL_ACTION_DELTA_CONFLICT", "blocked", symbol))
    return out
