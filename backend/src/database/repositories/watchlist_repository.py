"""
Watchlist repository for managing watched stocks.
Handles CRUD operations for watchlist collection.
"""

from datetime import datetime

import structlog
from motor.motor_asyncio import AsyncIOMotorCollection

from src.core.utils.date_utils import utcnow

from ...models.watchlist import WatchlistItem, WatchlistItemCreate

logger = structlog.get_logger()


class WatchlistRepository:
    """Repository for watchlist data access operations."""

    def __init__(self, collection: AsyncIOMotorCollection):
        """
        Initialize watchlist repository.

        Args:
            collection: MongoDB collection for watchlist items
        """
        self.collection = collection

    async def ensure_indexes(self) -> None:
        """Create indexes for optimal query performance."""
        # Unique index on symbol (no per-user partition)
        await self.collection.create_index(
            "symbol", unique=True, name="idx_symbol"
        )
        await self.collection.create_index(
            "last_analyzed_at", name="last_analyzed_at_1"
        )
        logger.info("Watchlist indexes ensured")

    async def create(
        self, user_id: str | None = None, watchlist_create: WatchlistItemCreate = None
    ) -> WatchlistItem:
        """Create a new watchlist item. user_id is ignored."""
        import uuid

        watchlist_id = f"watch_{uuid.uuid4().hex[:12]}"

        watchlist_item = WatchlistItem(
            watchlist_id=watchlist_id,
            symbol=watchlist_create.symbol.upper(),
            added_at=utcnow(),
            last_analyzed_at=None,
            notes=watchlist_create.notes,
        )

        await self.collection.insert_one(watchlist_item.model_dump())
        logger.info(
            "Watchlist item created",
            watchlist_id=watchlist_id,
            symbol=watchlist_item.symbol,
        )
        return watchlist_item

    async def get_by_user(
        self, user_id: str | None = None, skip: int = 0, limit: int = 50
    ) -> list[WatchlistItem]:
        """List watchlist items. user_id ignored."""
        cursor = (
            self.collection.find({})
            .sort("added_at", -1)
            .skip(skip)
            .limit(limit)
        )

        items = []
        async for item_dict in cursor:
            item_dict.pop("_id", None)
            items.append(WatchlistItem(**item_dict))
        return items

    async def get_by_id(
        self, watchlist_id: str, user_id: str | None = None
    ) -> WatchlistItem | None:
        """Get a specific watchlist item. user_id ignored."""
        item_dict = await self.collection.find_one({"watchlist_id": watchlist_id})
        if not item_dict:
            return None
        item_dict.pop("_id", None)
        return WatchlistItem(**item_dict)

    async def delete(
        self, watchlist_id: str, user_id: str | None = None
    ) -> bool:
        """Delete a watchlist item. user_id ignored."""
        result = await self.collection.delete_one({"watchlist_id": watchlist_id})
        deleted = result.deleted_count > 0
        if deleted:
            logger.info("Watchlist item deleted", watchlist_id=watchlist_id)
        return deleted

    async def update_last_analyzed(
        self,
        watchlist_id: str,
        user_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> bool:
        """Update last_analyzed_at timestamp. user_id ignored."""
        if timestamp is None:
            timestamp = utcnow()

        result = await self.collection.update_one(
            {"watchlist_id": watchlist_id},
            {"$set": {"last_analyzed_at": timestamp}},
        )
        return result.modified_count > 0

    async def get_stale_items(self, minutes: int = 5) -> list[WatchlistItem]:
        """Get watchlist items not analyzed recently."""
        from datetime import timedelta

        cutoff_time = utcnow() - timedelta(minutes=minutes)

        cursor = self.collection.find(
            {
                "$or": [
                    {"last_analyzed_at": None},
                    {"last_analyzed_at": {"$lt": cutoff_time}},
                ]
            }
        ).sort("last_analyzed_at", 1)

        items = []
        async for item_dict in cursor:
            item_dict.pop("_id", None)
            items.append(WatchlistItem(**item_dict))
        return items
