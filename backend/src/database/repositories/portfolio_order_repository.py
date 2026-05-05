"""
Portfolio order repository for order audit trail.

Stores all orders placed through Alpaca with complete audit trail
linking orders to analysis decisions and chat contexts.

W5b: user_id removed from schema. user_id parameter kept on read methods
for caller compatibility but ignored.
"""

from datetime import datetime
from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorCollection

from src.core.utils.date_utils import utcnow

from ...models.portfolio import PortfolioOrder

logger = structlog.get_logger()


class PortfolioOrderRepository:
    """Repository for portfolio order data access operations."""

    def __init__(self, collection: AsyncIOMotorCollection):
        """
        Initialize portfolio order repository.

        Args:
            collection: MongoDB collection for portfolio_orders
        """
        self.collection = collection

    async def ensure_indexes(self) -> None:
        """Create indexes for optimal query performance."""
        # Index for listing orders sorted by time
        await self.collection.create_index(
            [("created_at", -1)],
            name="idx_orders_created",
        )
        # Audit trail
        await self.collection.create_index(
            [("analysis_id", 1)],
            name="idx_analysis_orders",
        )
        # Unique on Alpaca id, but only for documents that actually have one.
        # `sparse=True` doesn't help here because pydantic always writes the
        # field as null; partialFilterExpression is the correct mongo idiom.
        # If an old `idx_alpaca_order` index exists from before, drop it first.
        try:
            await self.collection.drop_index("idx_alpaca_order")
        except Exception:
            pass  # Index didn't exist, fine
        await self.collection.create_index(
            [("alpaca_order_id", 1)],
            name="idx_alpaca_order",
            unique=True,
            partialFilterExpression={"alpaca_order_id": {"$type": "string"}},
        )
        # Status filter
        await self.collection.create_index(
            [("status", 1), ("created_at", -1)],
            name="idx_status_orders",
        )
        # Symbol-specific
        await self.collection.create_index(
            [("symbol", 1), ("created_at", -1)],
            name="idx_symbol_orders",
        )
        logger.info("Portfolio order indexes ensured")

    async def create(self, order: PortfolioOrder) -> PortfolioOrder:
        """
        Create a new portfolio order.

        Args:
            order: Portfolio order to store

        Returns:
            Created order

        Raises:
            DuplicateKeyError: If order with same alpaca_order_id exists
        """
        # Convert to dict for MongoDB
        order_dict = order.model_dump()

        # Insert into database
        await self.collection.insert_one(order_dict)

        logger.info(
            "Portfolio order created",
            order_id=order.order_id,
            alpaca_order_id=order.alpaca_order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            status=order.status,
            analysis_id=order.analysis_id,
        )

        return order

    async def create_many(self, orders: list[PortfolioOrder]) -> int:
        """
        Batch insert multiple portfolio orders.

        Uses insert_many() for efficient bulk insertion, reducing
        database round trips from N to 1.

        Args:
            orders: List of portfolio orders to store

        Returns:
            Number of orders inserted

        Raises:
            BulkWriteError: If any order fails (e.g., duplicate alpaca_order_id)
        """
        if not orders:
            return 0

        order_dicts = [o.model_dump() for o in orders]
        result = await self.collection.insert_many(order_dicts)

        logger.info(
            "Portfolio orders batch created",
            count=len(result.inserted_ids),
            symbols=[o.symbol for o in orders],
        )

        return len(result.inserted_ids)

    async def get(self, order_id: str) -> PortfolioOrder | None:
        """
        Get order by internal order ID.

        Args:
            order_id: Internal order identifier

        Returns:
            PortfolioOrder if found, None otherwise
        """
        order_dict = await self.collection.find_one({"order_id": order_id})

        if not order_dict:
            return None

        # Remove MongoDB _id field
        order_dict.pop("_id", None)

        return PortfolioOrder(**order_dict)

    async def get_by_alpaca_id(self, alpaca_order_id: str) -> PortfolioOrder | None:
        """
        Get order by Alpaca order ID.

        Args:
            alpaca_order_id: Alpaca's native order UUID

        Returns:
            PortfolioOrder if found, None otherwise
        """
        order_dict = await self.collection.find_one(
            {"alpaca_order_id": alpaca_order_id}
        )

        if not order_dict:
            return None

        # Remove MongoDB _id field
        order_dict.pop("_id", None)

        return PortfolioOrder(**order_dict)

    async def get_by_analysis_id(self, analysis_id: str) -> PortfolioOrder | None:
        """
        Get order by analysis ID (audit trail).

        Args:
            analysis_id: Analysis identifier used as client_order_id

        Returns:
            PortfolioOrder if found, None otherwise
        """
        order_dict = await self.collection.find_one({"analysis_id": analysis_id})

        if not order_dict:
            return None

        # Remove MongoDB _id field
        order_dict.pop("_id", None)

        return PortfolioOrder(**order_dict)

    async def list_by_user(
        self,
        user_id: str | None = None,
        status: str | None = None,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[PortfolioOrder]:
        """List orders. user_id ignored."""
        query: dict[str, Any] = {}

        if status:
            query["status"] = status

        if symbol:
            query["symbol"] = symbol.upper()

        cursor = self.collection.find(query).sort("created_at", -1).limit(limit)

        orders = []
        async for order_dict in cursor:
            order_dict.pop("_id", None)
            orders.append(PortfolioOrder(**order_dict))

        return orders

    async def list_by_chat(
        self, chat_id: str, limit: int = 100
    ) -> list[PortfolioOrder]:
        """
        List orders for a specific chat.

        Args:
            chat_id: Chat identifier
            limit: Maximum number of orders to return

        Returns:
            List of orders sorted by created_at descending
        """
        cursor = (
            self.collection.find({"chat_id": chat_id})
            .sort("created_at", -1)
            .limit(limit)
        )

        orders = []
        async for order_dict in cursor:
            # Remove MongoDB _id field
            order_dict.pop("_id", None)
            orders.append(PortfolioOrder(**order_dict))

        return orders

    async def update_status(
        self,
        alpaca_order_id: str,
        status: str,
        filled_qty: float | None = None,
        filled_avg_price: float | None = None,
        filled_at: datetime | None = None,
    ) -> PortfolioOrder | None:
        """
        Update order status and fill information.

        Used when order status changes in Alpaca (e.g., filled, canceled).

        Args:
            alpaca_order_id: Alpaca order UUID
            status: New status
            filled_qty: Filled quantity (if status is filled/partially_filled)
            filled_avg_price: Average fill price
            filled_at: Fill timestamp

        Returns:
            Updated order if found, None otherwise
        """
        # Build update dict
        update_dict = {
            "status": status,
            "updated_at": utcnow(),
        }

        if filled_qty is not None:
            update_dict["filled_qty"] = filled_qty

        if filled_avg_price is not None:
            update_dict["filled_avg_price"] = filled_avg_price

        if filled_at is not None:
            update_dict["filled_at"] = filled_at

        # Update in database
        result = await self.collection.find_one_and_update(
            {"alpaca_order_id": alpaca_order_id},
            {"$set": update_dict},
            return_document=True,
        )

        if not result:
            return None

        # Remove MongoDB _id field
        result.pop("_id", None)

        logger.info(
            "Order status updated",
            alpaca_order_id=alpaca_order_id,
            status=status,
            filled_qty=filled_qty,
            filled_avg_price=filled_avg_price,
        )

        return PortfolioOrder(**result)

    async def mark_filled(
        self,
        order_id: str,
        filled_qty: float,
        filled_avg_price: float,
        filled_at: datetime,
        user_transaction_id: str | None,
    ) -> PortfolioOrder | None:
        """
        Mark a locally-suggested order as executed by the user.

        This is the DecisionTracker "Mark Executed" path — distinct from
        `update_status` which keys on `alpaca_order_id` for live trading.
        Here we key on our DB primary key `order_id` because the order never
        went through Alpaca.
        """
        update_dict: dict[str, Any] = {
            "status": "filled",
            "filled_qty": filled_qty,
            "filled_avg_price": filled_avg_price,
            "filled_at": filled_at,
            "user_transaction_id": user_transaction_id,
            "updated_at": utcnow(),
        }
        result = await self.collection.find_one_and_update(
            {"order_id": order_id},
            {"$set": update_dict},
            return_document=True,
        )
        if not result:
            return None
        result.pop("_id", None)
        return PortfolioOrder(**result)

    async def revert_filled(self, order_id: str) -> PortfolioOrder | None:
        """
        Revert a previously-filled order back to "suggested" state.

        Used by the DELETE /user-transactions path so the originating order
        is no longer marked executed when the corresponding transaction is
        removed. We DO NOT clear `decision_price`, `decision_type`, or any
        of the audit fields — only the fill state.
        """
        update_dict: dict[str, Any] = {
            "status": "suggested",
            "filled_qty": 0.0,
            "filled_avg_price": None,
            "filled_at": None,
            "user_transaction_id": None,
            "updated_at": utcnow(),
        }
        result = await self.collection.find_one_and_update(
            {"order_id": order_id},
            {"$set": update_dict},
            return_document=True,
        )
        if not result:
            return None
        result.pop("_id", None)
        return PortfolioOrder(**result)

    async def count_by_user(
        self, user_id: str | None = None, status: str | None = None
    ) -> int:
        """Count orders. user_id ignored."""
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        return await self.collection.count_documents(query)

    # ---------------------------------------------------------------------
    # Decision-tracking (P&L snapshot) queries
    # ---------------------------------------------------------------------

    async def list_pending_pnl_snapshots(
        self,
        horizon_days: int,
        cutoff_dt: datetime,
        limit: int = 200,
    ) -> list[PortfolioOrder]:
        """
        Return decisions older than `horizon_days` (created_at <= cutoff_dt)
        that have a decision_price but no snapshot yet for this horizon.
        """
        horizon_key = f"pnl_snapshots.{horizon_days}d"
        query: dict[str, Any] = {
            "decision_price": {"$ne": None, "$gt": 0},
            "created_at": {"$lte": cutoff_dt},
            horizon_key: {"$exists": False},
        }
        cursor = self.collection.find(query).sort("created_at", -1).limit(limit)
        out: list[PortfolioOrder] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(PortfolioOrder(**doc))
        return out

    async def update_pnl_snapshot(
        self,
        order_id: str,
        horizon_days: int,
        snapshot: dict[str, Any],
    ) -> bool:
        """Write one P&L snapshot under pnl_snapshots.{N}d. Returns True if matched."""
        result = await self.collection.update_one(
            {"order_id": order_id},
            {
                "$set": {
                    f"pnl_snapshots.{horizon_days}d": snapshot,
                    "updated_at": utcnow(),
                }
            },
        )
        return result.matched_count > 0

    async def list_decisions(
        self,
        symbol: str | None = None,
        decision_type: str | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[PortfolioOrder]:
        """List decisions (orders + signals), newest first. Used by /api/decisions."""
        query: dict[str, Any] = {}
        if symbol:
            query["symbol"] = symbol.upper()
        if decision_type:
            query["decision_type"] = decision_type
        if source:
            query["recommendation_source"] = source
        cursor = self.collection.find(query).sort("created_at", -1).limit(limit)
        out: list[PortfolioOrder] = []
        async for doc in cursor:
            doc.pop("_id", None)
            out.append(PortfolioOrder(**doc))
        return out
