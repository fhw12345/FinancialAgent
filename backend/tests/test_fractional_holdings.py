"""Fractional quantities must survive domain, repository, API and manual ledger."""

from unittest.mock import AsyncMock, MagicMock
from datetime import UTC, datetime
import pytest
from src.models.holding import HoldingCreate, Holding
from src.models.user_transaction import UserTransaction
from src.database.repositories.holding_repository import HoldingRepository
from src.api.schemas.portfolio_models import HoldingResponse
from src.services.holdings_ledger import apply_transaction


@pytest.mark.asyncio
async def test_fractional_repository_and_wire_response_are_not_integers():
    collection = MagicMock()
    from tests.evidence_fixtures import Database

    collection.database = Database()
    collection.insert_one = AsyncMock()
    saved = await HoldingRepository(collection).create(
        holding_create=HoldingCreate(symbol="AAPL", quantity=0.5, avg_price=100)
    )
    assert collection.insert_one.call_args.args[0]["quantity"] == 0.5
    assert saved.cost_basis == 50
    assert HoldingResponse.from_holding(saved).model_dump()["quantity"] == 0.5


@pytest.mark.asyncio
async def test_fractional_manual_sells_do_not_leave_float_dust_or_oversell():
    row = Holding(
        holding_id="h1", symbol="AAPL", quantity=0.3, avg_price=100, cost_basis=30
    )
    repo = MagicMock()
    repo.get_by_symbol = AsyncMock(side_effect=lambda **kw: row)
    repo.delete = AsyncMock()

    async def update(_id, values):
        row.quantity = values.quantity

    repo.update = AsyncMock(side_effect=update)
    for qty in (0.1, 0.2):
        tx = UserTransaction(
            transaction_id=str(qty),
            symbol="AAPL",
            side="sell",
            quantity=qty,
            price=100,
            total_amount=qty * 100,
            executed_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await apply_transaction(tx, repo)
    repo.delete.assert_awaited_once_with("h1")
