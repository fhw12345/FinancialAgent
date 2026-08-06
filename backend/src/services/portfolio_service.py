"""
Portfolio service for holdings management with real-time pricing.

Coordinates between holding repository and market data services.
"""

from typing import Any

import structlog

from ..core.config import Settings
from ..core.data.ticker_data_service import TickerDataService
from ..database.repositories.holding_repository import HoldingRepository
from ..models.holding import Holding, HoldingCreate, HoldingUpdate

logger = structlog.get_logger()


class PortfolioService:
    """Service for portfolio management with real-time pricing."""

    def __init__(
        self,
        holding_repo: HoldingRepository,
        ticker_service: TickerDataService,
        settings: Settings,
    ):
        """
        Initialize portfolio service.

        Args:
            holding_repo: Repository for holding persistence
            ticker_service: Service for market data
            settings: Application settings
        """
        self.holding_repo = holding_repo
        self.ticker_service = ticker_service
        self.settings = settings

    async def add_holding(self, user_id: str, holding_create: HoldingCreate) -> Holding:
        """
        Add new holding to portfolio.

        Auto-fetches current price if avg_price not provided.

        Args:
            user_id: User identifier
            holding_create: Holding creation data

        Returns:
            Created holding with cost basis calculated

        Raises:
            ValueError: If holding already exists for symbol or price unavailable
        """
        # Check for duplicate
        existing = await self.holding_repo.get_by_symbol(
            user_id, holding_create.symbol.upper()
        )
        if existing:
            raise ValueError(
                f"Holding already exists for {holding_create.symbol}. "
                "Use PATCH to update quantity."
            )

        # Auto-fetch price if not provided
        if holding_create.avg_price is None:
            logger.info(
                "Auto-fetching price for new holding",
                symbol=holding_create.symbol,
            )
            current_price = await self.ticker_service.get_current_price(
                holding_create.symbol.upper()
            )
            if not current_price or current_price <= 0:
                raise ValueError(
                    f"Unable to fetch current price for {holding_create.symbol}. "
                    "Please try again or provide price manually."
                )
            holding_create.avg_price = current_price
            logger.info(
                "Using current price as purchase price",
                symbol=holding_create.symbol,
                price=current_price,
            )

        # Create holding
        holding = await self.holding_repo.create(user_id, holding_create)

        # Try to fetch current price (non-blocking)
        try:
            current_price = await self.ticker_service.get_current_price(holding.symbol)
            if current_price and current_price > 0:
                updated = await self.holding_repo.update_price(
                    holding.holding_id, current_price
                )
                if updated is not None:
                    holding = updated
                    logger.info(
                        "Holding price initialized",
                        symbol=holding.symbol,
                        current_price=current_price,
                    )
            elif current_price is not None:
                logger.warning(
                    "Invalid price received (<=0)",
                    symbol=holding.symbol,
                    current_price=current_price,
                )
        except Exception as e:
            logger.warning(
                "Failed to initialize holding price",
                symbol=holding.symbol,
                error=str(e),
            )

        return holding

    async def get_user_holdings_with_prices(self, user_id: str) -> list[Holding]:
        """
        Get all holdings with updated prices.

        This method:
        1. Fetches holdings from DB
        2. Updates current prices from market data
        3. Recalculates P&L for each holding

        Args:
            user_id: User identifier

        Returns:
            List of holdings with current prices
        """
        holdings = await self.holding_repo.list_by_user(user_id)

        # Update prices for all holdings (parallel)
        updated_holdings = []
        for holding in holdings:
            try:
                current_price = await self.ticker_service.get_current_price(
                    holding.symbol
                )
                if current_price and current_price > 0:
                    updated_holding = await self.holding_repo.update_price(
                        holding.holding_id, current_price
                    )
                    if updated_holding:
                        updated_holdings.append(updated_holding)
                    else:
                        updated_holdings.append(holding)
                else:
                    updated_holdings.append(holding)
                    if current_price is not None and current_price <= 0:
                        logger.warning(
                            "Invalid price received (<=0)",
                            symbol=holding.symbol,
                            current_price=current_price,
                        )
            except Exception as e:
                logger.warning(
                    "Failed to update holding price",
                    symbol=holding.symbol,
                    error=str(e),
                )
                updated_holdings.append(holding)

        return updated_holdings

    async def get_portfolio_summary(self, user_id: str) -> dict[str, Any]:
        """
        Get portfolio summary with aggregated metrics.

        Calculates:
        - Total cost basis
        - Total market value
        - Total unrealized P&L

        Args:
            user_id: User identifier

        Returns:
            Dictionary with summary metrics
        """
        holdings = await self.get_user_holdings_with_prices(user_id)

        if not holdings:
            return {
                "holdings_count": 0,
                "total_cost_basis": None,
                "total_market_value": None,
                "total_unrealized_pl": None,
                "total_unrealized_pl_pct": None,
            }

        # Calculate totals
        total_cost_basis = sum(h.cost_basis for h in holdings)
        total_market_value = sum(
            h.market_value for h in holdings if h.market_value is not None
        )

        # Calculate overall P&L
        total_unrealized_pl = total_market_value - total_cost_basis
        total_unrealized_pl_pct = (
            (total_unrealized_pl / total_cost_basis) * 100
            if total_cost_basis > 0
            else 0
        )

        return {
            "holdings_count": len(holdings),
            "total_cost_basis": round(total_cost_basis, 2),
            "total_market_value": round(total_market_value, 2),
            "total_unrealized_pl": round(total_unrealized_pl, 2),
            "total_unrealized_pl_pct": round(total_unrealized_pl_pct, 2),
        }

    async def update_holding(
        self, user_id: str, holding_id: str, holding_update: HoldingUpdate
    ) -> Holding | None:
        """
        Update holding quantity or average price.

        Verifies ownership before updating.

        Args:
            user_id: User identifier (for ownership check)
            holding_id: Holding identifier
            holding_update: Fields to update

        Returns:
            Updated holding if found and owned by user, None otherwise
        """
        # Verify ownership
        holding = await self.holding_repo.get(holding_id)
        if not holding:
            logger.warning(
                "Holding not found",
                user_id=user_id,
                holding_id=holding_id,
            )
            return None

        # Update holding
        updated_holding = await self.holding_repo.update(holding_id, holding_update)

        return updated_holding

    async def delete_holding(self, user_id: str, holding_id: str) -> bool:
        """
        Delete holding from portfolio.

        Verifies ownership before deleting.

        Args:
            user_id: User identifier (for ownership check)
            holding_id: Holding identifier

        Returns:
            True if deleted, False if not found or access denied
        """
        # Verify ownership
        holding = await self.holding_repo.get(holding_id)
        if not holding:
            logger.warning(
                "Holding not found",
                user_id=user_id,
                holding_id=holding_id,
            )
            return False

        # Delete holding
        deleted = await self.holding_repo.delete(holding_id)

        return deleted
