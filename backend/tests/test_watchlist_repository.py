"""Tests for canonical watchlist repository persistence."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.repositories.watchlist_repository import WatchlistRepository


@pytest.mark.asyncio
async def test_get_by_symbol_normalizes_case():
    collection = MagicMock()
    collection.find_one = AsyncMock(
        return_value={
            "_id": "mongo-id",
            "watchlist_id": "watch_aapl",
            "symbol": "AAPL",
            "added_at": datetime(2026, 7, 17, tzinfo=UTC),
            "last_analyzed_at": None,
        }
    )
    repository = WatchlistRepository(collection)

    item = await repository.get_by_symbol(" aapl ")

    collection.find_one.assert_awaited_once_with({"symbol": "AAPL"})
    assert item is not None
    assert item.symbol == "AAPL"


@pytest.mark.asyncio
async def test_mark_analyzed_by_symbol_returns_written_timestamp():
    collection = MagicMock()
    collection.update_one = AsyncMock(
        return_value=SimpleNamespace(matched_count=1, modified_count=1)
    )
    repository = WatchlistRepository(collection)
    timestamp = datetime(2026, 7, 17, 5, 30, 0, 123456, tzinfo=UTC)
    persisted_timestamp = datetime(2026, 7, 17, 5, 30, 0, 123000, tzinfo=UTC)

    result = await repository.mark_analyzed_by_symbol(" aapl ", timestamp)

    collection.update_one.assert_awaited_once_with(
        {"symbol": "AAPL"},
        {"$set": {"last_analyzed_at": persisted_timestamp}},
    )
    assert result == persisted_timestamp


@pytest.mark.asyncio
async def test_mark_analyzed_by_symbol_returns_none_when_not_watched():
    collection = MagicMock()
    collection.update_one = AsyncMock(
        return_value=SimpleNamespace(matched_count=0, modified_count=0)
    )
    repository = WatchlistRepository(collection)

    result = await repository.mark_analyzed_by_symbol("MSFT")

    assert result is None


@pytest.mark.asyncio
async def test_mark_analyzed_by_symbol_propagates_database_error():
    collection = MagicMock()
    collection.update_one = AsyncMock(side_effect=RuntimeError("mongo unavailable"))
    repository = WatchlistRepository(collection)

    with pytest.raises(RuntimeError, match="mongo unavailable"):
        await repository.mark_analyzed_by_symbol("AAPL")
