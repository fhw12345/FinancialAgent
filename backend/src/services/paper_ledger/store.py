"""Single-document append-only PAPER aggregates; projections replay, never shadow-write."""

import json
from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ...core.exceptions import AppError, NotFoundError
from ...database.repositories.evidence_repository import EvidenceStorage
from ...models.paper_ledger import (
    CreatePaper,
    InitialInput,
    PaperEvent,
    PaperExperiment,
    Payload,
    ValuationInput,
)
from ..evidence.identity import digest
from .accounting import PaperInvalid, replay

COLLECTION = "paper_experiments"


class PaperConflict(AppError):
    status_code = 409
    error_type = "paper_ledger_conflict"


def hash_event(event: PaperEvent) -> str:
    return digest(event.model_dump(mode="json", exclude={"event_hash"}))


def event(
    experiment_id: str,
    sequence: int,
    request_id: str,
    request_hash: str,
    payload: Payload,
    previous_hash: str,
) -> PaperEvent:
    made = PaperEvent(
        event_id="paper_event_" + digest([experiment_id, request_id]),
        sequence=sequence,
        request_id=request_id,
        request_hash=request_hash,
        recorded_at=datetime.now(UTC),
        payload=payload,
        previous_hash=previous_hash,
        event_hash="",
    )
    made.event_hash = hash_event(made)
    return made


def validate(value: PaperExperiment) -> PaperExperiment:
    if value.sequence != len(value.events):
        raise PaperConflict("PAPER_SEQUENCE_INTEGRITY")
    previous = ""
    identities = set()
    for sequence, row in enumerate(value.events, 1):
        if (
            row.sequence != sequence
            or row.previous_hash != previous
            or row.event_hash != hash_event(row)
            or row.request_id in identities
            or row.event_id
            != "paper_event_" + digest([value.experiment_id, row.request_id])
        ):
            raise PaperConflict("PAPER_EVENT_INTEGRITY")
        if (
            isinstance(row.payload, ValuationInput)
            and row.payload.ledger_sequence != sequence - 1
        ):
            raise PaperConflict("PAPER_VALUATION_SEQUENCE_INTEGRITY")
        if row.recorded_at.tzinfo is None or (
            sequence > 1 and row.recorded_at < value.events[sequence - 2].recorded_at
        ):
            raise PaperConflict("PAPER_EVENT_TIME_INTEGRITY")
        identities.add(row.request_id)
        previous = row.event_hash
    try:
        replay(value.events)
    except ValueError as error:
        code = (
            str(error)
            if isinstance(error, PaperInvalid)
            else "PAPER_POSITION_RANGE_INVALID"
        )
        raise PaperConflict(code) from error
    return value


def parse(row: dict[str, object]) -> PaperExperiment:
    row.pop("_id", None)
    return validate(PaperExperiment.model_validate(row))


async def get(db: EvidenceStorage, identifier: str) -> PaperExperiment:
    row = await db.get_collection(COLLECTION).find_one({"_id": identifier})
    if row is None:
        raise NotFoundError("Paper experiment not found")
    return parse(row)


async def create(db: EvidenceStorage, body: CreatePaper) -> PaperExperiment:
    identifier = "paper_" + digest(body.request_id)
    fingerprint = digest(body.model_dump(mode="json"))
    initial = event(
        identifier,
        1,
        body.request_id,
        fingerprint,
        InitialInput(settings=body.settings),
        "",
    )
    made = PaperExperiment(experiment_id=identifier, sequence=1, events=[initial])
    document = made.model_dump(mode="json")
    try:
        row = await db.get_collection(COLLECTION).find_one_and_update(
            {"_id": identifier},
            {"$setOnInsert": document},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        row = await db.get_collection(COLLECTION).find_one({"_id": identifier})
    if row is None:
        raise RuntimeError("Paper creation returned no durable record")
    saved = parse(row)
    if saved.events[0].request_hash != fingerprint:
        raise PaperConflict("Paper creation request has different inputs")
    return saved


def replay_request(current: PaperExperiment, request_id: str, fingerprint: str) -> bool:
    found = next((e for e in current.events if e.request_id == request_id), None)
    if found is not None and found.request_hash != fingerprint:
        raise PaperConflict("Paper request has different inputs")
    return found is not None


async def append(
    db: EvidenceStorage,
    current: PaperExperiment,
    addition: PaperEvent,
    deadline: datetime | None = None,
) -> PaperExperiment:
    if len(current.events) >= 500:
        raise PaperConflict("Paper journal budget exhausted; history is retained")
    made = PaperExperiment(
        experiment_id=current.experiment_id,
        sequence=current.sequence + 1,
        events=[*current.events, addition],
    )
    validate(made)
    document = made.model_dump(mode="json")
    if len(json.dumps(document).encode()) > 2 * 1024 * 1024:
        raise PaperConflict("Paper journal exceeds the 2 MiB budget")
    row = await db.get_collection(COLLECTION).find_one_and_update(
        {
            "_id": current.experiment_id,
            "sequence": current.sequence,
            **({"$expr": {"$lt": ["$$NOW", deadline]}} if deadline else {}),
        },
        {"$set": document},
        return_document=ReturnDocument.AFTER,
    )
    if row is None:
        # Concurrent identical requests may both prepare; only one appends. Return
        # its committed event, never retry a changed input or an expired valuation.
        latest = await get(db, current.experiment_id)
        if replay_request(latest, addition.request_id, addition.request_hash):
            return latest
        raise PaperConflict("Paper ledger changed or valuation session expired; reload")
    return parse(row)
