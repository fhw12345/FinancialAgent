"""Prepare → deterministic checks → atomic publication/approval. Never touches an account ledger."""

from datetime import UTC, datetime

from ...core.exceptions import NotFoundError
from ...database.repositories.evidence_repository import EvidenceStorage
from ...models.decision_review import (
    ApprovalEvent,
    ApprovalReceipt,
    ApproveReview,
    ControlEvent,
    ProposeReview,
    ReviewPointer,
    ReviewView,
    RevisionRequest,
)
from ...models.model_decision import ModelDecisionRecord
from ..evidence.identity import digest
from . import control, policies, review_gate, review_storage
from .review_projection import project, readiness


async def get(db: EvidenceStorage, identifier: str) -> ReviewView:
    batch = await review_storage.load(db, identifier)
    if batch is None:
        raise NotFoundError("Review batch not found")
    return await project(db, batch)


async def recent(db: EvidenceStorage) -> list[ReviewView]:
    state = await control.read(db)
    return [await get(db, p.batch_id) for p in reversed(state.published[-20:])]


async def propose(
    db: EvidenceStorage,
    request: ProposeReview,
    model: ModelDecisionRecord | None = None,
) -> ReviewView:
    identifier = "review_" + digest(request.request_id)
    existing = await review_storage.load(db, identifier)
    current = await control.read(db)
    if existing:
        if existing.request_hash != digest(
            request.model_dump(mode="json")
        ) or existing.model_decision != (model if model else None):
            raise control.ReviewConflict("Proposal request ID has different inputs")
        if not any(p.batch_id == identifier for p in current.published):
            raise control.ReviewConflict(
                "Unpublished preparation; use a new request ID after reloading"
            )
        return await project(db, existing)
    control.check(current, request)
    if len(current.published) >= 200:
        raise control.ReviewConflict(
            "Review history budget exhausted; history is retained"
        )
    batch = await review_gate.evaluate(db, request, policies.active(current), model)
    await review_storage.save(db, review_storage.BATCHES, batch.batch_id, batch)
    pointer = ReviewPointer(
        batch_id=batch.batch_id,
        receipt_hash=batch.receipt_hash,
        world_revision=current.revision,
    )
    await control.commit(
        db,
        current,
        current.model_copy(
            update={
                "generation": current.generation + 1,
                "current": pointer,
                "published": [*current.published, pointer],
            }
        ),
        deadline=batch.expires_at if not batch.reasons else None,
    )
    return await project(db, batch)


async def approve(
    db: EvidenceStorage, identifier: str, request: ApproveReview
) -> ReviewView:
    current = await control.read(db)
    fingerprint = digest(
        {"batch_id": identifier, "request": request.model_dump(mode="json")}
    )
    replay = next(
        (e for e in current.approvals if e.request.request_id == request.request_id),
        None,
    )
    if replay:
        if replay.batch_id != identifier or replay.request_hash != fingerprint:
            raise control.ReviewConflict("Approval request ID has different inputs")
        return await get(db, identifier)
    control.check(current, request)
    view = await get(db, identifier)
    if (
        not view.approvable
        or current.current is None
        or current.current.batch_id != identifier
    ):
        raise control.ReviewConflict("Review batch is not currently ready for approval")
    if len(current.approvals) >= 200:
        raise control.ReviewConflict(
            "Approval history budget exhausted; history is retained"
        )
    selected = set(request.symbols)
    if not selected <= {t.symbol for t in view.batch.request.targets}:
        raise control.ReviewConflict("Approval subset includes an unauthorized target")
    evaluation = await review_gate.evaluate(
        db,
        ProposeReview(
            expected_revision=request.expected_revision,
            expected_generation=request.expected_generation,
            request_id=request.request_id,
            assessment_id=view.batch.request.assessment_id,
            targets=[t for t in view.batch.request.targets if t.symbol in selected],
        ),
        policies.active(current),
        view.batch.model_decision,
    )
    if (
        readiness(evaluation.reasons) != "ready"
        or evaluation.source_hash != view.batch.source_hash
    ):
        raise control.ReviewConflict(
            "Selected subset rejected: "
            + ", ".join(r.code for r in evaluation.reasons),
            reasons=[r.model_dump(mode="json") for r in evaluation.reasons],
            evaluation=evaluation.model_dump(mode="json"),
        )
    approval_id = "review_approval_" + digest(request.request_id)
    receipt = ApprovalReceipt(
        approval_id=approval_id,
        request_hash=fingerprint,
        receipt_hash="",
        batch_id=identifier,
        evaluation=evaluation,
    )
    receipt.receipt_hash = review_storage.receipt_hash(receipt)
    await review_storage.save(db, review_storage.APPROVALS, approval_id, receipt)
    event = ApprovalEvent(
        approval_id=approval_id,
        batch_id=identifier,
        request=request,
        request_hash=fingerprint,
        receipt_hash=receipt.receipt_hash,
        approved_at=datetime.now(UTC),
        world_revision=current.revision,
        generation=current.generation + 1,
    )
    await control.commit(
        db,
        current,
        current.model_copy(
            update={
                "generation": current.generation + 1,
                "current": current.current.model_copy(
                    update={"state": "approved", "approval_id": approval_id}
                ),
                "approvals": [*current.approvals, event],
            }
        ),
        deadline=min(view.batch.expires_at, evaluation.expires_at),
    )
    return await get(db, identifier)


async def cancel(
    db: EvidenceStorage, identifier: str, request: RevisionRequest
) -> ReviewView:
    current = await control.read(db)
    event = ControlEvent(
        request_id=request.request_id,
        request_hash=digest(request.model_dump(mode="json")),
        kind="cancel",
        batch_id=identifier,
    )
    if policies.event_replay(current, event):
        return await get(db, identifier)
    control.check(current, request, clean=False)
    if current.current is None or current.current.batch_id != identifier:
        raise control.ReviewConflict("Only the current review can be cancelled")
    await control.commit(
        db,
        current,
        current.model_copy(
            update={
                "generation": current.generation + 1,
                "current": current.current.model_copy(
                    update={
                        "state": "cancelled",
                        "cancellation_request": request.request_id,
                    }
                ),
                "events": [*current.events, event],
            }
        ),
    )
    return await get(db, identifier)
