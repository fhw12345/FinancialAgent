"""
Unit tests for DatabaseStatsService.

Tests MongoDB collection statistics collection.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from src.services.database_stats_service import DatabaseStatsService

# ===== Fixtures =====


@pytest.fixture
def mock_db():
    """Create mock MongoDB database."""
    db = AsyncMock()
    db.list_collection_names = AsyncMock(return_value=[])
    db.command = AsyncMock(return_value={})
    return db


@pytest.fixture
def stats_service(mock_db):
    """Create DatabaseStatsService with mocked database."""
    return DatabaseStatsService(db=mock_db)


# ===== __init__ Tests =====


class TestDatabaseStatsServiceInit:
    """Test DatabaseStatsService initialization."""

    def test_init_sets_db(self, mock_db):
        """Test initialization sets database."""
        service = DatabaseStatsService(db=mock_db)
        assert service.db == mock_db


# ===== get_collection_stats Tests =====


class TestGetCollectionStats:
    """Test get_collection_stats method."""

    @pytest.mark.asyncio
    async def test_empty_database(self, stats_service, mock_db):
        """Test getting stats from empty database."""
        mock_db.list_collection_names.return_value = []

        result = await stats_service.get_collection_stats()

        assert result == []
        mock_db.list_collection_names.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_collection(self, stats_service, mock_db):
        """Test getting stats for single collection."""
        mock_db.list_collection_names.return_value = ["users"]

        mock_collection = AsyncMock()
        mock_collection.count_documents = AsyncMock(return_value=100)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        mock_db.command.return_value = {
            "size": 102400,  # 100 KB
            "avgObjSize": 1024,
        }

        result = await stats_service.get_collection_stats()

        assert len(result) == 1
        assert result[0].collection == "users"
        assert result[0].document_count == 100
        assert result[0].size_bytes == 102400
        assert result[0].size_mb == 0.1  # 102400 / 1024 / 1024 ≈ 0.1
        assert result[0].avg_document_size_bytes == 1024

    @pytest.mark.asyncio
    async def test_multiple_collections_sorted_by_size(self, stats_service, mock_db):
        """Test collections are sorted by size (largest first)."""
        mock_db.list_collection_names.return_value = ["small", "large", "medium"]

        mock_collection = AsyncMock()
        mock_collection.count_documents = AsyncMock(return_value=10)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        # Return different sizes for each collection
        def command_side_effect(cmd, name):
            sizes = {
                "small": {"size": 1000, "avgObjSize": 100},
                "large": {"size": 100000, "avgObjSize": 1000},
                "medium": {"size": 10000, "avgObjSize": 500},
            }
            return sizes.get(name, {"size": 0, "avgObjSize": 0})

        mock_db.command.side_effect = command_side_effect

        result = await stats_service.get_collection_stats()

        assert len(result) == 3
        # Should be sorted by size descending
        assert result[0].collection == "large"
        assert result[1].collection == "medium"
        assert result[2].collection == "small"

    @pytest.mark.asyncio
    async def test_skips_system_collections(self, stats_service, mock_db):
        """Test system collections are skipped."""
        mock_db.list_collection_names.return_value = [
            "users",
            "system.indexes",
            "system.users",
            "messages",
        ]

        mock_collection = AsyncMock()
        mock_collection.count_documents = AsyncMock(return_value=50)
        mock_db.__getitem__ = Mock(return_value=mock_collection)
        mock_db.command.return_value = {"size": 5000, "avgObjSize": 100}

        result = await stats_service.get_collection_stats()

        # Only users and messages should be included
        assert len(result) == 2
        collection_names = [r.collection for r in result]
        assert "system.indexes" not in collection_names
        assert "system.users" not in collection_names

    @pytest.mark.asyncio
    async def test_handles_collection_error(self, stats_service, mock_db):
        """Test handles error for individual collection."""
        mock_db.list_collection_names.return_value = [
            "good_collection",
            "bad_collection",
        ]

        mock_collection = AsyncMock()
        mock_collection.count_documents = AsyncMock(return_value=10)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        def command_side_effect(cmd, name):
            if name == "bad_collection":
                raise Exception("Collection error")
            return {"size": 1000, "avgObjSize": 100}

        mock_db.command.side_effect = command_side_effect

        result = await stats_service.get_collection_stats()

        # Should still return good_collection
        assert len(result) == 1
        assert result[0].collection == "good_collection"

    @pytest.mark.asyncio
    async def test_handles_list_collections_error(self, stats_service, mock_db):
        """Test handles error when listing collections."""
        mock_db.list_collection_names.side_effect = Exception("Database error")

        result = await stats_service.get_collection_stats()

        assert result == []

    @pytest.mark.asyncio
    async def test_missing_size_defaults_to_zero(self, stats_service, mock_db):
        """Test missing size values default to zero."""
        mock_db.list_collection_names.return_value = ["empty_stats"]

        mock_collection = AsyncMock()
        mock_collection.count_documents = AsyncMock(return_value=0)
        mock_db.__getitem__ = Mock(return_value=mock_collection)

        # Return empty stats
        mock_db.command.return_value = {}

        result = await stats_service.get_collection_stats()

        assert len(result) == 1
        assert result[0].size_bytes == 0
        assert result[0].size_mb == 0.0
        assert result[0].avg_document_size_bytes == 0
