"""Immutable confirmation/replay/CAS and deactivation never mutate historical assumptions."""

import asyncio
import copy
from unittest.mock import AsyncMock
from datetime import UTC, datetime
import pytest
from src.services.research_strategy import store
from src.models.research_strategy import StrategyVersion
from tests.strategy_fixtures import parameters
from tests.evidence_fixtures import Database
from tests.portfolio_risk_fixtures import policy


def database():
    db = Database()
    db.get_collection("risk_policy").rows["local"] = {
        "_id": "local",
        **policy().model_dump(mode="json"),
    }
    return db


@pytest.mark.asyncio
async def test_no_defaults_explicit_version_and_idempotent_request():
    db = database()
    assert await store.active(db) is None
    first = await store.confirm(db, parameters(), 0, "first", 1)
    original = first.versions[0].model_dump(mode="json")
    assert (
        first.versions[0].horizon == 252
        and first.versions[0].benchmark == "SPY_total_return@1"
    )
    assert (
        await store.confirm(db, parameters(), 0, "first", 1)
    ).model_dump() == first.model_dump()
    with pytest.raises(store.StrategyConflict):
        await store.confirm(db, parameters(growth_rate=0.04), 0, "first", 1)
    second = await store.confirm(db, parameters(growth_rate=0.04), 1, "second", 1)
    assert (
        len(second.versions) == 2
        and second.versions[0].model_dump(mode="json") == original
    )
    assert second.versions[0].version_id != second.versions[1].version_id
    await store.deactivate(db, 2)
    assert await store.active(db) is None
    assert len((await store.confirm(db, parameters(), 0, "first", 1)).versions) == 2
    assert (
        await store.active(db) is None
    )  # late replay cannot resurrect deactivated config
    corrupted = {**original, "horizon": 60}
    with pytest.raises(ValueError):
        StrategyVersion.model_validate(corrupted)


@pytest.mark.asyncio
async def test_concurrent_confirm_has_one_winner_and_costs_are_required():
    db = database()
    outcomes = await asyncio.gather(
        *(store.confirm(db, parameters(), 0, str(i), 1) for i in range(8)),
        return_exceptions=True,
    )
    assert sum(isinstance(r, store.StrategyConflict) for r in outcomes) == 7
    with pytest.raises(store.StrategyConflict):
        await store.deactivate(db, 0)
    with pytest.raises(store.StrategyConflict):
        await store.confirm(db, parameters(), 1, "new", 2)
    db.get_collection("risk_policy").rows.clear()
    with pytest.raises(store.StrategyConflict):
        await store.confirm(db, parameters(), 1, "new", 1)


@pytest.mark.asyncio
async def test_storage_error_does_not_report_a_saved_version():
    db = database()
    collection = db.get_collection("research_strategy_state")
    collection.find_one_and_update = AsyncMock(side_effect=RuntimeError("disk offline"))
    with pytest.raises(RuntimeError):
        await store.confirm(db, parameters(), 0, "key", 1)
    assert await store.active(db) is None
