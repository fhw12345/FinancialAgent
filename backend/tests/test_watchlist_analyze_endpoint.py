"""Integration tests for single-symbol watchlist analysis persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies.storage import get_mongodb
from src.api.dependencies.watchlist_deps import get_watchlist_repository
from src.api.watchlist import router
from src.database.repositories.watchlist_repository import (
    WATCHLIST_COLLECTION,
    WatchlistRepository,
)


def _mock_repository(
    *,
    analyzed_at: datetime | None = None,
) -> MagicMock:
    repository = MagicMock(spec=WatchlistRepository)
    repository.mark_analyzed_by_symbol = AsyncMock(return_value=analyzed_at)
    return repository


def _make_app(
    *,
    repository: MagicMock | None = None,
    mongodb: MagicMock | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.watchlist_analyzer = MagicMock()

    if repository is None and mongodb is None:
        repository = _mock_repository()
    if repository is not None:
        app.dependency_overrides[get_watchlist_repository] = lambda: repository
    if mongodb is not None:
        app.dependency_overrides[get_mongodb] = lambda: mongodb
    return app


@pytest.fixture
def patched_run_single_symbol():
    with patch(
        "src.agent.portfolio.flows.run_single_symbol",
        new_callable=AsyncMock,
    ) as mocked_flow:
        yield mocked_flow


def test_single_symbol_route_calls_run_single_symbol(patched_run_single_symbol):
    """Endpoint invokes the unified flow and preserves ad-hoc analysis."""
    patched_run_single_symbol.return_value = {
        "result_count": 1,
        "run_id": "single_abcd1234",
        "symbol": "AAPL",
        "message": "ok",
    }
    repository = _mock_repository()
    app = _make_app(repository=repository)

    response = TestClient(app).post("/api/watchlist/analyze?symbol=AAPL")

    assert response.status_code == 202, response.text
    assert response.json() == {
        "status": "analysis_completed",
        "symbol": "AAPL",
        "result_count": 1,
        "run_id": "single_abcd1234",
        "watchlist_updated": False,
        "last_analyzed_at": None,
    }
    patched_run_single_symbol.assert_awaited_once()
    args, _ = patched_run_single_symbol.call_args
    assert args[1] == "AAPL"
    repository.mark_analyzed_by_symbol.assert_awaited_once_with("AAPL")


def test_single_symbol_returns_persisted_watchlist_timestamp(
    patched_run_single_symbol,
):
    """A watched symbol returns the exact timestamp written to MongoDB."""
    patched_run_single_symbol.return_value = {
        "result_count": 1,
        "run_id": "single_xyz",
        "symbol": "MSFT",
    }
    analyzed_at = datetime(2026, 7, 17, 5, 30, tzinfo=UTC)
    repository = _mock_repository(analyzed_at=analyzed_at)
    app = _make_app(repository=repository)

    response = TestClient(app).post("/api/watchlist/analyze?symbol=msft")

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "analysis_completed"
    assert body["watchlist_updated"] is True
    returned_at = datetime.fromisoformat(
        body["last_analyzed_at"].replace("Z", "+00:00")
    )
    assert returned_at == analyzed_at
    repository.mark_analyzed_by_symbol.assert_awaited_once_with("MSFT")


def test_analyze_endpoint_uses_canonical_watchlist_collection(
    patched_run_single_symbol,
):
    """The real dependency must select the collection used by CRUD."""
    patched_run_single_symbol.return_value = {
        "result_count": 1,
        "run_id": "single_collection",
        "symbol": "AAPL",
    }
    collection = MagicMock()
    collection.update_one = AsyncMock(
        return_value=SimpleNamespace(matched_count=1, modified_count=1)
    )
    mongodb = MagicMock()
    mongodb.get_collection.return_value = collection
    app = _make_app(mongodb=mongodb)

    response = TestClient(app).post("/api/watchlist/analyze?symbol=AAPL")

    assert response.status_code == 202, response.text
    assert response.json()["watchlist_updated"] is True
    mongodb.get_collection.assert_called_once_with(WATCHLIST_COLLECTION)
    collection.update_one.assert_awaited_once()
    query = collection.update_one.await_args.args[0]
    assert query == {"symbol": "AAPL"}


def test_watchlist_persistence_failure_is_not_reported_as_completed(
    patched_run_single_symbol,
):
    """A timestamp write failure must surface as an endpoint failure."""
    patched_run_single_symbol.return_value = {
        "result_count": 1,
        "run_id": "single_failed_stamp",
        "symbol": "AAPL",
    }
    repository = _mock_repository()
    repository.mark_analyzed_by_symbol.side_effect = RuntimeError(
        "watchlist write failed"
    )
    app = _make_app(repository=repository)

    response = TestClient(app).post("/api/watchlist/analyze?symbol=AAPL")

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Unable to trigger watchlist analysis. Please try again later."
    )


def test_single_symbol_failure_returns_failed_status(patched_run_single_symbol):
    """Flow failures remain explicit and do not stamp the watchlist."""
    patched_run_single_symbol.side_effect = RuntimeError("LLM offline")
    repository = _mock_repository()
    app = _make_app(repository=repository)

    response = TestClient(app).post("/api/watchlist/analyze?symbol=NVDA")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "analysis_failed"
    assert body["symbol"] == "NVDA"
    assert "RuntimeError" in body["message"]
    repository.mark_analyzed_by_symbol.assert_not_awaited()


def test_single_symbol_zero_persisted_returns_failed(patched_run_single_symbol):
    """No persisted decision means the timestamp must remain unchanged."""
    patched_run_single_symbol.return_value = {
        "result_count": 0,
        "run_id": None,
        "symbol": "TSLA",
        "message": "Phase 1 produced no research for TSLA.",
    }
    repository = _mock_repository()
    app = _make_app(repository=repository)

    response = TestClient(app).post("/api/watchlist/analyze?symbol=TSLA")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "analysis_failed"
    assert body["watchlist_updated"] is False
    assert body["last_analyzed_at"] is None
    repository.mark_analyzed_by_symbol.assert_not_awaited()


def test_invalid_symbol_returns_400():
    app = _make_app()

    response = TestClient(app).post("/api/watchlist/analyze?symbol=A!B")

    assert response.status_code == 400


def test_no_symbol_uses_legacy_batch_path():
    """The all-watchlist path remains on the legacy batch analyzer."""
    repository = _mock_repository()
    app = _make_app(repository=repository)
    analyzer = MagicMock()
    analyzer.run_analysis_cycle = AsyncMock()
    app.state.watchlist_analyzer = analyzer

    response = TestClient(app).post("/api/watchlist/analyze")

    assert response.status_code == 202
    assert response.json()["status"] == "analysis_started"
    analyzer.run_analysis_cycle.assert_awaited_once_with(force=True)
    repository.mark_analyzed_by_symbol.assert_not_awaited()
