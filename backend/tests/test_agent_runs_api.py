"""API and Portfolio compatibility tests for shared durable runs."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies.run_deps import get_agent_run_repository
from src.api.dependencies.storage import get_mongodb
from src.api.portfolio_admin import (
    _get_legacy_run,
    _run_holdings_flow,
    _to_analysis_run,
)
from src.api.portfolio_admin import (
    router as portfolio_router,
)
from src.api.runs import router
from src.core.utils.date_utils import utcnow
from src.models.agent_run import AgentRun
from src.models.portfolio_analysis import PortfolioSettings


def agent_run(**updates) -> AgentRun:
    payload = {
        "run_id": "run_shared",
        "requested_policy": "auto",
        "policy_version": "auto-router-v1",
        "status": "completed",
        "started_at": utcnow(),
    }
    payload.update(updates)
    return AgentRun(**payload)


def test_run_lookup_and_chat_list_api():
    repository = MagicMock()
    repository.get = AsyncMock(
        return_value=agent_run(chat_id="chat_1", execution_mode="instant")
    )
    repository.list_by_chat = AsyncMock(return_value=[agent_run(chat_id="chat_1")])
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_agent_run_repository] = lambda: repository
    client = TestClient(app)

    detail = client.get("/api/runs/run_shared")
    listed = client.get("/api/runs?chat_id=chat_1&limit=10")

    assert detail.status_code == 200
    assert detail.json()["execution_mode"] == "instant"
    assert listed.status_code == 200
    assert listed.json()[0]["run_id"] == "run_shared"
    repository.list_by_chat.assert_awaited_once_with("chat_1", limit=10)


def test_portfolio_compatibility_maps_shared_run_fields():
    run = agent_run(
        portfolio_key="picks",
        metadata={
            "message": "Selected 5 candidates",
            "result_count": 5,
            "sectors": ["Technology"],
        },
    )

    compatibility = _to_analysis_run(run)

    assert compatibility.run_id == "picks"
    assert compatibility.agent_run_id == "run_shared"
    assert compatibility.status == "done"
    assert compatibility.message == "Selected 5 candidates"
    assert compatibility.result_count == 5
    assert compatibility.sectors == ["Technology"]


def test_portfolio_status_releases_expired_lease_before_returning_run():
    repository = MagicMock()
    repository.release_stale_portfolio_claim = AsyncMock(return_value=1)
    repository.get_latest_by_portfolio_key = AsyncMock(
        return_value=agent_run(
            portfolio_key="holdings",
            status="failed",
            error_code="STALE_RUN_LEASE",
            error_message="Run lease expired before completion",
        )
    )
    app = FastAPI()
    app.include_router(portfolio_router)
    app.dependency_overrides[get_agent_run_repository] = lambda: repository
    app.dependency_overrides[get_mongodb] = lambda: MagicMock()
    client = TestClient(app)

    response = client.get("/api/admin/portfolio/status/holdings")

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert response.json()["message"] == "Run lease expired before completion"
    repository.release_stale_portfolio_claim.assert_awaited_once()
    repository.get_latest_by_portfolio_key.assert_awaited_once_with("holdings")


@pytest.mark.asyncio
async def test_legacy_running_run_expires_instead_of_blocking_cutover():
    mongodb = MagicMock()
    collection = MagicMock()
    collection.update_one = AsyncMock()
    collection.find_one = AsyncMock(
        return_value={
            "run_id": "holdings",
            "status": "error",
            "started_at": utcnow(),
            "finished_at": utcnow(),
            "message": "Legacy run lease expired before completion",
        }
    )
    mongodb.get_collection.return_value = collection

    run = await _get_legacy_run(mongodb, "holdings")

    assert run is not None
    assert run.status == "error"
    assert run.message == "Legacy run lease expired before completion"
    query = collection.update_one.await_args.args[0]
    assert query["status"] == "running"
    assert "$lte" in query["started_at"]


@pytest.mark.asyncio
async def test_portfolio_background_flow_uses_shared_transitions():
    run_service = AsyncMock()
    settings = PortfolioSettings(
        cash_balance=100_000,
        risk_tolerance="moderate",
        max_position_pct=10,
    )
    with patch(
        "src.agent.portfolio.flows.run_analyze_holdings",
        new=AsyncMock(
            return_value={
                "message": "Analyzed holdings",
                "result_count": 3,
            }
        ),
    ):
        await _run_holdings_flow(
            run_service,
            "run_portfolio",
            MagicMock(),
            settings,
        )

    assert run_service.transition_portfolio.await_args_list[0].kwargs == {
        "status": "running"
    }
    assert run_service.transition_portfolio.await_args_list[1].kwargs == {
        "status": "completed",
        "metadata": {
            "message": "Analyzed holdings",
            "result_count": 3,
        },
    }
