"""Gate/service edge cases: forged records, permissions, stale claims, and the real HTTP API."""

from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.api.dependencies.storage import get_mongodb
from src.api.portfolio.model_decisions import router
from src.core.exceptions import AppError, NotFoundError
from src.models.decision_review import ProposeReview, ReviewTarget, RevisionRequest
from src.services.decision_policy import (
    control,
    model_decision,
    model_decision_gate,
    policies,
    review_gate,
)
from tests.review_fixtures import NOW
from tests.test_model_decisions import ENABLED, Agent, decisions, ready_case, request


async def completed(monkeypatch, output=None, **kwargs):
    db, source, snaps = await ready_case(monkeypatch, **kwargs)
    view = await model_decision.decide(
        db,
        Agent(output or decisions(snaps, AAPL=("ADD", 0.2), MSFT=("HOLD", None))),
        await request(db, source),
    )
    return db, source, snaps, view.record


async def gate(db, source, record, targets):
    policy = policies.active(await control.read(db))
    result = await review_gate.evaluate(
        db,
        ProposeReview(
            expected_revision=0,
            expected_generation=0,
            request_id="gate-request",
            assessment_id=source.assessment_id,
            targets=[
                ReviewTarget(symbol=s, target_weight=w) for s, w in targets.items()
            ],
        ),
        policy,
        record,
    )
    return {r.code for r in result.reasons}


@pytest.mark.asyncio
async def test_forged_or_inconsistent_records_are_blocked(monkeypatch):
    db, source, snaps, record = await completed(monkeypatch)
    assert "MODEL_DECISION_UNAVAILABLE" in await gate(
        db, source, record.model_copy(update={"output": None}), {"AAPL": 0.2}
    )
    assert "MODEL_DECISION_SOURCE_MISMATCH" in await gate(
        db, source, record.model_copy(update={"source_hash": "x"}), {"AAPL": 0.2}
    )
    assert "MODEL_DECISION_POLICY_CHANGED" in await gate(
        db,
        source,
        record.model_copy(update={"policy_version_id": "old"}),
        {"AAPL": 0.2},
    )
    doubled = record.output.model_copy(
        update={"decisions": [*record.output.decisions, record.output.decisions[0]]}
    )
    assert "MODEL_DECISION_DUPLICATE" in await gate(
        db, source, record.model_copy(update={"output": doubled}), {"AAPL": 0.2}
    )
    assert "MODEL_DECISION_TARGET_MISMATCH" in await gate(
        db, source, record, {"AAPL": 0.3}
    )
    assert "MODEL_DECISION_TARGET_MISMATCH" in await gate(
        db, source, record, {"MSFT": 0.1}
    )


@pytest.mark.asyncio
async def test_exit_permission_and_bearish_exit_rules(monkeypatch):
    from tests.review_fixtures import setup

    db, _, source, snaps = await setup(
        monkeypatch, model_policy=dict(ENABLED, model_may_exit=False)
    )
    output = decisions(snaps, AAPL=("SELL", 0.0), MSFT=("HOLD", None))
    view = await model_decision.decide(db, Agent(output), await request(db, source))
    assert "MODEL_EXIT_NOT_PERMITTED" in {r.code for r in view.review.reasons}
    db, _, source, snaps = await setup(monkeypatch, model_policy=ENABLED)
    view = await model_decision.decide(
        db,
        Agent(decisions(snaps, AAPL=("SELL", 0.0), MSFT=("HOLD", None))),
        await request(db, source),
    )
    # SELL against the recorded bullish stance needs review; code does not overrule either way.
    assert "MODEL_ACTION_STANCE_CONFLICT" in {r.code for r in view.review.reasons}


@pytest.mark.asyncio
async def test_missing_strategy_review_or_snapshot_is_unverified_evidence(monkeypatch):
    db, source, snaps, record = await completed(monkeypatch)
    no_review = source.model_copy(deep=True)
    no_review.strategy.reviews = []
    assert await model_decision_gate.allowed_evidence(db, no_review, "AAPL") == set()
    assert model_decision_gate.stance(no_review, "AAPL") == "unknown"
    db.get_collection("research_snapshots").rows["snapshot_AAPL"]["state"] = "failed"
    assert await model_decision_gate.allowed_evidence(db, source, "AAPL") == set()


@pytest.mark.asyncio
async def test_expired_running_claim_is_taken_over_once_and_agent_is_required(
    monkeypatch,
):
    db, source, snaps = await ready_case(monkeypatch)
    body = await request(db, source)
    policy, src, symbols = await model_decision.eligible(db, source.assessment_id)
    record, owned = await model_decision.claim(db, body, policy, src, symbols)
    assert owned
    row = db.get_collection(model_decision.COLLECTION).rows[record.decision_id]
    row["lease_until"] = (NOW - timedelta(days=1)).isoformat()
    taken, owned = await model_decision.claim(db, body, policy, src, symbols)
    assert owned and taken.owner != record.owner
    with pytest.raises(control.ReviewConflict, match="claim was lost"):
        await model_decision.finish(db, record, status="failed")
    with pytest.raises(control.ReviewConflict, match="unavailable"):
        await model_decision.decide(
            db, None, (await request(db, source, "model-no-agent"))
        )
    with pytest.raises(NotFoundError):
        await model_decision.get(db, "absent")
    with pytest.raises(NotFoundError):
        await model_decision.eligible(db, "assessment_" + "0" * 32)


@pytest.mark.asyncio
async def test_real_http_routes_list_detail_revalidate_and_origin(monkeypatch):
    db, source, snaps, record = await completed(monkeypatch)
    app = FastAPI()
    app.include_router(router, prefix="/api/portfolio")
    app.dependency_overrides[get_mongodb] = lambda: db
    app.state.portfolio_agent = Agent(
        decisions(snaps, AAPL=("ADD", 0.2), MSFT=("HOLD", None))
    )

    @app.exception_handler(AppError)
    async def handled(request, error):
        return JSONResponse(error.to_dict(), status_code=error.status_code)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://localhost"
    ) as client:
        root = "/api/portfolio/model-decisions"
        listed = await client.get(root)
        assert (
            listed.status_code == 200 and listed.headers["cache-control"] == "no-store"
        )
        assert listed.json()[0]["record"]["decision_id"] == record.decision_id
        assert (await client.get(f"{root}/{record.decision_id}")).json()["review"][
            "readiness"
        ] == "ready"
        body = (await request(db, source, "api-model-request")).model_dump(mode="json")
        assert (await client.post(root, json=body)).status_code == 403
        assert (
            await client.post(
                root,
                json={**body, "ready": True},
                headers={"X-Financial-Agent-Local": "1"},
            )
        ).status_code == 422
        made = await client.post(
            root, json=body, headers={"X-Financial-Agent-Local": "1"}
        )
        assert (
            made.status_code == 200 and made.json()["record"]["status"] == "completed"
        )
        state = await control.read(db)
        again = await client.post(
            f"{root}/{record.decision_id}/review",
            json=RevisionRequest(
                expected_revision=state.revision,
                expected_generation=state.generation,
                request_id="api-revalidate",
            ).model_dump(),
            headers={"X-Financial-Agent-Local": "1"},
        )
        assert (
            again.status_code == 200
            and again.json()["review"]["batch"]["model_decision"]["decision_id"]
            == record.decision_id
        )
        assert (await client.get(f"{root}/absent")).status_code == 404


@pytest.mark.asyncio
async def test_cancelled_call_is_recorded_failed_not_left_running(monkeypatch):
    import asyncio

    db, source, snaps = await ready_case(monkeypatch)
    started = asyncio.Event()

    async def hang():
        started.set()
        await asyncio.Event().wait()

    body = await request(db, source)
    task = asyncio.create_task(model_decision.decide(db, Agent(during=hang), body))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    row = next(iter(db.get_collection(model_decision.COLLECTION).rows.values()))
    assert row["status"] == "failed" and row["error_code"] == "CancelledError"
    with pytest.raises(control.ReviewConflict, match="failed"):
        await model_decision.decide(db, Agent(), body)
