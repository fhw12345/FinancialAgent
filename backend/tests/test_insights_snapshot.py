"""
Unit tests for InsightsSnapshotService.

Tests snapshot creation, persistence, and retrieval.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from src.services.insights.models import (
    CompositeScore,
    InsightMetric,
    MetricExplanation,
    MetricStatus,
)
from src.services.insights.snapshot_service import (
    InsightsSnapshotService,
    _get_status_from_score,
)

# ===== Helper Function Tests =====


class TestGetStatusFromScore:
    """Test _get_status_from_score helper."""

    def test_low_score(self):
        """Test LOW status for score < 25."""
        assert _get_status_from_score(0) == "low"
        assert _get_status_from_score(10) == "low"
        assert _get_status_from_score(24) == "low"

    def test_normal_score(self):
        """Test NORMAL status for 25 <= score < 50."""
        assert _get_status_from_score(25) == "normal"
        assert _get_status_from_score(35) == "normal"
        assert _get_status_from_score(49) == "normal"

    def test_elevated_score(self):
        """Test ELEVATED status for 50 <= score < 75."""
        assert _get_status_from_score(50) == "elevated"
        assert _get_status_from_score(60) == "elevated"
        assert _get_status_from_score(74) == "elevated"

    def test_high_score(self):
        """Test HIGH status for score >= 75."""
        assert _get_status_from_score(75) == "high"
        assert _get_status_from_score(90) == "high"
        assert _get_status_from_score(100) == "high"


# ===== Fixtures =====


@pytest.fixture
def mock_settings():
    """Mock Settings object."""
    settings = Mock()
    settings.cache_ttl_insights = 86400
    settings.fred_api_key = "test_key"
    return settings


@pytest.fixture
def mock_mongodb():
    """Mock MongoDB connection."""
    mongodb = Mock()
    mock_collection = MagicMock()
    mock_collection.create_index = AsyncMock()
    mock_collection.update_one = AsyncMock()
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_collection.find = MagicMock()
    mongodb.get_collection = Mock(return_value=mock_collection)
    return mongodb


@pytest.fixture
def mock_redis_cache():
    """Mock RedisCache."""
    cache = Mock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    return cache


@pytest.fixture
def mock_data_manager():
    """Mock DataManager."""
    dm = Mock()

    # Create mock SharedContext
    mock_context = Mock()
    mock_context.ohlcv = {"NVDA": Mock()}
    mock_context.treasury = {"treasury_2y": Mock()}
    mock_context.news = [Mock()]
    mock_context.ipo = [Mock()]
    mock_context.errors = {}

    dm.prefetch_shared = AsyncMock(return_value=mock_context)
    return dm


@pytest.fixture
def mock_registry():
    """Mock InsightsCategoryRegistry."""
    registry = Mock()

    # Create mock category instance
    mock_category = Mock()
    mock_category.get_category_data = AsyncMock(
        return_value=Mock(
            metrics=[
                InsightMetric(
                    id="test_metric",
                    name="Test Metric",
                    score=65.0,
                    status=MetricStatus.ELEVATED,
                    explanation=MetricExplanation(
                        summary="Test",
                        detail="Detail",
                        methodology="Method",
                        historical_context="Context",
                        actionable_insight="Action",
                    ),
                )
            ],
            composite=CompositeScore(
                score=65.0,
                status=MetricStatus.ELEVATED,
                weights={"test_metric": 1.0},
                breakdown={"test_metric": 65.0},
                interpretation="Test interpretation",
            ),
        )
    )

    registry.get_category_instance = Mock(return_value=mock_category)
    return registry


@pytest.fixture
def snapshot_service(
    mock_mongodb, mock_redis_cache, mock_data_manager, mock_settings, mock_registry
):
    """Create InsightsSnapshotService instance."""
    service = InsightsSnapshotService(
        mongodb=mock_mongodb,
        redis_cache=mock_redis_cache,
        data_manager=mock_data_manager,
        settings=mock_settings,
        registry=mock_registry,
    )
    return service


# ===== Initialization Tests =====


class TestSnapshotServiceInit:
    """Test InsightsSnapshotService initialization."""

    def test_init_with_registry(
        self,
        mock_mongodb,
        mock_redis_cache,
        mock_data_manager,
        mock_settings,
        mock_registry,
    ):
        """Test initialization with provided registry."""
        service = InsightsSnapshotService(
            mongodb=mock_mongodb,
            redis_cache=mock_redis_cache,
            data_manager=mock_data_manager,
            settings=mock_settings,
            registry=mock_registry,
        )

        assert service._registry is mock_registry

    def test_init_creates_registry_lazily(
        self, mock_mongodb, mock_redis_cache, mock_data_manager, mock_settings
    ):
        """Test registry is created lazily when not provided."""
        service = InsightsSnapshotService(
            mongodb=mock_mongodb,
            redis_cache=mock_redis_cache,
            data_manager=mock_data_manager,
            settings=mock_settings,
            registry=None,
        )

        assert service._registry is None


# ===== ensure_indexes Tests =====


class TestEnsureIndexes:
    """Test ensure_indexes method."""

    @pytest.mark.asyncio
    async def test_creates_index(self, snapshot_service, mock_mongodb):
        """Test index creation."""
        await snapshot_service.ensure_indexes()

        collection = mock_mongodb.get_collection.return_value
        collection.create_index.assert_called_once()


# ===== create_snapshot Tests =====


class TestCreateSnapshot:
    """Test create_snapshot method."""

    @pytest.mark.asyncio
    async def test_create_snapshot_success(self, snapshot_service, mock_registry):
        """Test successful snapshot creation."""
        result = await snapshot_service.create_snapshot(
            category_id="ai_sector_risk",
            run_id="test_run",
        )

        assert result["status"] == "success"
        assert result["category_id"] == "ai_sector_risk"
        assert result["run_id"] == "test_run"
        assert "composite_score" in result
        assert "metric_count" in result
        assert "timing" in result

    @pytest.mark.asyncio
    async def test_create_snapshot_category_not_found(
        self, snapshot_service, mock_registry
    ):
        """Test snapshot with non-existent category."""
        mock_registry.get_category_instance.return_value = None

        result = await snapshot_service.create_snapshot(
            category_id="nonexistent",
        )

        assert result["status"] == "error"
        assert "Category not found" in result["error"]

    @pytest.mark.asyncio
    async def test_create_snapshot_generates_run_id(self, snapshot_service):
        """Test snapshot generates run_id if not provided."""
        result = await snapshot_service.create_snapshot(category_id="ai_sector_risk")

        assert result["run_id"].startswith("snapshot_")

    @pytest.mark.asyncio
    async def test_create_snapshot_rejects_missing_composite(
        self, snapshot_service, mock_registry
    ):
        """Metrics without a composite score are an invalid category contract."""
        mock_category = mock_registry.get_category_instance.return_value
        mock_category.get_category_data.return_value.composite = None

        result = await snapshot_service.create_snapshot(category_id="ai_sector_risk")

        assert result["status"] == "error"
        assert "without a composite score" in result["error"]

    @pytest.mark.asyncio
    async def test_create_snapshot_handles_exception(
        self, snapshot_service, mock_registry
    ):
        """Test snapshot handles exceptions."""
        mock_category = mock_registry.get_category_instance.return_value
        mock_category.get_category_data.side_effect = Exception("API Error")

        result = await snapshot_service.create_snapshot(category_id="ai_sector_risk")

        assert result["status"] == "error"
        assert "API Error" in result["error"]
        assert "timing" in result


# ===== _prefetch_shared_data Tests =====


class TestPrefetchSharedData:
    """Test _prefetch_shared_data method."""

    @pytest.mark.asyncio
    async def test_prefetch_success(self, snapshot_service, mock_data_manager):
        """Test successful data prefetch."""
        result = await snapshot_service._prefetch_shared_data()

        assert "ohlcv" in result
        assert "treasury" in result
        assert "news" in result
        assert "ipo" in result
        assert "errors" in result
        mock_data_manager.prefetch_shared.assert_awaited_once_with(
            symbols=["NVDA", "MSFT", "AMD", "PLTR"],
            treasury_maturities=["2y", "10y"],
            include_news=True,
            include_ipo=True,
        )

    @pytest.mark.asyncio
    async def test_prefetch_does_not_hide_programming_errors(
        self, snapshot_service, mock_data_manager
    ):
        """Programming errors must not look like provider degradation."""
        mock_data_manager.prefetch_shared.side_effect = TypeError("bad contract")

        with pytest.raises(TypeError, match="bad contract"):
            await snapshot_service._prefetch_shared_data()


# ===== _persist_snapshot Tests =====


class TestPersistSnapshot:
    """Test _persist_snapshot method."""

    @pytest.mark.asyncio
    async def test_persist_to_mongodb_and_redis(
        self, snapshot_service, mock_mongodb, mock_redis_cache
    ):
        """Test snapshot is persisted to both MongoDB and Redis."""
        metrics = [
            InsightMetric(
                id="metric1",
                name="Metric 1",
                score=50.0,
                status=MetricStatus.NORMAL,
                explanation=MetricExplanation(
                    summary="Test",
                    detail="Detail",
                    methodology="Method",
                    historical_context="Context",
                    actionable_insight="Action",
                ),
            )
        ]
        composite = CompositeScore(
            score=50.0,
            status=MetricStatus.NORMAL,
            weights={"metric1": 1.0},
            breakdown={"metric1": 50.0},
            interpretation="Normal",
        )

        result = await snapshot_service._persist_snapshot(
            category_id="ai_sector_risk",
            metrics=metrics,
            composite=composite,
        )

        # Check MongoDB update
        collection = mock_mongodb.get_collection.return_value
        collection.update_one.assert_called_once()

        # Check Redis set
        mock_redis_cache.set.assert_called_once()

        # Check result structure
        assert result["category_id"] == "ai_sector_risk"
        assert result["composite_score"] == 50.0


# ===== get_latest_snapshot Tests =====


class TestGetLatestSnapshot:
    """Test get_latest_snapshot method."""

    @pytest.mark.asyncio
    async def test_cache_hit(self, snapshot_service, mock_redis_cache):
        """Test returns cached data."""
        cached_data = {
            "category_id": "ai_sector_risk",
            "composite_score": 65.0,
        }
        mock_redis_cache.get.return_value = cached_data

        result = await snapshot_service.get_latest_snapshot("ai_sector_risk")

        assert result == cached_data
        mock_redis_cache.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss_mongodb_hit(
        self, snapshot_service, mock_redis_cache, mock_mongodb
    ):
        """Test falls back to MongoDB on cache miss."""
        mock_redis_cache.get.return_value = None

        mongo_doc = {
            "_id": "mongo_id",
            "category_id": "ai_sector_risk",
            "date": datetime.now(UTC),
            "composite_score": 65.0,
        }
        collection = mock_mongodb.get_collection.return_value
        collection.find_one.return_value = mongo_doc

        result = await snapshot_service.get_latest_snapshot("ai_sector_risk")

        assert result["category_id"] == "ai_sector_risk"
        assert "_id" not in result  # Should be removed

    @pytest.mark.asyncio
    async def test_cache_miss_mongodb_miss(
        self, snapshot_service, mock_redis_cache, mock_mongodb
    ):
        """Test returns None when no data exists."""
        mock_redis_cache.get.return_value = None
        collection = mock_mongodb.get_collection.return_value
        collection.find_one.return_value = None

        result = await snapshot_service.get_latest_snapshot("ai_sector_risk")

        assert result is None


# ===== get_trend Tests =====


class TestGetTrend:
    """Test get_trend method."""

    @pytest.mark.asyncio
    async def test_get_trend_success(self, snapshot_service, mock_mongodb):
        """Test getting trend data."""
        # Create mock async iterator
        docs = [
            {
                "_id": "id1",
                "category_id": "ai_sector_risk",
                "date": datetime.now(UTC),
                "composite_score": 65.0,
            },
            {
                "_id": "id2",
                "category_id": "ai_sector_risk",
                "date": datetime.now(UTC),
                "composite_score": 60.0,
            },
        ]

        # Mock the async iterator
        class MockCursor:
            def __init__(self, docs):
                self.docs = docs
                self.index = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.index >= len(self.docs):
                    raise StopAsyncIteration
                doc = self.docs[self.index]
                self.index += 1
                return doc

        collection = mock_mongodb.get_collection.return_value
        collection.find.return_value = MockCursor(docs)

        result = await snapshot_service.get_trend(category_id="ai_sector_risk", days=30)

        assert len(result) == 2
        assert "_id" not in result[0]
        assert "date" in result[0]

    @pytest.mark.asyncio
    async def test_get_trend_empty(self, snapshot_service, mock_mongodb):
        """Test getting trend with no data."""

        class MockCursor:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        collection = mock_mongodb.get_collection.return_value
        collection.find.return_value = MockCursor()

        result = await snapshot_service.get_trend(category_id="ai_sector_risk", days=30)

        assert result == []
