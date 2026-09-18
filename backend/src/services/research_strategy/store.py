"""Bounded immutable strategy versions plus one CAS active pointer; no inference on configuration."""

from datetime import UTC, datetime

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ...core.exceptions import AppError
from ...database.repositories.evidence_repository import EvidenceStorage
from ...models.research_strategy import (
    StrategyParameters,
    StrategyState,
    StrategyVersion,
)
from ...services.evidence.identity import digest
from ...services.portfolio_risk.service import policy_state


class StrategyConflict(AppError):
    status_code = 409
    error_type = "strategy_revision_changed"


async def state(db: EvidenceStorage) -> StrategyState:
    row = await db.get_collection("research_strategy_state").find_one({"_id": "local"})
    if row is None:
        return StrategyState()
    row.pop("_id", None)
    return StrategyState.model_validate(row)


def active_version(current: StrategyState) -> StrategyVersion | None:
    if current.active_version is None:
        return None
    found = next(
        (v for v in current.versions if v.version_id == current.active_version), None
    )
    if found is None:
        raise StrategyConflict("Active strategy version is missing")
    return found.model_copy(deep=True)


async def active(db: EvidenceStorage) -> StrategyVersion | None:
    return active_version(await state(db))


async def confirm(
    db: EvidenceStorage,
    params: StrategyParameters,
    expected: int,
    request_id: str,
    cost_revision: int,
) -> StrategyState:
    previous = await state(db)
    fingerprint = digest(
        {
            "parameters": params.model_dump(mode="json"),
            "cost_revision": cost_revision,
            "pilot": "fundamental-252@1",
        }
    )
    replay = next((v for v in previous.versions if v.request_id == request_id), None)
    if replay:
        if replay.input_hash != fingerprint:
            raise StrategyConflict("Request key has different parameters")
        return previous
    if expected != previous.revision:
        raise StrategyConflict("Strategy changed; reload")
    if len(previous.versions) >= 100:
        raise StrategyConflict("Strategy version budget exhausted; history is retained")
    costs = await policy_state(db)
    if (
        costs.policy is None
        or costs.confirmed_at is None
        or costs.revision != cost_revision
    ):
        raise StrategyConflict("Confirm/reload the cost policy first")
    version = StrategyVersion(
        version_id="strategy_" + digest([expected + 1, fingerprint]),
        revision=expected + 1,
        parameters=params,
        cost_policy_revision=cost_revision,
        cost_policy=costs.policy,
        confirmed_at=datetime.now(UTC),
        request_id=request_id,
        input_hash=fingerprint,
    )
    next_state = StrategyState(
        revision=expected + 1,
        active_version=version.version_id,
        versions=[*previous.versions, version],
    )
    await _save(db, next_state, expected)
    return next_state


async def deactivate(db: EvidenceStorage, expected: int) -> StrategyState:
    previous = await state(db)
    if previous.revision != expected:
        raise StrategyConflict("Strategy changed; reload")
    next_state = previous.model_copy(
        update={"revision": expected + 1, "active_version": None}
    )
    await _save(db, next_state, expected)
    return next_state


async def _save(db: EvidenceStorage, value: StrategyState, expected: int) -> None:
    try:
        saved = await db.get_collection("research_strategy_state").find_one_and_update(
            {"_id": "local", "revision": expected},
            {"$set": value.model_dump(mode="json")},
            upsert=expected == 0,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError as error:
        raise StrategyConflict("Concurrent strategy change; reload") from error
    if saved is None:
        raise StrategyConflict("Concurrent strategy change; reload")
