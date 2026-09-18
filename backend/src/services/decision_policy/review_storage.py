"""Immutable preparations. Only review_control can attest publication or approval."""

import json

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ...database.repositories.evidence_repository import EvidenceStorage
from ...models.decision_review import ApprovalReceipt, PreparedReview
from ..evidence.identity import digest
from .control import ReviewConflict

BATCHES = "review_batches"
APPROVALS = "review_approval_receipts"


def receipt_hash(value: PreparedReview | ApprovalReceipt) -> str:
    return digest(value.model_dump(mode="json", exclude={"receipt_hash"}))


async def save[
    T: (PreparedReview, ApprovalReceipt)
](db: EvidenceStorage, collection: str, identifier: str, value: T) -> T:
    document = value.model_dump(mode="json")
    if len(json.dumps(document).encode()) > 2 * 1024 * 1024:
        raise ReviewConflict("Review receipt exceeds the bounded storage budget")
    if value.receipt_hash != receipt_hash(value):
        raise ReviewConflict("Review receipt hash mismatch")
    try:
        row = await db.get_collection(collection).find_one_and_update(
            {"_id": identifier},
            {"$setOnInsert": document},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        row = await db.get_collection(collection).find_one({"_id": identifier})
    if row is None:
        raise RuntimeError("Review preparation persistence returned no record")
    row.pop("_id", None)
    if row != document:
        raise ReviewConflict("Concurrent/different preparation for this request ID")
    return value


async def load(db: EvidenceStorage, identifier: str) -> PreparedReview | None:
    row = await db.get_collection(BATCHES).find_one({"_id": identifier})
    if row is None:
        return None
    row.pop("_id", None)
    result = PreparedReview.model_validate(row)
    if result.receipt_hash != receipt_hash(result):
        raise ReviewConflict("Stored review receipt hash mismatch")
    return result


async def approval(db: EvidenceStorage, identifier: str) -> ApprovalReceipt:
    row = await db.get_collection(APPROVALS).find_one({"_id": identifier})
    if row is None:
        raise ReviewConflict("Approval preparation is missing")
    row.pop("_id", None)
    result = ApprovalReceipt.model_validate(row)
    if result.receipt_hash != receipt_hash(result):
        raise ReviewConflict("Stored approval receipt hash mismatch")
    return result
