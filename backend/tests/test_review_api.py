"""Actual HTTP schemas/local-action controls route to real review gates and immutable storage."""

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.api.dependencies.storage import get_mongodb
from src.api.portfolio.reviews import router
from src.core.exceptions import AppError
from src.models.decision_review import RevisionRequest
from src.services.decision_policy import control
from tests.review_fixtures import setup
from tests.test_review_gates import approval

HEADERS = {"X-Financial-Agent-Local": "1"}


@pytest.mark.asyncio
async def test_real_http_review_lifecycle_schema_and_origin_boundary(monkeypatch):
    db, body, _, _ = await setup(monkeypatch)
    app = FastAPI()
    app.include_router(router, prefix="/api/portfolio")
    app.dependency_overrides[get_mongodb] = lambda: db

    @app.exception_handler(AppError)
    async def handled(request, error):
        return JSONResponse(error.to_dict(), status_code=error.status_code)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://localhost"
    ) as client:
        root = "/api/portfolio"
        state = await client.get(root + "/review-policy")
        assert state.status_code == 200 and state.headers["cache-control"] == "no-store"
        denied = await client.post(
            root + "/review-batches", json=body.model_dump(mode="json")
        )
        assert denied.status_code == 403
        hostile = await client.post(
            root + "/review-batches",
            headers={**HEADERS, "Origin": "https://attacker.example"},
            json=body.model_dump(mode="json"),
        )
        assert hostile.status_code == 403
        assert not (await control.read(db)).published
        forged = await client.post(
            root + "/review-batches",
            headers=HEADERS,
            json={**body.model_dump(mode="json"), "ready": True},
        )
        assert forged.status_code == 422
        created = await client.post(
            root + "/review-batches", headers=HEADERS, json=body.model_dump(mode="json")
        )
        assert created.status_code == 200, created.text
        assert created.headers["cache-control"] == "no-store"
        assert created.json()["readiness"] == "ready"
        identifier = created.json()["batch"]["batch_id"]
        from src.models.decision_review import ReviewView

        view = ReviewView.model_validate(created.json())
        approved = await client.post(
            root + f"/review-batches/{identifier}/approve",
            headers=HEADERS,
            json=approval(view).model_dump(mode="json"),
        )
        assert approved.status_code == 200 and approved.json()["approval_current"]
        detail = await client.get(root + f"/review-batches/{identifier}")
        assert (
            detail.json()["lifecycle"] == "approved"
            and detail.json()["executable"] is False
        )
        assert len((await client.get(root + "/review-batches")).json()) == 1
        cancel = RevisionRequest(
            expected_revision=detail.json()["control_revision"],
            expected_generation=detail.json()["control_generation"],
            request_id="api-cancel",
        )
        result = await client.post(
            root + f"/review-batches/{identifier}/cancel",
            headers=HEADERS,
            json=cancel.model_dump(mode="json"),
        )
        assert result.status_code == 200 and not result.json()["approval_current"]
        assert (await client.get(root + "/review-batches/absent")).status_code == 404
