"""
Unit tests for PortfolioOrderRepository.

Tests portfolio order data access operations including:
- Creating orders
- Retrieving orders by various IDs
- Listing orders with filters
- Updating order status
- Counting orders
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from pymongo.errors import DuplicateKeyError

from src.database.repositories.portfolio_order_repository import (
    PortfolioOrderRepository,
)
from src.models.portfolio import PortfolioOrder

# ===== Helper Classes =====


class AsyncIterator:
    """Helper class to make a list async-iterable for testing"""

    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


# ===== Fixtures =====


@pytest.fixture
def mock_collection():
    """Mock MongoDB collection"""
    collection = Mock()
    collection.create_index = AsyncMock()
    collection.insert_one = AsyncMock()
    collection.find_one = AsyncMock()
    collection.find = Mock()
    collection.update_one = AsyncMock()
    collection.find_one_and_update = AsyncMock()
    collection.count_documents = AsyncMock()
    return collection


@pytest.fixture
def repository(mock_collection):
    """Create PortfolioOrderRepository instance"""
    return PortfolioOrderRepository(mock_collection)


@pytest.fixture
def sample_order():
    """Sample portfolio order"""
    return PortfolioOrder(
        order_id="order_123",
        user_id="user_456",
        chat_id="chat_789",
        analysis_id="analysis_abc",
        alpaca_order_id="alpaca_xyz",
        symbol="AAPL",
        side="buy",
        quantity=10,
        order_type="market",
        time_in_force="day",
        limit_price=None,
        stop_price=None,
        status="pending_submit",
        filled_quantity=0,
        filled_avg_price=None,
        submitted_at=None,
        filled_at=None,
        cancelled_at=None,
        failed_at=None,
        failure_reason=None,
        created_at=datetime.now(UTC),
    )


# ===== Index Tests =====


# ===== Create Tests =====


class TestCreate:
    """Test order creation"""

    @pytest.mark.asyncio
    async def test_create_order_success(
        self, repository, mock_collection, sample_order
    ):
        """Test successful order creation"""
        # Arrange
        mock_collection.insert_one.return_value = Mock(inserted_id="mongo_id")

        # Act
        result = await repository.create(sample_order)

        # Assert
        assert result == sample_order
        mock_collection.insert_one.assert_called_once()

        # Verify order data was converted to dict
        call_args = mock_collection.insert_one.call_args[0][0]
        assert call_args["order_id"] == "order_123"
        assert call_args["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_create_duplicate_alpaca_id_raises_error(
        self, repository, mock_collection, sample_order
    ):
        """Test that duplicate alpaca_order_id raises error"""
        # Arrange
        mock_collection.insert_one.side_effect = DuplicateKeyError("Duplicate key")

        # Act & Assert
        with pytest.raises(DuplicateKeyError):
            await repository.create(sample_order)


# ===== Get Tests =====


class TestGet:
    """Test order retrieval by ID"""

    @pytest.mark.asyncio
    async def test_get_existing_order(self, repository, mock_collection):
        """Test retrieving existing order"""
        # Arrange
        mock_collection.find_one.return_value = {
            "order_id": "order_123",
            "user_id": "user_456",
            "chat_id": "chat_789",
            "analysis_id": "analysis_abc",
            "alpaca_order_id": "alpaca_xyz",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 10,
            "order_type": "market",
            "time_in_force": "day",
            "limit_price": None,
            "stop_price": None,
            "status": "filled",
            "filled_quantity": 10,
            "filled_avg_price": 150.50,
            "submitted_at": datetime.now(UTC),
            "filled_at": datetime.now(UTC),
            "cancelled_at": None,
            "failed_at": None,
            "failure_reason": None,
            "created_at": datetime.now(UTC),
        }

        # Act
        result = await repository.get("order_123")

        # Assert
        assert result is not None
        assert result.order_id == "order_123"
        assert result.symbol == "AAPL"
        mock_collection.find_one.assert_called_once_with({"order_id": "order_123"})

    @pytest.mark.asyncio
    async def test_get_nonexistent_order_returns_none(
        self, repository, mock_collection
    ):
        """Test that non-existent order returns None"""
        # Arrange
        mock_collection.find_one.return_value = None

        # Act
        result = await repository.get("nonexistent_order")

        # Assert
        assert result is None


class TestGetByAlpacaId:
    """Test order retrieval by Alpaca ID"""

    @pytest.mark.asyncio
    async def test_get_by_alpaca_id_success(self, repository, mock_collection):
        """Test retrieving order by Alpaca ID"""
        # Arrange
        mock_collection.find_one.return_value = {
            "order_id": "order_123",
            "alpaca_order_id": "alpaca_xyz",
            "user_id": "user_456",
            "chat_id": "chat_789",
            "analysis_id": "analysis_abc",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 10,
            "order_type": "market",
            "time_in_force": "day",
            "limit_price": None,
            "stop_price": None,
            "status": "filled",
            "filled_quantity": 10,
            "filled_avg_price": 150.50,
            "submitted_at": datetime.now(UTC),
            "filled_at": datetime.now(UTC),
            "cancelled_at": None,
            "failed_at": None,
            "failure_reason": None,
            "created_at": datetime.now(UTC),
        }

        # Act
        result = await repository.get_by_alpaca_id("alpaca_xyz")

        # Assert
        assert result is not None
        assert result.alpaca_order_id == "alpaca_xyz"
        mock_collection.find_one.assert_called_once_with(
            {"alpaca_order_id": "alpaca_xyz"}
        )


class TestGetByAnalysisId:
    """Test order retrieval by analysis ID"""

    @pytest.mark.asyncio
    async def test_get_by_analysis_id_success(self, repository, mock_collection):
        """Test retrieving order by analysis ID"""
        # Arrange
        mock_collection.find_one.return_value = {
            "order_id": "order_123",
            "alpaca_order_id": "alpaca_xyz",
            "user_id": "user_456",
            "chat_id": "chat_789",
            "analysis_id": "analysis_abc",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 10,
            "order_type": "market",
            "time_in_force": "day",
            "limit_price": None,
            "stop_price": None,
            "status": "filled",
            "filled_quantity": 10,
            "filled_avg_price": 150.50,
            "submitted_at": datetime.now(UTC),
            "filled_at": datetime.now(UTC),
            "cancelled_at": None,
            "failed_at": None,
            "failure_reason": None,
            "created_at": datetime.now(UTC),
        }

        # Act
        result = await repository.get_by_analysis_id("analysis_abc")

        # Assert
        assert result is not None
        assert result.analysis_id == "analysis_abc"
        mock_collection.find_one.assert_called_once_with(
            {"analysis_id": "analysis_abc"}
        )


# ===== List Tests =====


class TestListByUser:
    """Test listing orders by user"""

    @pytest.mark.asyncio
    async def test_list_by_user_no_filters(self, repository, mock_collection):
        """Test listing all orders for a user"""
        # Arrange
        order_data = [
            {
                "order_id": "order_1",
                "user_id": "user_456",
                "chat_id": "chat_789",
                "analysis_id": "analysis_abc",
                "alpaca_order_id": "alpaca_1",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 10,
                "order_type": "market",
                "time_in_force": "day",
                "limit_price": None,
                "stop_price": None,
                "status": "filled",
                "filled_quantity": 10,
                "filled_avg_price": 150.50,
                "submitted_at": datetime.now(UTC),
                "filled_at": datetime.now(UTC),
                "cancelled_at": None,
                "failed_at": None,
                "failure_reason": None,
                "created_at": datetime.now(UTC),
            },
            {
                "order_id": "order_2",
                "user_id": "user_456",
                "chat_id": "chat_789",
                "analysis_id": "analysis_def",
                "alpaca_order_id": "alpaca_2",
                "symbol": "GOOGL",
                "side": "sell",
                "quantity": 5,
                "order_type": "limit",
                "time_in_force": "gtc",
                "limit_price": 2800.00,
                "stop_price": None,
                "status": "pending_submit",
                "filled_quantity": 0,
                "filled_avg_price": None,
                "submitted_at": None,
                "filled_at": None,
                "cancelled_at": None,
                "failed_at": None,
                "failure_reason": None,
                "created_at": datetime.now(UTC),
            },
        ]
        mock_cursor = AsyncIterator(order_data)
        mock_cursor.sort = Mock(return_value=mock_cursor)
        mock_cursor.limit = Mock(return_value=mock_cursor)
        mock_collection.find.return_value = mock_cursor

        # Act
        result = await repository.list_by_user("user_456")

        # Assert
        assert len(result) == 2
        assert result[0].order_id == "order_1"
        assert result[1].order_id == "order_2"

class TestListByChat:
    """Test listing orders by chat"""

    @pytest.mark.asyncio
    async def test_list_by_chat_success(self, repository, mock_collection):
        """Test listing orders for a specific chat"""
        # Arrange
        mock_cursor = AsyncIterator([])
        mock_cursor.sort = Mock(return_value=mock_cursor)
        mock_cursor.limit = Mock(return_value=mock_cursor)
        mock_collection.find.return_value = mock_cursor

        # Act
        result = await repository.list_by_chat("chat_789")

        # Assert
        mock_collection.find.assert_called_once_with({"chat_id": "chat_789"})
        assert isinstance(result, list)


# ===== Update Tests =====


class TestUpdateStatus:
    """Test order status updates"""

    @pytest.mark.asyncio
    async def test_update_status_to_filled(self, repository, mock_collection):
        """Test updating order status to filled"""
        # Arrange
        filled_at = datetime.now(UTC)
        mock_collection.find_one_and_update.return_value = {
            "order_id": "order_123",
            "alpaca_order_id": "alpaca_xyz",
            "user_id": "user_456",
            "chat_id": "chat_789",
            "analysis_id": "analysis_abc",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 10,
            "order_type": "market",
            "time_in_force": "day",
            "limit_price": None,
            "stop_price": None,
            "status": "filled",
            "filled_qty": 10,
            "filled_avg_price": 150.50,
            "submitted_at": datetime.now(UTC),
            "filled_at": filled_at,
            "cancelled_at": None,
            "failed_at": None,
            "failure_reason": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

        # Act
        result = await repository.update_status(
            alpaca_order_id="alpaca_xyz",
            status="filled",
            filled_qty=10,
            filled_avg_price=150.50,
            filled_at=filled_at,
        )

        # Assert
        assert result is not None
        assert result.status == "filled"
        assert result.filled_qty == 10
        assert result.filled_avg_price == 150.50
        mock_collection.find_one_and_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_nonexistent_order(self, repository, mock_collection):
        """Test updating non-existent order returns None"""
        # Arrange
        mock_collection.find_one_and_update.return_value = None

        # Act
        result = await repository.update_status(
            alpaca_order_id="nonexistent", status="filled"
        )

        # Assert
        assert result is None
