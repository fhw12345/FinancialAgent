"""Repository unit fixtures with a real in-memory control aggregate for write fencing."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.database.repositories.holding_repository import HoldingRepository
from src.models.holding import Holding, HoldingCreate
from tests.evidence_fixtures import Database


@pytest.fixture
def mock_collection():
    collection = Mock()
    collection.database = Database()
    collection.create_index = AsyncMock()
    collection.insert_one = AsyncMock()
    collection.find_one = AsyncMock()
    collection.find = Mock()
    collection.find_one_and_update = AsyncMock()
    collection.update_one = AsyncMock()
    collection.delete_one = AsyncMock()
    return collection


@pytest.fixture
def repository(mock_collection):
    return HoldingRepository(mock_collection)


@pytest.fixture
def sample_holding():
    return Holding(
        holding_id="holding_abc123",
        user_id="user_123",
        symbol="AAPL",
        quantity=100,
        avg_price=150.50,
        current_price=155.25,
        cost_basis=15050.00,
        market_value=15525.00,
        unrealized_pl=475.00,
        unrealized_pl_pct=3.16,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_price_update=datetime.now(UTC),
    )


@pytest.fixture
def sample_holding_create():
    return HoldingCreate(symbol="AAPL", quantity=100, avg_price=150.50)
