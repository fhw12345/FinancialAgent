"""
Unit tests for PortfolioService.

Tests portfolio management with holdings CRUD and real-time pricing.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from src.models.holding import Holding, HoldingCreate, HoldingUpdate
from src.services.portfolio_service import PortfolioService


# ===== Fixtures =====


@pytest.fixture
def mock_holding_repo():
    """Mock HoldingRepository"""
    repo = Mock()
    repo.get_by_symbol = AsyncMock()
    repo.get = AsyncMock()
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.update_price = AsyncMock()
    repo.list_by_user = AsyncMock()
    repo.delete = AsyncMock()
    return repo


@pytest.fixture
def mock_ticker_service():
    """Mock TickerDataService"""
    service = Mock()
    service.get_current_price = AsyncMock()
    return service


@pytest.fixture
def mock_settings():
    """Mock Settings"""
    return Mock()


@pytest.fixture
def portfolio_service(mock_holding_repo, mock_ticker_service, mock_settings):
    """Create PortfolioService with mocked dependencies"""
    return PortfolioService(
        holding_repo=mock_holding_repo,
        ticker_service=mock_ticker_service,
        settings=mock_settings,
    )


@pytest.fixture
def sample_holding():
    """Sample holding for tests"""
    return Holding(
        holding_id="hold_123",
        user_id="user_456",
        symbol="AAPL",
        quantity=10.0,
        avg_price=150.0,
        cost_basis=1500.0,
        current_price=175.0,
        market_value=1750.0,
        unrealized_pl=250.0,
        unrealized_pl_pct=16.67,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_holding_create():
    """Sample HoldingCreate for tests"""
    return HoldingCreate(
        symbol="AAPL",
        quantity=10.0,
        avg_price=150.0,
    )


# ===== add_holding Tests =====


class TestAddHolding:
    """Test add_holding method"""

    @pytest.mark.asyncio
    async def test_add_holding_success(
        self, portfolio_service, mock_holding_repo, mock_ticker_service, sample_holding
    ):
        """Test successful holding addition"""
        mock_holding_repo.get_by_symbol.return_value = None  # No duplicate
        mock_holding_repo.create.return_value = sample_holding
        mock_ticker_service.get_current_price.return_value = 175.0
        mock_holding_repo.update_price.return_value = sample_holding

        holding_create = HoldingCreate(
            symbol="AAPL",
            quantity=10.0,
            avg_price=150.0,
        )

        result = await portfolio_service.add_holding("user_456", holding_create)

        assert result.symbol == "AAPL"
        mock_holding_repo.get_by_symbol.assert_called_once_with("user_456", "AAPL")
        mock_holding_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_holding_duplicate_symbol(
        self, portfolio_service, mock_holding_repo, sample_holding
    ):
        """Test adding duplicate holding raises error"""
        mock_holding_repo.get_by_symbol.return_value = sample_holding  # Existing

        holding_create = HoldingCreate(
            symbol="AAPL",
            quantity=5.0,
            avg_price=160.0,
        )

        with pytest.raises(ValueError) as exc_info:
            await portfolio_service.add_holding("user_456", holding_create)

        assert "already exists" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_add_holding_auto_fetch_price(
        self, portfolio_service, mock_holding_repo, mock_ticker_service, sample_holding
    ):
        """Test auto-fetching price when avg_price not provided"""
        mock_holding_repo.get_by_symbol.return_value = None
        mock_ticker_service.get_current_price.return_value = 175.0
        mock_holding_repo.create.return_value = sample_holding
        mock_holding_repo.update_price.return_value = sample_holding

        holding_create = HoldingCreate(
            symbol="AAPL",
            quantity=10.0,
            avg_price=None,  # No price provided
        )

        result = await portfolio_service.add_holding("user_456", holding_create)

        assert result is not None
        # First call for auto-fetch, second for initial price
        assert mock_ticker_service.get_current_price.call_count >= 1

    @pytest.mark.asyncio
    async def test_add_holding_price_fetch_fails(
        self, portfolio_service, mock_holding_repo, mock_ticker_service
    ):
        """Test error when price fetch fails and no price provided"""
        mock_holding_repo.get_by_symbol.return_value = None
        mock_ticker_service.get_current_price.return_value = None

        holding_create = HoldingCreate(
            symbol="INVALID",
            quantity=10.0,
            avg_price=None,
        )

        with pytest.raises(ValueError) as exc_info:
            await portfolio_service.add_holding("user_456", holding_create)

        assert "Unable to fetch current price" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_add_holding_zero_price_fails(
        self, portfolio_service, mock_holding_repo, mock_ticker_service
    ):
        """Test error when price is zero"""
        mock_holding_repo.get_by_symbol.return_value = None
        mock_ticker_service.get_current_price.return_value = 0.0

        holding_create = HoldingCreate(
            symbol="AAPL",
            quantity=10.0,
            avg_price=None,
        )

        with pytest.raises(ValueError) as exc_info:
            await portfolio_service.add_holding("user_456", holding_create)

        assert "Unable to fetch current price" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_add_holding_price_update_fails_gracefully(
        self, portfolio_service, mock_holding_repo, mock_ticker_service, sample_holding
    ):
        """Test that price update failure doesn't prevent holding creation"""
        mock_holding_repo.get_by_symbol.return_value = None
        mock_holding_repo.create.return_value = sample_holding
        mock_ticker_service.get_current_price.side_effect = Exception("API Error")

        holding_create = HoldingCreate(
            symbol="AAPL",
            quantity=10.0,
            avg_price=150.0,  # Price provided, so auto-fetch not needed
        )

        result = await portfolio_service.add_holding("user_456", holding_create)

        # Should still return holding even if price update fails
        assert result is not None


# ===== get_user_holdings_with_prices Tests =====


class TestGetUserHoldingsWithPrices:
    """Test get_user_holdings_with_prices method"""

    @pytest.mark.asyncio
    async def test_get_holdings_success(
        self, portfolio_service, mock_holding_repo, mock_ticker_service, sample_holding
    ):
        """Test successful retrieval of holdings with prices"""
        mock_holding_repo.list_by_user.return_value = [sample_holding]
        mock_ticker_service.get_current_price.return_value = 180.0
        mock_holding_repo.update_price.return_value = sample_holding

        result = await portfolio_service.get_user_holdings_with_prices("user_456")

        assert len(result) == 1
        assert result[0].symbol == "AAPL"
        mock_holding_repo.list_by_user.assert_called_once_with("user_456")

    @pytest.mark.asyncio
    async def test_get_holdings_empty_portfolio(
        self, portfolio_service, mock_holding_repo
    ):
        """Test empty portfolio returns empty list"""
        mock_holding_repo.list_by_user.return_value = []

        result = await portfolio_service.get_user_holdings_with_prices("user_456")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_holdings_price_update_failure(
        self, portfolio_service, mock_holding_repo, mock_ticker_service, sample_holding
    ):
        """Test holdings returned even when price update fails"""
        mock_holding_repo.list_by_user.return_value = [sample_holding]
        mock_ticker_service.get_current_price.side_effect = Exception("API Error")

        result = await portfolio_service.get_user_holdings_with_prices("user_456")

        assert len(result) == 1
        assert result[0] == sample_holding

    @pytest.mark.asyncio
    async def test_get_holdings_invalid_price_skipped(
        self, portfolio_service, mock_holding_repo, mock_ticker_service, sample_holding
    ):
        """Test holdings with invalid (<=0) price keep original data"""
        mock_holding_repo.list_by_user.return_value = [sample_holding]
        mock_ticker_service.get_current_price.return_value = -5.0  # Invalid

        result = await portfolio_service.get_user_holdings_with_prices("user_456")

        assert len(result) == 1
        # Original holding returned (price update skipped)
        mock_holding_repo.update_price.assert_not_called()


# ===== get_portfolio_summary Tests =====


class TestGetPortfolioSummary:
    """Test get_portfolio_summary method"""

    @pytest.mark.asyncio
    async def test_portfolio_summary_success(
        self, portfolio_service, mock_holding_repo, mock_ticker_service, sample_holding
    ):
        """Test successful portfolio summary calculation"""
        mock_holding_repo.list_by_user.return_value = [sample_holding]
        mock_ticker_service.get_current_price.return_value = 175.0
        mock_holding_repo.update_price.return_value = sample_holding

        result = await portfolio_service.get_portfolio_summary("user_456")

        assert result["holdings_count"] == 1
        assert result["total_cost_basis"] == 1500.0
        assert result["total_market_value"] == 1750.0
        assert result["total_unrealized_pl"] == 250.0

    @pytest.mark.asyncio
    async def test_portfolio_summary_empty(self, portfolio_service, mock_holding_repo):
        """Test portfolio summary for empty portfolio"""
        mock_holding_repo.list_by_user.return_value = []

        result = await portfolio_service.get_portfolio_summary("user_456")

        assert result["holdings_count"] == 0
        assert result["total_cost_basis"] is None
        assert result["total_market_value"] is None
        assert result["total_unrealized_pl"] is None

    @pytest.mark.asyncio
    async def test_portfolio_summary_multiple_holdings(
        self, portfolio_service, mock_holding_repo, mock_ticker_service
    ):
        """Test portfolio summary with multiple holdings"""
        holdings = [
            Holding(
                holding_id="hold_1",
                user_id="user_456",
                symbol="AAPL",
                quantity=10.0,
                avg_price=150.0,
                cost_basis=1500.0,
                current_price=175.0,
                market_value=1750.0,
                unrealized_pl=250.0,
                unrealized_pl_pct=16.67,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
            Holding(
                holding_id="hold_2",
                user_id="user_456",
                symbol="GOOGL",
                quantity=5.0,
                avg_price=100.0,
                cost_basis=500.0,
                current_price=120.0,
                market_value=600.0,
                unrealized_pl=100.0,
                unrealized_pl_pct=20.0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ),
        ]
        mock_holding_repo.list_by_user.return_value = holdings
        mock_ticker_service.get_current_price.return_value = None  # Skip updates

        result = await portfolio_service.get_portfolio_summary("user_456")

        assert result["holdings_count"] == 2
        assert result["total_cost_basis"] == 2000.0
        assert result["total_market_value"] == 2350.0


# ===== update_holding Tests =====


class TestUpdateHolding:
    """Test update_holding method"""

    @pytest.mark.asyncio
    async def test_update_holding_not_found(self, portfolio_service, mock_holding_repo):
        """Test update for non-existent holding"""
        mock_holding_repo.get.return_value = None

        update_data = HoldingUpdate(quantity=15.0)
        result = await portfolio_service.update_holding(
            "user_456", "nonexistent", update_data
        )

        assert result is None


# ===== delete_holding Tests =====


class TestDeleteHolding:
    """Test delete_holding method"""

    @pytest.mark.asyncio
    async def test_delete_holding_not_found(self, portfolio_service, mock_holding_repo):
        """Test delete for non-existent holding"""
        mock_holding_repo.get.return_value = None

        result = await portfolio_service.delete_holding("user_456", "nonexistent")

        assert result is False
        mock_holding_repo.delete.assert_not_called()
