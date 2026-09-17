"""Atomic seal, replay, generation fencing, child preservation and real BSON encoding."""

import asyncio
from datetime import UTC, datetime, timedelta
from bson import BSON
import pytest
from src.database.repositories.evidence_repository import (
    EvidenceRepository,
    EvidenceConflict,
)
from src.services.evidence.claims import build_dossier
from src.services.evidence.context import evidence_scope, install_tools
from langchain_core.tools import tool
from tests.evidence_fixtures import Database
from tests.test_evidence_claims import record, NOW, claim
import json


async def begin(repo, **kw):
    return await repo.begin(
        request_key="same", run_id="run", symbol="AAPL", as_of=NOW, **kw
    )


@pytest.mark.asyncio
async def test_seal_is_atomic_and_replay_does_not_refetch_or_mutate():
    db = Database()
    repo = EvidenceRepository(db)
    pending = await begin(repo)
    with pytest.raises(EvidenceConflict):
        await repo.get(pending.snapshot_id)
    row = record(snapshot_id=pending.snapshot_id)
    sealed = await repo.finish(pending, [row])
    wire = sealed.model_dump(mode="json")
    BSON.encode(wire)
    row.value = 200.0
    assert (await begin(repo)).model_dump(mode="json") == wire
    assert (await repo.get(sealed.snapshot_id)).records[0].value == 100
    with pytest.raises(EvidenceConflict):
        await repo.finish(pending, [row])


@pytest.mark.asyncio
async def test_competing_collection_and_expired_owner_cannot_seal():
    db = Database()
    repo = EvidenceRepository(db)
    first = await begin(repo)
    with pytest.raises(EvidenceConflict):
        await begin(repo)
    db.get_collection("research_snapshots").rows[first.snapshot_id]["lease_until"] = (
        datetime.now(UTC) - timedelta(seconds=1)
    ).isoformat()
    second = await begin(repo)
    assert second.generation == first.generation + 1
    with pytest.raises(EvidenceConflict):
        await repo.finish(first, [record(snapshot_id=first.snapshot_id)])
    await repo.finish(second, [record(snapshot_id=second.snapshot_id)])


@pytest.mark.asyncio
async def test_cancel_failure_and_integrity_errors_are_not_sealed_success():
    db = Database()
    repo = EvidenceRepository(db)
    pending = await begin(repo)
    await repo.abort(pending, "CANCELLED", True)
    with pytest.raises(EvidenceConflict):
        await repo.get(pending.snapshot_id)
    with pytest.raises(EvidenceConflict):
        await repo.finish(pending, [record(snapshot_id=pending.snapshot_id)])
    fresh = await begin(repo)
    sealed = await repo.finish(fresh, [record(snapshot_id=fresh.snapshot_id)])
    db.get_collection("research_snapshots").rows[sealed.snapshot_id]["records"][0][
        "value"
    ] = 500
    with pytest.raises(EvidenceConflict):
        await repo.get(sealed.snapshot_id)


@pytest.mark.asyncio
async def test_child_conflict_retains_parent_bytes_and_scoped_claim_edges():
    db = Database()
    repo = EvidenceRepository(db)
    pending = await begin(repo)
    parent = await repo.finish(pending, [record(snapshot_id=pending.snapshot_id)])
    before = parent.model_dump(mode="json")
    child = await repo.begin(
        request_key="child",
        run_id="run",
        symbol="AAPL",
        as_of=NOW,
        parent_id=parent.snapshot_id,
    )
    sealed = await repo.finish(
        child, [record(snapshot_id=child.snapshot_id, value=101, provider="finnhub")]
    )
    assert len(sealed.records) == 2 and sealed.conflicts
    assert (await repo.get(parent.snapshot_id)).model_dump(mode="json") == before
    c = claim(parent.records[0])
    d = build_dossier(
        sealed,
        "<claims-json>"
        + json.dumps({"claims": [c.model_dump(mode="json")]})
        + "</claims-json>",
    )
    await repo.save_dossier(d)
    assert (await repo.get_dossier(d.dossier_id)).claims[0].reasons == [
        "CONFLICTING_EVIDENCE"
    ]


@pytest.mark.asyncio
async def test_frozen_tools_do_not_fetch_and_scope_does_not_leak_between_tasks():
    calls = []

    @tool
    async def get_stock_quote(symbol: str) -> str:
        """Recorded outer quote boundary."""
        calls.append(symbol)
        return "fresh"

    tools = [get_stock_quote]
    install_tools(tools)
    install_tools(tools)
    db = Database()
    repo = EvidenceRepository(db)
    pending = await begin(repo)
    sealed = await repo.finish(pending, [record(snapshot_id=pending.snapshot_id)])

    async def frozen():
        with evidence_scope({"AAPL": sealed}):
            result = await get_stock_quote.ainvoke({"symbol": "AAPL"})
            assert sealed.snapshot_id in result and "ev_" in result
            assert "outside" in await get_stock_quote.ainvoke({"symbol": "MSFT"})

    async def normal():
        assert await get_stock_quote.ainvoke({"symbol": "MSFT"}) == "fresh"

    await asyncio.gather(frozen(), normal())
    assert calls == ["MSFT"]
