"""Publish stored model decisions through the unchanged review gate. No model calls here."""

from ...database.repositories.evidence_repository import EvidenceStorage
from ...models.decision_review import (
    ProposeReview,
    ReviewTarget,
    ReviewView,
    RevisionRequest,
)
from ...models.model_decision import ModelDecisionRecord
from ..evidence.identity import digest
from . import control, review_service, review_storage
from .model_decision import ModelDecisionView, get


def targets(record: ModelDecisionRecord) -> list[ReviewTarget]:
    decisions = record.output.decisions if record.output else []
    return [
        ReviewTarget(symbol=d.symbol, target_weight=d.target_weight)
        for d in decisions
        if d.action != "HOLD" and d.target_weight is not None
    ]


async def latest_review(
    db: EvidenceStorage, record: ModelDecisionRecord
) -> ReviewView | None:
    state = await control.read(db)
    published = [p.batch_id for p in state.published]
    for batch_id in reversed(published):
        batch = await review_storage.load(db, batch_id)
        if (
            batch
            and batch.model_decision
            and (batch.model_decision.decision_id == record.decision_id)
        ):
            return await review_service.get(db, batch_id)
    return None


async def publish(
    db: EvidenceStorage, record: ModelDecisionRecord, revision: RevisionRequest
) -> ModelDecisionView:
    if record.status != "completed" or record.output is None:
        raise control.ReviewConflict("Only a completed model decision can be reviewed")
    wanted = targets(record)
    if not wanted:
        return ModelDecisionView(
            record=record,
            review_error="All decisions are HOLD/WAIT; there is no change to approve.",
        )
    request = ProposeReview(
        expected_revision=revision.expected_revision,
        expected_generation=revision.expected_generation,
        # Disjoint from manual proposal IDs; bound to this stored model output.
        request_id="mdr_" + digest([record.decision_id, revision.request_id])[:48],
        assessment_id=record.assessment_id,
        targets=wanted,
    )
    try:
        review = await review_service.propose(db, request, record)
    except control.ReviewConflict as error:
        return ModelDecisionView(record=record, review_error=error.message)
    return ModelDecisionView(record=record, review=review)


async def revalidate(
    db: EvidenceStorage, decision_id: str, revision: RevisionRequest
) -> ModelDecisionView:
    """Re-run all gates for a stored decision after inputs changed. Never re-calls a model."""
    return await publish(db, await get(db, decision_id), revision)


async def view(db: EvidenceStorage, decision_id: str) -> ModelDecisionView:
    record = await get(db, decision_id)
    return ModelDecisionView(record=record, review=await latest_review(db, record))
