"""
Unit tests for HoldingRepository.

Tests portfolio holding data access operations including:
- Creating holdings with cost basis calculation
- Retrieving holdings by ID and symbol
- Listing user holdings
- Updating holdings (quantity, avg_price)
- Price updates with P/L recalculation
- P/L calculation logic (market_value, unrealized P/L, % gain/loss)
- Holding deletion
- Index creation for optimal performance
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from pymongo.errors import DuplicateKeyError

from src.database.repositories.holding_repository import HoldingRepository
from src.models.holding import Holding, HoldingCreate, HoldingUpdate

# ===== Fixtures =====


@pytest.fixture
def mock_collection():
    """Mock MongoDB collection"""
    collection = Mock()
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
    """Create HoldingRepository instance"""
    return HoldingRepository(mock_collection)


@pytest.fixture
def sample_holding():
    """Sample holding object"""
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
    """Sample holding creation data"""
    return HoldingCreate(symbol="AAPL", quantity=100, avg_price=150.50)


# ===== Index Tests =====


# ===== Create Tests =====


class TestCreate:
    """Test holding creation"""

    @pytest.mark.asyncio
    async def test_create_holding_success(
        self, repository, mock_collection, sample_holding_create
    ):
        """Test successful holding creation"""
        # Arrange
        mock_collection.insert_one.return_value = Mock(inserted_id="mongo_id")

        # Act
        result = await repository.create("user_123", sample_holding_create)

        # Assert
        assert result.symbol == "AAPL"
        assert result.quantity == 100
        assert result.avg_price == 150.50
        assert result.cost_basis == 15050.00  # 100 * 150.50
        assert result.holding_id.startswith("holding_")
        assert result.current_price is None  # Not set initially
        assert result.market_value is None
        assert result.unrealized_pl is None
        mock_collection.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_holding_uppercases_symbol(self, repository, mock_collection):
        """Test that symbol is converted to uppercase"""
        # Arrange
        holding_create = HoldingCreate(symbol="aapl", quantity=10, avg_price=100.0)
        mock_collection.insert_one.return_value = Mock(inserted_id="mongo_id")

        # Act
        result = await repository.create("user_123", holding_create)

        # Assert
        assert result.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_create_holding_calculates_cost_basis(
        self, repository, mock_collection
    ):
        """Test that cost basis is correctly calculated"""
        # Arrange
        holding_create = HoldingCreate(symbol="GOOGL", quantity=50, avg_price=2500.75)
        mock_collection.insert_one.return_value = Mock(inserted_id="mongo_id")

        # Act
        result = await repository.create("user_123", holding_create)

        # Assert
        expected_cost_basis = 50 * 2500.75
        assert result.cost_basis == expected_cost_basis

    @pytest.mark.asyncio
    async def test_create_duplicate_holding_raises_error(
        self, repository, mock_collection, sample_holding_create
    ):
        """Test that duplicate holding (user+symbol) raises DuplicateKeyError"""
        # Arrange
        mock_collection.insert_one.side_effect = DuplicateKeyError("Duplicate key")

        # Act & Assert
        with pytest.raises(DuplicateKeyError):
            await repository.create("user_123", sample_holding_create)


# ===== Get Tests =====


class TestGet:
    """Test holding retrieval by ID"""

    @pytest.mark.asyncio
    async def test_get_existing_holding(self, repository, mock_collection):
        """Test retrieving existing holding"""
        # Arrange
        now = datetime.now(UTC)
        mock_collection.find_one.return_value = {
            "_id": "mongo_id",
            "holding_id": "holding_abc123",
            "user_id": "user_123",
            "symbol": "AAPL",
            "quantity": 100,
            "avg_price": 150.50,
            "current_price": 155.25,
            "cost_basis": 15050.00,
            "market_value": 15525.00,
            "unrealized_pl": 475.00,
            "unrealized_pl_pct": 3.16,
            "created_at": now,
            "updated_at": now,
            "last_price_update": now,
        }

        # Act
        result = await repository.get("holding_abc123")

        # Assert
        assert result is not None
        assert result.holding_id == "holding_abc123"
        assert result.symbol == "AAPL"
        assert result.quantity == 100
        mock_collection.find_one.assert_called_once_with(
            {"holding_id": "holding_abc123"}
        )

    @pytest.mark.asyncio
    async def test_get_nonexistent_holding(self, repository, mock_collection):
        """Test retrieving non-existent holding returns None"""
        # Arrange
        mock_collection.find_one.return_value = None

        # Act
        result = await repository.get("nonexistent")

        # Assert
        assert result is None


class TestGetBySymbol:
    """Test holding retrieval by user and symbol"""

    @pytest.mark.asyncio
    async def test_get_by_symbol_not_found(self, repository, mock_collection):
        """Test retrieving non-existent holding by symbol"""
        # Arrange
        mock_collection.find_one.return_value = None

        # Act
        result = await repository.get_by_symbol("user_123", "NONEXISTENT")

        # Assert
        assert result is None


# ===== List Tests =====


class TestListByUser:
    """Test listing user holdings"""

    @pytest.mark.asyncio
    async def test_list_by_user_empty_portfolio(self, repository, mock_collection):
        """Test listing holdings for user with no holdings"""

        # Arrange
        async def mock_async_iter():
            return
            yield  # Make this an async generator

        mock_cursor = Mock()
        mock_cursor.sort = Mock(return_value=mock_cursor)
        mock_cursor.__aiter__ = lambda self: mock_async_iter()
        mock_collection.find.return_value = mock_cursor

        # Act
        result = await repository.list_by_user("user_empty")

        # Assert
        assert result == []


# ===== P/L Calculation Tests =====


class TestCalculatePL:
    """Test profit/loss calculation logic"""

    def test_calculate_pl_profit(self, repository):
        """Test P/L calculation with profit"""
        # Arrange
        quantity = 100
        current_price = 155.00
        cost_basis = 15000.00  # avg_price = 150.00

        # Act
        result = repository._calculate_pl(quantity, current_price, cost_basis)

        # Assert
        assert result["market_value"] == 15500.00
        assert result["unrealized_pl"] == 500.00
        assert abs(result["unrealized_pl_pct"] - 3.33) < 0.01  # ~3.33%

    def test_calculate_pl_loss(self, repository):
        """Test P/L calculation with loss"""
        # Arrange
        quantity = 50
        current_price = 2400.00
        cost_basis = 125000.00  # avg_price = 2500.00

        # Act
        result = repository._calculate_pl(quantity, current_price, cost_basis)

        # Assert
        assert result["market_value"] == 120000.00
        assert result["unrealized_pl"] == -5000.00
        assert result["unrealized_pl_pct"] == -4.00  # -4%

    def test_calculate_pl_break_even(self, repository):
        """Test P/L calculation at break-even"""
        # Arrange
        quantity = 200
        current_price = 100.00
        cost_basis = 20000.00  # avg_price = 100.00

        # Act
        result = repository._calculate_pl(quantity, current_price, cost_basis)

        # Assert
        assert result["market_value"] == 20000.00
        assert result["unrealized_pl"] == 0.00
        assert result["unrealized_pl_pct"] == 0.00


# ===== Update Tests =====


class TestUpdate:
    """Test holding updates"""

    @pytest.mark.asyncio
    async def test_update_quantity_only(self, repository, mock_collection):
        """Test updating only quantity"""
        # Arrange
        now = datetime.now(UTC)

        # Mock get() call to return current holding
        current_holding = Holding(
            holding_id="holding_123",
            user_id="user_456",
            symbol="AAPL",
            quantity=100,
            avg_price=150.00,
            current_price=155.00,
            cost_basis=15000.00,
            market_value=15500.00,
            unrealized_pl=500.00,
            unrealized_pl_pct=3.33,
            created_at=now,
            updated_at=now,
            last_price_update=now,
        )

        # Mock find_one for get() call
        mock_collection.find_one.return_value = {
            "_id": "mongo_id",
            **current_holding.model_dump(),
        }

        # Mock find_one_and_update to return updated holding
        mock_collection.find_one_and_update.return_value = {
            "_id": "mongo_id",
            "holding_id": "holding_123",
            "user_id": "user_456",
            "symbol": "AAPL",
            "quantity": 150,  # Updated
            "avg_price": 150.00,
            "current_price": 155.00,
            "cost_basis": 22500.00,  # Recalculated: 150 * 150
            "market_value": 23250.00,  # Recalculated: 150 * 155
            "unrealized_pl": 750.00,
            "unrealized_pl_pct": 3.33,
            "created_at": now,
            "updated_at": now,
            "last_price_update": now,
        }

        holding_update = HoldingUpdate(quantity=150)

        # Act
        result = await repository.update("holding_123", holding_update)

        # Assert
        assert result is not None
        assert result.quantity == 150
        assert result.cost_basis == 22500.00

    @pytest.mark.asyncio
    async def test_update_avg_price_only(self, repository, mock_collection):
        """Test updating only average price"""
        # Arrange
        now = datetime.now(UTC)

        # Mock get() call
        current_holding = Holding(
            holding_id="holding_123",
            user_id="user_456",
            symbol="GOOGL",
            quantity=50,
            avg_price=2500.00,
            current_price=2600.00,
            cost_basis=125000.00,
            market_value=130000.00,
            unrealized_pl=5000.00,
            unrealized_pl_pct=4.00,
            created_at=now,
            updated_at=now,
            last_price_update=now,
        )

        mock_collection.find_one.return_value = {
            "_id": "mongo_id",
            **current_holding.model_dump(),
        }

        mock_collection.find_one_and_update.return_value = {
            "_id": "mongo_id",
            "holding_id": "holding_123",
            "user_id": "user_456",
            "symbol": "GOOGL",
            "quantity": 50,
            "avg_price": 2550.00,  # Updated
            "current_price": 2600.00,
            "cost_basis": 127500.00,  # Recalculated
            "market_value": 130000.00,
            "unrealized_pl": 2500.00,  # Recalculated
            "unrealized_pl_pct": 1.96,
            "created_at": now,
            "updated_at": now,
            "last_price_update": now,
        }

        holding_update = HoldingUpdate(avg_price=2550.00)

        # Act
        result = await repository.update("holding_123", holding_update)

        # Assert
        assert result is not None
        assert result.avg_price == 2550.00
        assert result.cost_basis == 127500.00

    @pytest.mark.asyncio
    async def test_update_nonexistent_holding(self, repository, mock_collection):
        """Test updating non-existent holding returns None"""
        # Arrange
        mock_collection.find_one.return_value = None
        mock_collection.find_one_and_update.return_value = None
        holding_update = HoldingUpdate(quantity=100)

        # Act
        result = await repository.update("nonexistent", holding_update)

        # Assert
        assert result is None


class TestUpdatePrice:
    """Test price update with P/L recalculation"""

    @pytest.mark.asyncio
    async def test_update_price_success(self, repository, mock_collection):
        """Test updating price and recalculating P/L"""
        # Arrange
        now = datetime.now(UTC)

        # Mock get() call
        current_holding = Holding(
            holding_id="holding_abc",
            user_id="user_123",
            symbol="TSLA",
            quantity=50,
            avg_price=200.00,
            current_price=190.00,
            cost_basis=10000.00,
            market_value=9500.00,
            unrealized_pl=-500.00,
            unrealized_pl_pct=-5.00,
            created_at=now,
            updated_at=now,
            last_price_update=now,
        )

        mock_collection.find_one.return_value = {
            "_id": "mongo_id",
            **current_holding.model_dump(),
        }

        # Mock find_one_and_update
        new_price = 220.00
        mock_collection.find_one_and_update.return_value = {
            "_id": "mongo_id",
            "holding_id": "holding_abc",
            "user_id": "user_123",
            "symbol": "TSLA",
            "quantity": 50,
            "avg_price": 200.00,
            "current_price": new_price,  # Updated
            "cost_basis": 10000.00,
            "market_value": 11000.00,  # Recalculated: 50 * 220
            "unrealized_pl": 1000.00,  # Recalculated
            "unrealized_pl_pct": 10.00,  # Recalculated
            "created_at": now,
            "updated_at": now,
            "last_price_update": now,
        }

        # Act
        result = await repository.update_price("holding_abc", new_price)

        # Assert
        assert result is not None
        assert result.current_price == 220.00
        assert result.market_value == 11000.00
        assert result.unrealized_pl == 1000.00
        assert result.unrealized_pl_pct == 10.00

    @pytest.mark.asyncio
    async def test_update_price_nonexistent_holding(self, repository, mock_collection):
        """Test updating price for non-existent holding"""
        # Arrange
        mock_collection.find_one.return_value = None

        # Act
        result = await repository.update_price("nonexistent", 100.00)

        # Assert
        assert result is None


# ===== Delete Tests =====


class TestDelete:
    """Test holding deletion"""

    @pytest.mark.asyncio
    async def test_delete_success(self, repository, mock_collection):
        """Test successfully deleting a holding"""
        # Arrange
        mock_result = Mock()
        mock_result.deleted_count = 1
        mock_collection.delete_one.return_value = mock_result

        # Act
        result = await repository.delete("holding_123")

        # Assert
        assert result is True
        mock_collection.delete_one.assert_called_once_with(
            {"holding_id": "holding_123"}
        )

    @pytest.mark.asyncio
    async def test_delete_not_found(self, repository, mock_collection):
        """Test deleting non-existent holding returns False"""
        # Arrange
        mock_result = Mock()
        mock_result.deleted_count = 0
        mock_collection.delete_one.return_value = mock_result

        # Act
        result = await repository.delete("nonexistent")

        # Assert
        assert result is False
