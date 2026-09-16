"""Legacy records remain readable; every former AI write entry is closed."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
import pytest
from src.database.repositories.portfolio_order_repository import (
    PortfolioOrderRepository,
)
from src.database.repositories.decision_assessment_repository import (
    DecisionWriteRejected,
)
from src.models.portfolio import PortfolioOrder


@pytest.fixture
def order():
    return PortfolioOrder(
        order_id="order_1",
        chat_id="chat_1",
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
@pytest.mark.parametrize("method", ["create", "upsert", "create_many", "mark_filled"])
async def test_legacy_writes_cannot_promote_unverified_data(order, method):
    collection = MagicMock()
    repository = PortfolioOrderRepository(collection)
    with pytest.raises(DecisionWriteRejected):
        if method == "create_many":
            await repository.create_many([order])
        elif method == "mark_filled":
            await repository.mark_filled(
                order.order_id, 2, 201, datetime.now(UTC), "tx1"
            )
        else:
            await getattr(repository, method)(order)
    collection.insert_one.assert_not_called()
    collection.find_one_and_update.assert_not_called()


@pytest.mark.asyncio
async def test_get_by_order_id_preserves_historical_data(order):
    collection = MagicMock()
    collection.find_one = AsyncMock(return_value={"_id": "mongo", **order.model_dump()})
    assert await PortfolioOrderRepository(collection).get(order.order_id) == order
    collection.find_one.assert_awaited_once_with({"order_id": order.order_id})


@pytest.mark.asyncio
async def test_ensure_indexes_has_no_broker_index():
    collection = MagicMock()
    collection.create_index = AsyncMock()
    await PortfolioOrderRepository(collection).ensure_indexes()
    calls = collection.create_index.await_args_list
    assert any(
        call.kwargs["name"] == "idx_order_id_unique" and call.kwargs.get("unique")
        for call in calls
    )
    assert all(call.kwargs["name"] != "idx_alpaca_order" for call in calls)
