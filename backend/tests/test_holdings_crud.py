"""End-to-end-ish tests for holdings CRUD endpoints.

Uses TestClient + dependency_overrides to inject AsyncMock repo.
Covers: POST new, POST merge, PATCH update, DELETE happy + 404,
validation errors, quote enrichment success + failure paths.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies.portfolio_deps import get_holding_repository
from src.main import app
from src.models.holding import Holding


def _holding(symbol: str = "AAPL", qty: int = 10, avg: float = 150.0) -> Holding:
    cost = qty * avg
    return Holding(
        holding_id=f"holding_{symbol.lower()}",
        symbol=symbol,
        quantity=qty,
        avg_price=avg,
        current_price=None,
        cost_basis=cost,
        market_value=None,
        unrealized_pl=None,
        unrealized_pl_pct=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_price_update=None,
    )


@pytest.fixture
def repo() -> MagicMock:
    r = MagicMock()
    r.get_by_symbol = AsyncMock(return_value=None)
    r.create = AsyncMock()
    r.update = AsyncMock()
    r.delete = AsyncMock(return_value=True)
    return r


@pytest.fixture
def client(repo: MagicMock):
    # Stub out app.state.data_manager so quote enrichment is a no-op.
    app.state.data_manager = None
    app.dependency_overrides[get_holding_repository] = lambda: repo
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------- POST ----------


class TestPostHoldings:
    def test_create_new(self, client: TestClient, repo: MagicMock):
        repo.create = AsyncMock(return_value=_holding("AAPL", 10, 150.0))
        r = client.post(
            "/api/portfolio/holdings",
            json={"symbol": "AAPL", "quantity": 10, "avg_price": 150.0},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["symbol"] == "AAPL"
        assert body["quantity"] == 10
        assert body["avg_price"] == 150.0
        assert body["cost_basis"] == 1500.0
        repo.get_by_symbol.assert_awaited_once_with(symbol="AAPL")
        repo.create.assert_awaited_once()
        repo.update.assert_not_awaited()

    def test_create_uppercases_symbol(self, client: TestClient, repo: MagicMock):
        repo.create = AsyncMock(return_value=_holding("AAPL", 5, 100.0))
        r = client.post(
            "/api/portfolio/holdings",
            json={"symbol": "aapl", "quantity": 5, "avg_price": 100.0},
        )
        assert r.status_code == 200
        # The HoldingCreate passed to repo.create should already be uppercase
        passed = repo.create.call_args.kwargs["holding_create"]
        assert passed.symbol == "AAPL"

    def test_merge_duplicate(self, client: TestClient, repo: MagicMock):
        # Existing AAPL: 10 shares @ $150
        existing = _holding("AAPL", 10, 150.0)
        repo.get_by_symbol = AsyncMock(return_value=existing)
        # After merge: 10+5=15 shares; new avg = (10*150 + 5*170)/15 = 156.67
        merged_obj = _holding("AAPL", 15, 156.6667)
        repo.update = AsyncMock(return_value=merged_obj)

        r = client.post(
            "/api/portfolio/holdings",
            json={"symbol": "AAPL", "quantity": 5, "avg_price": 170.0},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["quantity"] == 15
        assert body["avg_price"] == pytest.approx(156.6667, abs=0.01)
        repo.update.assert_awaited_once()
        # Verify the formula was applied correctly
        call_kwargs = repo.update.call_args
        update_payload = call_kwargs.args[1]
        assert update_payload.quantity == 15
        assert update_payload.avg_price == pytest.approx(156.6667, abs=0.0001)
        repo.create.assert_not_awaited()

    def test_missing_avg_price_returns_422(self, client: TestClient):
        # Pydantic field-level validation catches this at request parsing time
        r = client.post(
            "/api/portfolio/holdings",
            json={"symbol": "AAPL", "quantity": 10},
        )
        # avg_price missing → handler raises 422 explicitly
        assert r.status_code == 422

    def test_zero_quantity_returns_422(self, client: TestClient):
        r = client.post(
            "/api/portfolio/holdings",
            json={"symbol": "AAPL", "quantity": 0, "avg_price": 100.0},
        )
        assert r.status_code == 422

    def test_negative_avg_price_returns_422(self, client: TestClient):
        r = client.post(
            "/api/portfolio/holdings",
            json={"symbol": "AAPL", "quantity": 5, "avg_price": -10.0},
        )
        assert r.status_code == 422


# ---------- PATCH ----------


class TestPatchHolding:
    def test_happy_path(self, client: TestClient, repo: MagicMock):
        repo.update = AsyncMock(return_value=_holding("AAPL", 12, 150.0))
        r = client.patch(
            "/api/portfolio/holdings/holding_aapl",
            json={"quantity": 12},
        )
        assert r.status_code == 200
        assert r.json()["quantity"] == 12
        repo.update.assert_awaited_once()

    def test_not_found(self, client: TestClient, repo: MagicMock):
        repo.update = AsyncMock(return_value=None)
        r = client.patch("/api/portfolio/holdings/missing", json={"quantity": 5})
        assert r.status_code == 404

    def test_empty_body_returns_422(self, client: TestClient):
        r = client.patch("/api/portfolio/holdings/holding_aapl", json={})
        assert r.status_code == 422


# ---------- DELETE ----------


class TestDeleteHolding:
    def test_happy_path(self, client: TestClient, repo: MagicMock):
        repo.delete = AsyncMock(return_value=True)
        r = client.delete("/api/portfolio/holdings/holding_aapl")
        assert r.status_code == 204
        repo.delete.assert_awaited_once_with("holding_aapl")

    def test_not_found(self, client: TestClient, repo: MagicMock):
        repo.delete = AsyncMock(return_value=False)
        r = client.delete("/api/portfolio/holdings/missing")
        assert r.status_code == 404


# ---------- Quote enrichment ----------


class TestQuoteEnrichment:
    def test_enriches_when_data_manager_returns_quote(
        self, client: TestClient, repo: MagicMock
    ):
        from types import SimpleNamespace

        repo.create = AsyncMock(return_value=_holding("AAPL", 10, 150.0))
        # Plug a fake DataManager into app.state
        dm = MagicMock()
        dm.get_quote = AsyncMock(return_value=SimpleNamespace(price=180.0))
        app.state.data_manager = dm

        r = client.post(
            "/api/portfolio/holdings",
            json={"symbol": "AAPL", "quantity": 10, "avg_price": 150.0},
        )
        body = r.json()
        assert r.status_code == 200
        assert body["current_price"] == 180.0
        assert body["market_value"] == 1800.0
        assert body["unrealized_pl"] == 300.0
        assert body["unrealized_pl_pct"] == pytest.approx(20.0)

    def test_quote_failure_does_not_break_post(
        self, client: TestClient, repo: MagicMock
    ):
        repo.create = AsyncMock(return_value=_holding("AAPL", 10, 150.0))
        dm = MagicMock()
        dm.get_quote = AsyncMock(side_effect=Exception("vendor down"))
        app.state.data_manager = dm

        r = client.post(
            "/api/portfolio/holdings",
            json={"symbol": "AAPL", "quantity": 10, "avg_price": 150.0},
        )
        assert r.status_code == 200
        body = r.json()
        # Insert succeeded; enrichment fields are null
        assert body["current_price"] is None
        assert body["market_value"] is None
