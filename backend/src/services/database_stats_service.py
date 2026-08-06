"""
Database statistics service for monitoring collection sizes and document counts.
"""

import typing

import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..api.schemas.admin_models import DatabaseStats

logger = structlog.get_logger()


class DatabaseStatsService:
    """Service for collecting MongoDB collection statistics."""

    def __init__(self, db: AsyncIOMotorDatabase[dict[str, typing.Any]]):
        """
        Initialize database statistics service.

        Args:
            db: MongoDB database instance
        """
        self.db = db

    async def get_collection_stats(self) -> list[DatabaseStats]:
        """
        Get statistics for all collections in the database.

        Collects:
        - Document count
        - Total size in bytes/MB
        - Average document size

        Returns:
            List of DatabaseStats sorted by size (largest first)
        """
        try:
            collection_names = await self.db.list_collection_names()
            stats = []

            for name in collection_names:
                # Skip system collections
                if name.startswith("system."):
                    continue

                try:
                    collection = self.db[name]

                    # Get document count
                    count = await collection.count_documents({})

                    # Get collection stats (size, avg doc size)
                    coll_stats = await self.db.command("collStats", name)

                    size_bytes = coll_stats.get("size", 0)
                    size_mb = size_bytes / (1024 * 1024)
                    avg_size = coll_stats.get("avgObjSize", 0)

                    stats.append(
                        DatabaseStats(
                            collection=name,
                            document_count=count,
                            size_bytes=size_bytes,
                            size_mb=round(size_mb, 2),
                            avg_document_size_bytes=avg_size,
                        )
                    )

                    logger.debug(
                        "Collected collection stats",
                        collection=name,
                        count=count,
                        size_mb=round(size_mb, 2),
                    )

                except Exception as e:
                    logger.warning(
                        "Failed to get stats for collection",
                        collection=name,
                        error=str(e),
                    )
                    continue

            # Sort by size (largest first)
            stats.sort(key=lambda x: x.size_bytes, reverse=True)

            logger.info(
                "Database statistics collected",
                total_collections=len(stats),
                total_size_mb=round(sum(s.size_mb for s in stats), 2),
            )

            return stats

        except Exception as e:
            logger.error("Failed to collect database statistics", error=str(e))
            return []
