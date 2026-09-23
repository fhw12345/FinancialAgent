"""Explicit, bounded, replay-safe model decision calls. The output is never an order."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ...core.config import get_settings
from ...core.exceptions import NotFoundError
from ...core.llm_roles import model_role_scope
from ...database.repositories.evidence_repository import EvidenceStorage
from ...models.decision_assessment import DecisionAssessment
from ...models.decision_review import (
    Confirmed,
    RequestId,
    ReviewPolicyVersion,
    ReviewView,
    Revision,
    RevisionRequest,
)
from ...models.model_decision import (
    ModelDecisionRecord,
    ModelDecisionSet,
    ModelProvenance,
)
from ...models.portfolio_risk import Record
from ..evidence.identity import digest
from . import control, model_decision_gate, policies, review_gate

COLLECTION = "review_model_decisions"
LEASE = timedelta(seconds=300)


class RequestModelDecision(Record):
    expected_revision: Revision
    expected_generation: Revision
    request_id: RequestId
    assessment_id: str = Field(pattern=r"^assessment_[a-f0-9]{32}$")
    confirm: Confirmed
    acknowledgment: Literal["uses-model-allowance-recommendation-only-no-trade"]


class ModelDecisionView(Record):
    record: ModelDecisionRecord
    review: ReviewView | None = None
    review_error: str | None = None


def _parse(row: dict[str, Any]) -> ModelDecisionRecord:
    row.pop("_id", None)
    return ModelDecisionRecord.model_validate(row)


async def get(db: EvidenceStorage, decision_id: str) -> ModelDecisionRecord:
    row = await db.get_collection(COLLECTION).find_one({"_id": decision_id})
    if row is None:
        raise NotFoundError("Model decision not found")
    return _parse(row)


async def recent(db: EvidenceStorage) -> list[ModelDecisionRecord]:
    rows = [_parse(r) async for r in db.get_collection(COLLECTION).find({})]
    return sorted(rows, key=lambda r: r.created_at, reverse=True)[:20]


async def eligible(
    db: EvidenceStorage, assessment_id: str
) -> tuple[ReviewPolicyVersion, DecisionAssessment, list[str]]:
    """Reject before any paid call when a decision could not possibly be reviewed."""
    state = await control.read(db)
    policy = policies.active(state)
    if policy is None or policy.policy.model_decisions != "propose_for_human_review":
        raise control.ReviewConflict(
            "Model decisions are not enabled by a confirmed policy"
        )
    source = await review_gate.source_record(db, assessment_id)
    if source is None:
        raise NotFoundError("Research source not found")
    reasons = await review_gate.source_reasons(db, source)
    settings = await policies.settings(db)
    blocking = [r.code for r in reasons] + [
        r for r in settings.reasons if r != "REVIEW_POLICY_UNCONFIRMED"
    ]
    if blocking:
        raise control.ReviewConflict(
            "Research source is not eligible for a model decision: "
            + ", ".join(sorted(set(blocking)))
        )
    symbols = model_decision_gate.scope(source, policy)
    if not symbols or len(symbols) > 20:
        raise control.ReviewConflict("Model decision scope must contain 1-20 symbols")
    return policy, source, symbols


async def prompt(
    db: EvidenceStorage,
    policy: ReviewPolicyVersion,
    source: DecisionAssessment,
    symbols: list[str],
) -> str:
    from ...agent.prompt_registry import get_prompt
    from ..portfolio_risk.service import policy_state

    risk = source.portfolio_risk
    costs = await policy_state(db)
    current = risk.current if risk else None
    receipts = []
    for symbol in symbols:
        review = next(
            (
                r
                for r in (source.strategy.reviews if source.strategy else [])
                if r.symbol == symbol
            ),
            None,
        )
        allowed = sorted(await model_decision_gate.allowed_evidence(db, source, symbol))
        receipts.append(
            {
                "symbol": symbol,
                "held": bool(
                    risk and any(p.symbol == symbol for p in risk.snapshot.positions)
                ),
                "current_weight": (
                    current.position_weights.get(symbol, 0.0) if current else None
                ),
                "strategy": (
                    review.model_dump(
                        mode="json",
                        include={
                            "status",
                            "valuations",
                            "checks",
                            "errors",
                            "conclusion",
                        },
                    )
                    if review
                    else None
                ),
                "evidence_ids": allowed[:60],
            }
        )
    research = "\n\n".join(
        f"## {r.symbol}\n{r.research[:6000]}"
        for r in source.results
        if r.symbol in symbols
    )
    return get_prompt("portfolio-model-decision").render(
        scope=", ".join(symbols),
        may_open=policy.policy.model_may_open,
        may_exit=policy.policy.model_may_exit,
        limits=json.dumps(
            {
                "risk_policy": (
                    costs.policy.model_dump(mode="json") if costs.policy else None
                ),
                "max_account_sigma": policy.policy.max_account_sigma,
            }
        ),
        account=json.dumps(
            {
                "equity": current.equity if current else None,
                "cash_weight": current.cash_weight if current else None,
                "position_weights": current.position_weights if current else {},
                "sector_weights": current.sector_weights if current else {},
                "session": str(risk.snapshot.session_date) if risk else None,
            }
        ),
        receipts=json.dumps(receipts, ensure_ascii=False),
        research=research,
    )


def provenance() -> ModelProvenance:
    settings = get_settings()
    if settings.llm_provider == "github_copilot":
        from ..copilot.context import current_profile

        profile = current_profile("portfolio_decisions")
        return ModelProvenance(
            provider="github_copilot",
            model=profile.model,
            api=profile.api,
            routing_revision=profile.routing_revision,
        )
    return ModelProvenance(
        provider=settings.llm_provider, model=settings.model_portfolio_decisions
    )


def fingerprint(body: RequestModelDecision) -> str:
    return digest(
        body.model_dump(
            mode="json", exclude={"expected_revision", "expected_generation"}
        )
    )


async def claim(
    db: EvidenceStorage,
    body: RequestModelDecision,
    policy: ReviewPolicyVersion,
    source: DecisionAssessment,
    symbols: list[str],
) -> tuple[ModelDecisionRecord, bool]:
    """Return (record, owned). Only an owned running claim may call the model."""
    identifier = "model_decision_" + digest(body.request_id)
    request_hash = fingerprint(body)
    now = datetime.now(UTC)
    fresh = ModelDecisionRecord(
        decision_id=identifier,
        request_id=body.request_id,
        request_hash=request_hash,
        assessment_id=source.assessment_id,
        source_hash=source.input_hash,
        policy_version_id=policy.version_id,
        scope=symbols,
        status="running",
        owner=uuid4().hex,
        lease_until=now + LEASE,
        created_at=now,
    )
    collection = db.get_collection(COLLECTION)
    try:
        row = await collection.find_one_and_update(
            {"_id": identifier},
            {"$setOnInsert": fresh.model_dump(mode="json")},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        row = await collection.find_one({"_id": identifier})
    if row is None:
        raise RuntimeError("Model decision claim returned no record")
    existing = _parse(row)
    if existing.request_hash != request_hash:
        raise control.ReviewConflict("Model decision request ID has different inputs")
    if existing.owner == fresh.owner:
        return existing, True
    if existing.status == "running" and existing.lease_until.astimezone(UTC) > now:
        raise control.ReviewConflict("This model decision is already running")
    if existing.status == "running":
        # An expired claim may be taken over exactly once; the stale owner is fenced.
        taken = await collection.find_one_and_update(
            {"_id": identifier, "owner": existing.owner, "status": "running"},
            {"$set": {"owner": fresh.owner, "lease_until": (now + LEASE).isoformat()}},
            return_document=ReturnDocument.AFTER,
        )
        if taken is None:
            raise control.ReviewConflict("This model decision is already running")
        return _parse(taken), True
    return existing, False


async def finish(
    db: EvidenceStorage, record: ModelDecisionRecord, **fields: Any
) -> ModelDecisionRecord:
    update = record.model_copy(update={**fields, "completed_at": datetime.now(UTC)})
    row = await db.get_collection(COLLECTION).find_one_and_update(
        {"_id": record.decision_id, "owner": record.owner, "status": "running"},
        {"$set": update.model_dump(mode="json")},
        return_document=ReturnDocument.AFTER,
    )
    if row is None:
        raise control.ReviewConflict("Model decision claim was lost; not recorded")
    return _parse(row)


async def decide(
    db: EvidenceStorage, agent: Any, body: RequestModelDecision
) -> ModelDecisionView:
    from . import model_review

    current = await control.read(db)
    stored = await db.get_collection(COLLECTION).find_one(
        {"_id": "model_decision_" + digest(body.request_id)}
    )
    if stored is not None and stored.get("status") != "running":
        # Replay never needs current revisions or eligibility and never re-calls a model.
        record = _parse(stored)
        if record.request_hash != fingerprint(body):
            raise control.ReviewConflict(
                "Model decision request ID has different inputs"
            )
        if record.status == "failed":
            raise control.ReviewConflict(
                "This model decision failed; use a new request ID"
            )
        return ModelDecisionView(
            record=record, review=await model_review.latest_review(db, record)
        )
    control.check(current, body_revision(body))
    policy, source, symbols = await eligible(db, body.assessment_id)
    record, owned = await claim(db, body, policy, source, symbols)
    if not owned:
        if record.status == "failed":
            raise control.ReviewConflict(
                "This model decision failed; use a new request ID"
            )
        return ModelDecisionView(
            record=record, review=await model_review.latest_review(db, record)
        )
    if agent is None:
        await finish(db, record, status="failed", error_code="AGENT_UNAVAILABLE")
        raise control.ReviewConflict("Portfolio agent is unavailable")
    text = await prompt(db, policy, source, symbols)
    try:
        with model_role_scope("react_agent", "portfolio_decisions"):
            made_by = provenance()
            raw = await agent.react_agent.ainvoke_structured(
                prompt=text, schema=ModelDecisionSet, context=None
            )
        output = ModelDecisionSet.model_validate(
            raw.model_dump() if hasattr(raw, "model_dump") else raw
        )
    except BaseException as error:
        # Cancellation/failure is recorded, never left looking like an in-flight success.
        # The partial call cannot be resumed; the user explicitly starts a new request.
        closing = asyncio.create_task(
            finish(db, record, status="failed", error_code=type(error).__name__[:80])
        )
        try:
            await asyncio.shield(closing)
        except asyncio.CancelledError:
            await closing
        raise
    record = await finish(
        db, record, status="completed", output=output, provenance=made_by
    )
    return await model_review.publish(db, record, body_revision(body))


def body_revision(body: RequestModelDecision) -> RevisionRequest:
    return RevisionRequest(
        expected_revision=body.expected_revision,
        expected_generation=body.expected_generation,
        request_id=body.request_id,
    )
