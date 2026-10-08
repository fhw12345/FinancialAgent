"""Real HTTP origin/schema/manual provenance and Decimal BSON-safe replay contracts."""

import json
from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from bson import BSON
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError

from src.api.dependencies.storage import get_mongodb
from src.api.portfolio.paper import router
from src.core.exceptions import AppError, NotFoundError
from src.services.paper_ledger import service, store
from tests.paper_fixtures import action, creation, journal, refresh, setup

HEADERS = {"X-Financial-Agent-Local": "1"}


@pytest.mark.asyncio
async def test_http_origin_schema_readonly_manifest_and_full_manual_flow(monkeypatch):
    db = setup(monkeypatch)
    app = FastAPI()
    app.include_router(router, prefix="/api/portfolio")
    app.dependency_overrides[get_mongodb] = lambda: db

    @app.exception_handler(AppError)
    async def handled(request, error):
        return JSONResponse(error.to_dict(), status_code=error.status_code)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://localhost"
    ) as client:
        root = "/api/portfolio/paper/experiments"
        payload = creation().model_dump(mode="json")
        assert (await client.post(root, json=payload)).status_code == 403
        assert (
            await client.post(
                root,
                json=payload,
                headers={**HEADERS, "Origin": "https://attacker.example"},
            )
        ).status_code == 403
        assert (
            await client.post(root, json={**payload, "holdings": []}, headers=HEADERS)
        ).status_code == 422
        made = await client.post(root, json=payload, headers=HEADERS)
        assert made.status_code == 200 and made.headers["cache-control"] == "no-store"
        identifier = made.json()["experiment"]["experiment_id"]
        endpoint = root + "/" + identifier
        assert (await client.get(root)).json()[0]["sequence"] == 1
        bought = await client.post(
            endpoint + "/journal",
            json=journal(1).model_dump(mode="json"),
            headers=HEADERS,
        )
        assert (
            bought.status_code == 200
            and bought.json()["projection"]["cash"] == "8999.00"
        )
        marked = await client.post(
            endpoint + "/valuation",
            json=refresh(2).model_dump(mode="json"),
            headers=HEADERS,
        )
        assert (
            marked.status_code == 200 and marked.json()["valuation"]["nav"] == "9999.00"
        )
        exported = await client.get(endpoint + "/manifest")
        assert (
            exported.status_code == 200
            and exported.headers["cache-control"] == "no-store"
        )
        assert len(exported.json()["events"]) == 3
        BSON.encode(
            exported.json()
        )  # Dates/decimals are JSON strings, safe in standalone Mongo.
        restored = store.parse(json.loads(exported.text))
        assert (
            service.view(restored).projection.cash
            == service.view(await store.get(db, identifier)).projection.cash
        )
        assert (await client.get(endpoint)).json()["ai_validated"] is False
        closed = await client.post(
            endpoint + "/journal",
            json=action(3, "api-close", {"kind": "close"}).model_dump(mode="json"),
            headers=HEADERS,
        )
        assert closed.json()["projection"]["closed"]
        assert (await client.get(root + "/absent")).status_code == 404


@pytest.mark.asyncio
async def test_integrity_failure_creation_storage_errors_and_event_budget(monkeypatch):
    db = setup(monkeypatch)
    original = await service.create(db, creation())
    identifier = original.experiment.experiment_id
    collection = db.get_collection(store.COLLECTION)
    write = collection.find_one_and_update
    collection.find_one_and_update = AsyncMock(side_effect=DuplicateKeyError("race"))
    assert (await service.create(db, creation())).experiment == original.experiment
    collection.find_one_and_update = AsyncMock(return_value=None)
    with pytest.raises(RuntimeError, match="no durable"):
        await service.create(db, creation())
    collection.find_one_and_update = write
    with pytest.raises(NotFoundError):
        await store.get(db, "absent")
    # Guard counts without a synthetic successful ledger: production budget checks
    # run before any append, and the original aggregate remains unchanged.
    exhausted = original.experiment.model_copy(
        update={"events": original.experiment.events * 500}
    )
    addition = store.event(
        identifier,
        2,
        "limit-test",
        "hash",
        journal(1).entry,
        original.experiment.events[-1].event_hash,
    )
    with pytest.raises(store.PaperConflict, match="budget"):
        await store.append(db, exhausted, addition)
    for defect, expected in [
        ("sequence", "SEQUENCE"),
        ("time", "TIME"),
        ("valuation_sequence", "VALUATION_SEQUENCE"),
    ]:
        current = original.experiment.model_copy(deep=True)
        if defect == "sequence":
            current.sequence = 2
        elif defect == "time":
            current.events[0].recorded_at = current.events[0].recorded_at.replace(
                tzinfo=None
            )
            current.events[0].event_hash = store.hash_event(current.events[0])
        else:
            from src.models.paper_ledger import ValuationInput

            event = store.event(
                identifier,
                2,
                "bad-valued",
                "hash",
                ValuationInput(
                    session_date="2026-09-17",
                    ledger_sequence=99,
                    fetched_at=current.events[0].recorded_at,
                    reconciliation="corporate-actions-inspected-through-this-session",
                    marks=[],
                ),
                current.events[-1].event_hash,
            )
            current.sequence = 2
            current.events.append(event)
        with pytest.raises(store.PaperConflict, match=expected):
            store.validate(current)
    row = collection.rows[identifier]
    row["events"][0]["recorded_at"] = (
        original.experiment.events[0].recorded_at + timedelta(days=1)
    ).isoformat()
    with pytest.raises(store.PaperConflict, match="INTEGRITY"):
        await store.get(db, identifier)
