from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.evaluations import get_evaluation_repository, router
from src.core.config import get_settings
from src.evals.live_schemas import (
    EvaluationRunSummary,
    LiveEvaluationMetrics,
    LiveEvaluationReport,
)


def _app(repository: AsyncMock, environment: str = "test") -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_evaluation_repository] = lambda: repository
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        environment=environment
    )
    return app


def _report(run_id: str) -> LiveEvaluationReport:
    now = datetime.now(UTC)
    return LiveEvaluationReport(
        run_id=run_id,
        lane="fake_live",
        status="completed",
        created_at=now,
        completed_at=now,
        max_cost_usd=1,
        metrics=LiveEvaluationMetrics(
            case_pass_rate=1,
            estimated_cost_usd=0.001,
        ),
        gates_passed=True,
    )


def test_live_api_requires_explicit_consent():
    repository = AsyncMock()
    response = TestClient(_app(repository)).post(
        "/api/admin/evaluations/live/runs",
        json={
            "lane": "fake_live",
            "enabled": False,
            "max_cost_usd": 1,
            "case_limit": 1,
        },
    )

    assert response.status_code == 422
    repository.save.assert_not_awaited()


def test_fake_live_api_is_test_only():
    repository = AsyncMock()
    response = TestClient(_app(repository, environment="development")).post(
        "/api/admin/evaluations/live/runs",
        json={
            "lane": "fake_live",
            "enabled": True,
            "max_cost_usd": 1,
            "case_limit": 1,
        },
    )

    assert response.status_code == 403


def test_live_api_persists_running_and_terminal_reports():
    repository = AsyncMock()

    async def fake_run(
        payload,
        *,
        gateway=None,
        run_id=None,
        created_at=None,
        progress_callback=None,
    ):
        report = _report(run_id)
        return report.model_copy(update={"created_at": created_at})

    with patch(
        "src.api.evaluations.run_live_evaluation",
        side_effect=fake_run,
    ):
        response = TestClient(_app(repository)).post(
            "/api/admin/evaluations/live/runs",
            json={
                "lane": "fake_live",
                "enabled": True,
                "max_cost_usd": 1,
                "case_limit": 1,
            },
        )

    assert response.status_code == 202
    assert response.json()["status"] == "running"
    assert repository.save.await_count == 2
    saved = repository.save.await_args_list
    assert saved[0].args[0].status == "running"
    assert saved[1].args[0].status == "completed"
    assert saved[1].args[0].created_at == saved[0].args[0].created_at


def test_live_api_lists_and_fetches_history():
    repository = AsyncMock()
    report = _report("eval_live_test")
    repository.list.return_value = [
        EvaluationRunSummary(
            run_id=report.run_id,
            suite_version=report.suite_version,
            lane=report.lane,
            status=report.status,
            created_at=report.created_at,
            completed_at=report.completed_at,
            gates_passed=True,
            case_pass_rate=1,
            estimated_cost_usd=0.001,
        )
    ]
    repository.get.return_value = report
    client = TestClient(_app(repository))

    listed = client.get("/api/admin/evaluations/live/runs")
    fetched = client.get(f"/api/admin/evaluations/live/runs/{report.run_id}")

    assert listed.status_code == 200
    assert listed.json()[0]["run_id"] == report.run_id
    assert fetched.status_code == 200
    assert fetched.json()["gates_passed"] is True


def test_live_capabilities_match_backend_environment():
    repository = AsyncMock()
    response = TestClient(_app(repository, environment="test")).get(
        "/api/admin/evaluations/live/capabilities"
    )

    assert response.status_code == 200
    assert response.json() == {
        "fake_live_available": True,
        "provider_smoke_available": False,
    }
