"""W2.2 reroute integration test: POST /api/watchlist/analyze?symbol=X
calls run_single_symbol (the W2.1 unified flow) instead of the legacy
WatchlistAnalyzer.analyze_symbol path, and stamps watchlist.last_analyzed_at
when the symbol is in the watchlist.

The legacy path was bug-prone (free-text DECISION:/POSITION_SIZE: parse
that crashed on format drift) and didn't write to portfolio_orders, so
the dashboard never saw watchlist results. After W2.2 the per-row
"Analyze Now" button persists a structured PortfolioOrder via
run_single_symbol; the dashboard's DecisionTracker picks it up.

This test stubs run_single_symbol + the watchlist repo so we can
assert the wiring without booting LangGraph / mongo / yfinance.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies.auth import require_admin
from src.api.watchlist import router
from src.models.watchlist import WatchlistItem


def _make_app(*, mongo: MagicMock | None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: None
    app.state.mongodb = mongo
    return app


@pytest.fixture
def patched_run_single_symbol():
    with patch("src.agent.portfolio.flows.run_single_symbol", new_callable=AsyncMock) as m:
        yield m


def test_single_symbol_route_calls_run_single_symbol(patched_run_single_symbol):
    """Endpoint must invoke W2.1 flow, NOT the legacy WatchlistAnalyzer."""
    patched_run_single_symbol.return_value = {
        "result_count": 1,
        "run_id": "single_abcd1234",
        "symbol": "AAPL",
        "message": "ok",
    }

    mongo = MagicMock()
    mongo.get_collection = MagicMock(return_value=MagicMock())
    app = _make_app(mongo=mongo)

    # Stub watchlist repo: AAPL not in watchlist → update path is skipped.
    with patch("src.api.watchlist.WatchlistRepository") as repo_cls:
        repo = MagicMock()
        repo.get_by_user = AsyncMock(return_value=[])
        repo.update_last_analyzed = AsyncMock(return_value=False)
        repo_cls.return_value = repo

        client = TestClient(app)
        r = client.post("/api/watchlist/analyze?symbol=AAPL")

    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "analysis_completed"
    assert body["symbol"] == "AAPL"
    assert body["result_count"] == 1
    assert body["run_id"] == "single_abcd1234"

    # Critical: W2.1 flow was called once with the upper-cased symbol.
    patched_run_single_symbol.assert_awaited_once()
    args, _ = patched_run_single_symbol.call_args
    assert args[1] == "AAPL"


def test_single_symbol_stamps_last_analyzed_when_in_watchlist(
    patched_run_single_symbol,
):
    """If the symbol IS in the watchlist, the row's last_analyzed_at
    must be updated so the WatchlistPanel shows the fresh timestamp."""
    patched_run_single_symbol.return_value = {
        "result_count": 1,
        "run_id": "single_xyz",
        "symbol": "MSFT",
    }

    mongo = MagicMock()
    mongo.get_collection = MagicMock(return_value=MagicMock())
    app = _make_app(mongo=mongo)

    msft_item = WatchlistItem(
        watchlist_id="wl_msft",
        user_id="local",
        symbol="MSFT",
        notes=None,
    )

    with patch("src.api.watchlist.WatchlistRepository") as repo_cls:
        repo = MagicMock()
        repo.get_by_user = AsyncMock(return_value=[msft_item])
        repo.update_last_analyzed = AsyncMock(return_value=True)
        repo_cls.return_value = repo

        client = TestClient(app)
        r = client.post("/api/watchlist/analyze?symbol=msft")  # lowercase ok

    assert r.status_code == 202, r.text
    assert r.json()["status"] == "analysis_completed"
    repo.update_last_analyzed.assert_awaited_once_with("wl_msft")


def test_single_symbol_failure_returns_failed_status(patched_run_single_symbol):
    """If run_single_symbol raises, endpoint returns analysis_failed
    instead of crashing the request — so the UI can show a toast."""
    patched_run_single_symbol.side_effect = RuntimeError("LLM offline")

    mongo = MagicMock()
    mongo.get_collection = MagicMock(return_value=MagicMock())
    app = _make_app(mongo=mongo)

    client = TestClient(app)
    r = client.post("/api/watchlist/analyze?symbol=NVDA")

    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "analysis_failed"
    assert body["symbol"] == "NVDA"
    assert "RuntimeError" in body["message"]


def test_single_symbol_zero_persisted_returns_failed(patched_run_single_symbol):
    """run_single_symbol returns result_count=0 when Phase1 produces
    no research. Endpoint must surface analysis_failed so the UI
    doesn't lie about success."""
    patched_run_single_symbol.return_value = {
        "result_count": 0,
        "run_id": None,
        "symbol": "TSLA",
        "message": "Phase 1 produced no research for TSLA.",
    }

    mongo = MagicMock()
    mongo.get_collection = MagicMock(return_value=MagicMock())
    app = _make_app(mongo=mongo)

    with patch("src.api.watchlist.WatchlistRepository") as repo_cls:
        repo = MagicMock()
        repo.get_by_user = AsyncMock(return_value=[])
        repo.update_last_analyzed = AsyncMock()
        repo_cls.return_value = repo

        client = TestClient(app)
        r = client.post("/api/watchlist/analyze?symbol=TSLA")

    assert r.status_code == 202
    assert r.json()["status"] == "analysis_failed"


def test_invalid_symbol_returns_400():
    app = _make_app(mongo=MagicMock())
    client = TestClient(app)
    r = client.post("/api/watchlist/analyze?symbol=A!B")
    assert r.status_code == 400


def test_no_symbol_uses_legacy_batch_path():
    """All-watchlist path (no `symbol` param) keeps using the legacy
    WatchlistAnalyzer because the 5-min cron + bulk sweep haven't been
    ported. UI never hits this branch."""
    app = _make_app(mongo=MagicMock())
    analyzer = MagicMock()
    analyzer.run_analysis_cycle = AsyncMock()
    app.state.watchlist_analyzer = analyzer

    client = TestClient(app)
    r = client.post("/api/watchlist/analyze")

    assert r.status_code == 202
    assert r.json()["status"] == "analysis_started"
    analyzer.run_analysis_cycle.assert_awaited_once_with(force=True)
