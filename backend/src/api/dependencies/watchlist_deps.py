"""Dependencies for watchlist API endpoints."""

from fastapi import Depends

from ...database.mongodb import MongoDB
from ...database.repositories.watchlist_repository import (
    WATCHLIST_COLLECTION,
    WatchlistRepository,
)
from .storage import get_mongodb


def get_watchlist_repository(
    mongodb: MongoDB = Depends(get_mongodb),
) -> WatchlistRepository:
    """Return the repository backed by the canonical watchlist collection."""
    return WatchlistRepository(mongodb.get_collection(WATCHLIST_COLLECTION))
