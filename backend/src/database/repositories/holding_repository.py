"""
Holding repository for portfolio management.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorCollection

from src.core.utils.date_utils import utcnow

from ...models.holding import Holding, HoldingCreate, HoldingUpdate

logger = structlog.get_logger()


class HoldingRepository:
    """Repository for holding data access operations."""

    def __init__(self, collection: AsyncIOMotorCollection):
        """
        Initialize holding repository.

        Args:
            collection: MongoDB collection for holdings
        """
        self.collection = collection

    async def ensure_indexes(self) -> None:
        """Create indexes for optimal query performance."""
        # Unique index on symbol (no per-user partition)
        await self.collection.create_index("symbol", name="idx_symbol", unique=True)
        await self.collection.create_index(
            [("updated_at", -1)],
            name="idx_holdings_updated",
        )
        logger.info("Holding indexes ensured")

    async def create(
        self, user_id: str | None = None, holding_create: HoldingCreate = None
    ) -> Holding:
        """Create a new holding. user_id ignored."""
        import uuid

        holding_id = f"holding_{uuid.uuid4().hex[:12]}"
        cost_basis = holding_create.quantity * holding_create.avg_price

        holding = Holding(
            holding_id=holding_id,
            symbol=holding_create.symbol.upper(),
            quantity=holding_create.quantity,
            avg_price=holding_create.avg_price,
            current_price=None,
            cost_basis=cost_basis,
            market_value=None,
            unrealized_pl=None,
            unrealized_pl_pct=None,
            created_at=utcnow(),
            updated_at=utcnow(),
            last_price_update=None,
        )

        await self.collection.insert_one(holding.model_dump())
        logger.info(
            "Holding created",
            holding_id=holding_id,
            symbol=holding.symbol,
            quantity=holding.quantity,
        )
        return holding

    async def get(self, holding_id: str) -> Holding | None:
        holding_dict = await self.collection.find_one({"holding_id": holding_id})
        if not holding_dict:
            return None
        holding_dict.pop("_id", None)
        return Holding(**holding_dict)

    async def get_by_symbol(
        self, user_id: str | None = None, symbol: str = ""
    ) -> Holding | None:
        """Get holding by symbol. user_id ignored."""
        holding_dict = await self.collection.find_one({"symbol": symbol.upper()})
        if not holding_dict:
            return None
        holding_dict.pop("_id", None)
        return Holding(**holding_dict)

    async def list_by_user(self, user_id: str | None = None) -> list[Holding]:
        """List all holdings. user_id ignored."""
        cursor = self.collection.find({}).sort("updated_at", -1)
        holdings = []
        async for holding_dict in cursor:
            holding_dict.pop("_id", None)
            holdings.append(Holding(**holding_dict))
        return holdings

    def _calculate_pl(
        self, quantity: int, current_price: float, cost_basis: float
    ) -> dict[str, float]:
        """
        Calculate market value and P&L metrics.

        Args:
            quantity: Number of shares
            current_price: Current market price per share
            cost_basis: Total cost basis (qty * avg_price)

        Returns:
            Dictionary with market_value, unrealized_pl, unrealized_pl_pct
        """
        market_value = quantity * current_price
        unrealized_pl = market_value - cost_basis
        unrealized_pl_pct = (unrealized_pl / cost_basis) * 100 if cost_basis > 0 else 0

        return {
            "market_value": market_value,
            "unrealized_pl": unrealized_pl,
            "unrealized_pl_pct": unrealized_pl_pct,
        }

    async def update(
        self, holding_id: str, holding_update: HoldingUpdate
    ) -> Holding | None:
        """
        Update holding quantity or average price.

        Args:
            holding_id: Holding identifier
            holding_update: Fields to update

        Returns:
            Updated holding if found, None otherwise
        """
        # Build update dict
        update_dict: dict[str, Any] = {"updated_at": utcnow()}

        if holding_update.quantity is not None:
            update_dict["quantity"] = holding_update.quantity

        if holding_update.avg_price is not None:
            update_dict["avg_price"] = holding_update.avg_price

        # Recalculate cost basis if quantity or price changed
        if holding_update.quantity or holding_update.avg_price:
            # Get current holding to calculate new cost basis
            current = await self.get(holding_id)
            if current:
                new_qty = holding_update.quantity or current.quantity
                new_price = holding_update.avg_price or current.avg_price
                update_dict["cost_basis"] = new_qty * new_price

                # Recalculate market value and P/L if we have current price
                if current.current_price:
                    pl_metrics = self._calculate_pl(
                        new_qty, current.current_price, update_dict["cost_basis"]
                    )
                    update_dict.update(pl_metrics)

        # Update in database
        result = await self.collection.find_one_and_update(
            {"holding_id": holding_id},
            {"$set": update_dict},
            return_document=True,
        )

        if not result:
            return None

        # Remove MongoDB _id field
        result.pop("_id", None)

        logger.info(
            "Holding updated", holding_id=holding_id, fields=list(update_dict.keys())
        )

        return Holding(**result)

    async def update_price(
        self,
        holding_id: str,
        current_price: float,
        session: str | None = None,
    ) -> Holding | None:
        """
        Update current price and recalculate P/L.

        Args:
            holding_id: Holding identifier
            current_price: New market price
            session: Optional market session label ("pre"|"regular"|"post"|"closed").
                When provided, persisted to last_session. Omitted callers leave
                the existing value unchanged.

        Returns:
            Updated holding if found, None otherwise
        """
        # Get current holding
        holding = await self.get(holding_id)
        if not holding:
            return None

        # Calculate P/L using shared method
        pl_metrics = self._calculate_pl(
            holding.quantity, current_price, holding.cost_basis
        )

        # Update in database
        now = datetime.now(UTC)
        update_dict: dict = {
            "current_price": current_price,
            "last_price_update": now,
            "updated_at": now,
            **pl_metrics,  # Unpack market_value, unrealized_pl, unrealized_pl_pct
        }
        if session is not None:
            update_dict["last_session"] = session

        result = await self.collection.find_one_and_update(
            {"holding_id": holding_id},
            {"$set": update_dict},
            return_document=True,
        )

        if not result:
            return None

        # Remove MongoDB _id field
        result.pop("_id", None)

        logger.info(
            "Holding price updated",
            holding_id=holding_id,
            symbol=holding.symbol,
            current_price=current_price,
            session=session,
            unrealized_pl=pl_metrics["unrealized_pl"],
        )

        return Holding(**result)

    async def delete(self, holding_id: str) -> bool:
        """
        Delete a holding.

        Args:
            holding_id: Holding identifier

        Returns:
            True if deleted, False if not found
        """
        result = await self.collection.delete_one({"holding_id": holding_id})

        if result.deleted_count > 0:
            logger.info("Holding deleted", holding_id=holding_id)
            return True

        return False
