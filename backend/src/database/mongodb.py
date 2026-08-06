"""
MongoDB connection and operations.
Following Factor 3: External Dependencies as Services.
"""

import typing

import structlog
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)

from ..core.exceptions import ConfigurationError, DatabaseError

logger = structlog.get_logger()


class MongoDB:
    """MongoDB connection manager with async support."""

    def __init__(self) -> None:
        self.client: AsyncIOMotorClient[dict[str, typing.Any]] | None = None
        self.database: AsyncIOMotorDatabase[dict[str, typing.Any]] | None = None

    async def connect(self, mongodb_url: str) -> None:
        """Establish connection to MongoDB."""
        try:
            # Extract and validate database name from URL
            db_with_params = mongodb_url.split("/")[-1]
            raw_db_name = db_with_params  # For logging
            database_name = (
                db_with_params.split("?")[0]
                if "?" in db_with_params
                else db_with_params
            )

            # Validate database name doesn't contain query parameters
            if any(char in database_name for char in ["?", "&", "="]):
                logger.error(
                    "Invalid database name: contains query parameter characters",
                    raw_value=raw_db_name,
                    parsed_value=database_name,
                    mongodb_url_suffix=db_with_params,
                )
                raise ConfigurationError(
                    f"Database name '{database_name}' contains invalid characters (?, &, =). "
                    f"Check MONGODB_URL format: should be mongodb://host/dbname?params",
                    raw_db_name=raw_db_name,
                    parsed_db_name=database_name,
                )

            # Log parsed database name for debugging
            if db_with_params != database_name:
                logger.info(
                    "Database name extracted from URL",
                    raw_url_suffix=db_with_params,
                    parsed_db_name=database_name,
                )

            self.client = AsyncIOMotorClient(mongodb_url)
            self.database = self.client[database_name]

            # Test connection
            await self.client.admin.command("ping")

            logger.info(
                "MongoDB connection established",
                database=database_name,
                connection_verified=True,
            )

        except ConfigurationError:
            # Re-raise configuration errors (already logged)
            raise
        except Exception as e:
            logger.error(
                "Failed to connect to MongoDB",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise DatabaseError(
                f"MongoDB connection failed: {str(e)}",
                original_error=type(e).__name__,
            ) from e

    async def disconnect(self) -> None:
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")

    async def health_check(self) -> dict[str, bool | str]:
        """Check MongoDB connection health."""
        try:
            if not self.client:
                return {"connected": False, "error": "No client connection"}

            # Ping database
            await self.client.admin.command("ping")

            # Get server info
            server_info = await self.client.server_info()

            return {
                "connected": True,
                "version": server_info.get("version", "unknown"),
                "database": (
                    self.database.name if self.database is not None else "unknown"
                ),
            }

        except Exception as e:
            logger.error("MongoDB health check failed", error=str(e))
            return {"connected": False, "error": str(e)}

    def get_collection(
        self, collection_name: str
    ) -> AsyncIOMotorCollection[dict[str, typing.Any]]:
        """Get a MongoDB collection."""
        if self.database is None:
            raise DatabaseError(
                "Cannot get collection: database connection not established",
                collection_name=collection_name,
            )
        return self.database[collection_name]
