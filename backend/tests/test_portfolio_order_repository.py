"""Tests for local portfolio-order persistence."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.repositories.portfolio_order_repository import (
    PortfolioOrderRepository,
)
from src.models.portfolio import PortfolioOrder


@pytest.fixture
def order() -> PortfolioOrder:
    return PortfolioOrder(
        order_id="order_1",
        chat_id="chat_1",
        message_id="message_1",
        analysis_id="analysis_1",
        symbol="AAPL",
        order_type="market",
        side="buy",
        quantity=2,
        status="suggested",
        created_at=datetime.now(UTC),
        decision_price=200,
    )


@pytest.mark.asyncio
async def test_create_inserts_local_order(order):
    collection = MagicMock()
    collection.insert_one = AsyncMock()
    repository = PortfolioOrderRepository(collection)

    result = await repository.create(order)

    assert result == order
    collection.insert_one.assert_awaited_once_with(order.model_dump())


@pytest.mark.asyncio
async def test_get_by_order_id(order):
    collection = MagicMock()
    collection.find_one = AsyncMock(return_value={"_id": "mongo", **order.model_dump()})
    repository = PortfolioOrderRepository(collection)

    result = await repository.get(order.order_id)

    assert result == order
    collection.find_one.assert_awaited_once_with({"order_id": order.order_id})


@pytest.mark.asyncio
async def test_mark_filled_uses_local_order_id(order):
    filled_at = datetime.now(UTC)
    filled = {
        **order.model_dump(),
        "status": "filled",
        "filled_qty": 2,
        "filled_avg_price": 201,
        "filled_at": filled_at,
        "user_transaction_id": "tx_1",
    }
    collection = MagicMock()
    collection.find_one_and_update = AsyncMock(return_value=filled)
    repository = PortfolioOrderRepository(collection)

    result = await repository.mark_filled(
        order_id=order.order_id,
        filled_qty=2,
        filled_avg_price=201,
        filled_at=filled_at,
        user_transaction_id="tx_1",
    )

    assert result is not None
    assert result.status == "filled"
    query = collection.find_one_and_update.await_args.args[0]
    assert query == {"order_id": order.order_id}


@pytest.mark.asyncio
async def test_ensure_indexes_has_no_broker_index():
    collection = MagicMock()
    collection.create_index = AsyncMock()
    repository = PortfolioOrderRepository(collection)

    await repository.ensure_indexes()

    names = [call.kwargs["name"] for call in collection.create_index.await_args_list]
    assert "idx_alpaca_order" not in names
