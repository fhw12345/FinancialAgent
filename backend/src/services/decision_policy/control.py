"""One atomic publication boundary shared with all supported input mutations."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import wraps
from inspect import signature
from typing import Any, cast
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ...core.exceptions import AppError
from ...database.repositories.evidence_repository import EvidenceStorage
from ...models.decision_review import ReviewControl, RevisionRequest

COLLECTION = "review_control"
_active: ContextVar[frozenset[str]] = ContextVar(
    "review_mutations", default=frozenset()
)


class ReviewConflict(AppError):
    status_code = 409
    error_type = "review_revision_changed"


async def read(db: EvidenceStorage) -> ReviewControl:
    row = await db.get_collection(COLLECTION).find_one({"_id": "local"})
    if row is None:
        return ReviewControl()
    row.pop("_id", None)
    return ReviewControl.model_validate(row)


async def ensure(db: EvidenceStorage) -> None:
    try:
        await db.get_collection(COLLECTION).update_one(
            {"_id": "local"},
            {"$setOnInsert": ReviewControl().model_dump(mode="json")},
            upsert=True,
        )
    except DuplicateKeyError:
        # Another first writer created the same unique aggregate.
        pass


def check(
    current: ReviewControl, request: RevisionRequest, *, clean: bool = True
) -> None:
    if (current.revision, current.generation) != (
        request.expected_revision,
        request.expected_generation,
    ):
        raise ReviewConflict("Inputs or review changed; reload before continuing")
    if current.mutations:
        raise ReviewConflict("Account/configuration mutation is in flight")
    if clean and current.uncertain:
        raise ReviewConflict("Declared account reconciliation is required")


async def commit(
    db: EvidenceStorage,
    previous: ReviewControl,
    next_state: ReviewControl,
    *,
    deadline: datetime | None = None,
) -> ReviewControl:
    """Prepared records become authoritative only through this same-document CAS."""
    await ensure(db)
    row = await db.get_collection(COLLECTION).find_one_and_update(
        {
            "_id": "local",
            "revision": previous.revision,
            "generation": previous.generation,
            "mutations": {},
            "uncertain": previous.uncertain,
            **({"$expr": {"$lt": ["$$NOW", deadline]}} if deadline else {}),
        },
        {"$set": next_state.model_dump(mode="json")},
        return_document=ReturnDocument.AFTER,
    )
    if row is None:
        raise ReviewConflict(
            "Concurrent input/review change or expired lifetime; nothing was published"
        )
    row.pop("_id", None)
    return ReviewControl.model_validate(row)


@asynccontextmanager
async def mutation(db: EvidenceStorage) -> AsyncIterator[None]:
    """No expiry/force-unlock. A failed writer cannot be mistaken for unchanged inputs.

    Bookkeeping is NEVER gated on policy/readiness/uncertainty. The ticket simply keeps
    partial writes out of approval. Nested ledger/repository writes share a ticket.
    """
    collection = db.get_collection(COLLECTION)
    key = str(collection.full_name)
    if key in _active.get():
        yield
        return
    await ensure(db)
    identifier = uuid4().hex
    announced = await collection.update_one(
        {"_id": "local"},
        {
            "$inc": {"revision": 1},
            "$set": {f"mutations.{identifier}": datetime.now(UTC).isoformat()},
        },
    )
    if announced.modified_count != 1:
        raise ReviewConflict("Mutation announcement failed; no input write allowed")
    token = _active.set(_active.get() | {key})
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        _active.reset(token)
        update: dict[str, Any] = {
            "$inc": {"revision": 1},
            "$unset": {f"mutations.{identifier}": ""},
        }
        if failed:
            update["$set"] = {"uncertain": True}

        async def finish() -> None:
            result = await collection.update_one(
                {"_id": "local", f"mutations.{identifier}": {"$exists": True}}, update
            )
            if result.modified_count != 1:
                raise ReviewConflict("Mutation ticket missing; reconcile offline")

        # Even cancellation must not expose partial writes as a clean revision.
        closing = asyncio.create_task(finish())
        try:
            await asyncio.shield(closing)
        except asyncio.CancelledError:
            await closing
            raise


def repository_write[
    **P, T
](function: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    @wraps(function)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        repository = cast(Any, args[0])
        async with mutation(repository.collection.database):
            return await function(*args, **kwargs)

    return wrapped


def service_write[
    **P, T
](function: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    @wraps(function)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        db = cast(
            EvidenceStorage, args[0] if args else kwargs.get("db", kwargs.get("mongo"))
        )
        async with mutation(db):
            return await function(*args, **kwargs)

    return wrapped


def ledger_write[
    **P, T
](function: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    resolved = signature(function, eval_str=True)

    @wraps(function)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
        repository = resolved.bind(*args, **kwargs).arguments["holding_repo"]
        async with mutation(repository.collection.database):
            return await function(*args, **kwargs)

    # Preserve resolved FastAPI annotations, not forward names in this module's globals.
    wrapped.__dict__["__signature__"] = resolved
    return wrapped
