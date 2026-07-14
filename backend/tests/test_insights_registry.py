"""
Unit tests for InsightsCategoryRegistry.

Tests category registration, instantiation, and data retrieval.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.insights.base import InsightCategoryBase
from src.services.insights.models import (
    CategoryMetadata,
    InsightCategory,
    InsightMetric,
)
from src.services.insights.registry import (
    InsightsCategoryRegistry,
    _category_registry,
    get_registered_categories,
    register_category,
)

# ===== Fixtures =====


@pytest.fixture
def mock_settings():
    """Mock Settings"""
    settings = Mock()
    settings.redis_cache_ttl_seconds = 86400
    return settings


@pytest.fixture
def mock_redis_cache():
    """Mock RedisCache"""
    cache = Mock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    return cache


@pytest.fixture
def mock_category_metadata():
    """Sample category metadata"""
    return CategoryMetadata(
        id="test_category",
        name="Test Category",
        description="A test category",
        icon="📊",
        metric_count=3,
    )


@pytest.fixture
def mock_insight_category():
    """Sample insight category data"""
    from src.services.insights.models import (
        MetricExplanation,
        MetricStatus,
        ThresholdConfig,
    )

    return InsightCategory(
        id="test_category",
        name="Test Category",
        description="A test category",
        icon="📊",
        last_updated=datetime.now(UTC),
        metrics=[
            InsightMetric(
                id="test_metric",
                name="Test Metric",
                score=75.5,
                status=MetricStatus.ELEVATED,
                explanation=MetricExplanation(
                    summary="Test summary",
                    detail="Test detail",
                    methodology="Test methodology",
                    historical_context="Test context",
                    actionable_insight="Test insight",
                    thresholds=ThresholdConfig(),
                ),
            )
        ],
    )


# ===== register_category Tests =====


class TestRegisterCategory:
    """Test register_category decorator"""

    def test_register_category_success(self):
        """Test successful category registration"""
        # Clear registry for this test
        original_registry = _category_registry.copy()
        _category_registry.clear()

        try:

            @register_category
            class TestCategory(InsightCategoryBase):
                CATEGORY_ID = "test_register"
                CATEGORY_NAME = "Test"
                CATEGORY_DESCRIPTION = "Test category"

            assert "test_register" in _category_registry
            assert _category_registry["test_register"] == TestCategory
        finally:
            # Restore registry
            _category_registry.clear()
            _category_registry.update(original_registry)

    def test_register_category_no_id(self):
        """Test registration fails without CATEGORY_ID"""
        with pytest.raises(ValueError) as exc_info:

            @register_category
            class BadCategory(InsightCategoryBase):
                CATEGORY_ID = ""  # Empty ID

        assert "must define CATEGORY_ID" in str(exc_info.value)


class TestGetRegisteredCategories:
    """Test get_registered_categories function"""

    def test_returns_copy(self):
        """Test returns a copy of registry"""
        result = get_registered_categories()
        # Modifying returned dict shouldn't affect original
        result["fake"] = Mock()
        assert "fake" not in _category_registry


# ===== InsightsCategoryRegistry Tests =====


class TestInsightsCategoryRegistry:
    """Test InsightsCategoryRegistry class"""

    def test_init(self, mock_settings, mock_redis_cache):
        """Test registry initialization"""
        with patch("src.services.insights.registry._category_registry", {}):
            with patch.object(
                InsightsCategoryRegistry, "_load_categories", return_value=None
            ):
                registry = InsightsCategoryRegistry(
                    settings=mock_settings,
                    redis_cache=mock_redis_cache,
                )

                assert registry.settings == mock_settings
                assert registry.redis_cache == mock_redis_cache

    def test_list_categories(
        self, mock_settings, mock_redis_cache, mock_category_metadata
    ):
        """Test listing categories"""
        with patch.object(
            InsightsCategoryRegistry, "_load_categories", return_value=None
        ):
            registry = InsightsCategoryRegistry(
                settings=mock_settings,
                redis_cache=mock_redis_cache,
            )

            # Add mock instance
            mock_instance = Mock()
            mock_instance.get_metadata.return_value = mock_category_metadata
            registry._instances["test_category"] = mock_instance

            result = registry.list_categories()

            assert len(result) == 1
            assert result[0].id == "test_category"

    def test_get_category_instance_found(self, mock_settings, mock_redis_cache):
        """Test getting existing category instance"""
        with patch.object(
            InsightsCategoryRegistry, "_load_categories", return_value=None
        ):
            registry = InsightsCategoryRegistry(
                settings=mock_settings,
                redis_cache=mock_redis_cache,
            )

            mock_instance = Mock()
            registry._instances["test_category"] = mock_instance

            result = registry.get_category_instance("test_category")

            assert result == mock_instance

    def test_get_category_instance_not_found(self, mock_settings, mock_redis_cache):
        """Test getting non-existent category instance"""
        with patch.object(
            InsightsCategoryRegistry, "_load_categories", return_value=None
        ):
            registry = InsightsCategoryRegistry(
                settings=mock_settings,
                redis_cache=mock_redis_cache,
            )

            result = registry.get_category_instance("nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_category_data_success(
        self, mock_settings, mock_redis_cache, mock_insight_category
    ):
        """Test getting category data"""
        with patch.object(
            InsightsCategoryRegistry, "_load_categories", return_value=None
        ):
            registry = InsightsCategoryRegistry(
                settings=mock_settings,
                redis_cache=mock_redis_cache,
            )

            mock_instance = Mock()
            mock_instance.get_category_data = AsyncMock(
                return_value=mock_insight_category
            )
            registry._instances["test_category"] = mock_instance

            result = await registry.get_category_data("test_category")

            assert result.id == "test_category"
            mock_instance.get_category_data.assert_called_once_with(force_refresh=False)

    @pytest.mark.asyncio
    async def test_get_category_data_not_found(self, mock_settings, mock_redis_cache):
        """Test getting data for non-existent category"""
        with patch.object(
            InsightsCategoryRegistry, "_load_categories", return_value=None
        ):
            registry = InsightsCategoryRegistry(
                settings=mock_settings,
                redis_cache=mock_redis_cache,
            )

            result = await registry.get_category_data("nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_all_categories_data(
        self, mock_settings, mock_redis_cache, mock_insight_category
    ):
        """Test getting data for all categories"""
        with patch.object(
            InsightsCategoryRegistry, "_load_categories", return_value=None
        ):
            registry = InsightsCategoryRegistry(
                settings=mock_settings,
                redis_cache=mock_redis_cache,
            )

            mock_instance1 = Mock()
            mock_instance1.get_category_data = AsyncMock(
                return_value=mock_insight_category
            )
            mock_instance2 = Mock()
            mock_instance2.get_category_data = AsyncMock(return_value=None)

            registry._instances["cat1"] = mock_instance1
            registry._instances["cat2"] = mock_instance2

            result = await registry.get_all_categories_data()

            assert len(result) == 1  # Only one returned data

    @pytest.mark.asyncio
    async def test_refresh_category_success(
        self, mock_settings, mock_redis_cache, mock_insight_category
    ):
        """Test refreshing a category"""
        with patch.object(
            InsightsCategoryRegistry, "_load_categories", return_value=None
        ):
            registry = InsightsCategoryRegistry(
                settings=mock_settings,
                redis_cache=mock_redis_cache,
            )

            mock_instance = Mock()
            mock_instance.refresh = AsyncMock(return_value=mock_insight_category)
            registry._instances["test_category"] = mock_instance

            result = await registry.refresh_category("test_category")

            assert result == mock_insight_category
            mock_instance.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_category_not_found(self, mock_settings, mock_redis_cache):
        """Test refreshing non-existent category"""
        with patch.object(
            InsightsCategoryRegistry, "_load_categories", return_value=None
        ):
            registry = InsightsCategoryRegistry(
                settings=mock_settings,
                redis_cache=mock_redis_cache,
            )

            result = await registry.refresh_category("nonexistent")

            assert result is None

    @pytest.mark.asyncio
    async def test_refresh_all(
        self, mock_settings, mock_redis_cache, mock_insight_category
    ):
        """Test refreshing all categories"""
        with patch.object(
            InsightsCategoryRegistry, "_load_categories", return_value=None
        ):
            registry = InsightsCategoryRegistry(
                settings=mock_settings,
                redis_cache=mock_redis_cache,
            )

            mock_instance1 = Mock()
            mock_instance1.refresh = AsyncMock(return_value=mock_insight_category)
            mock_instance2 = Mock()
            mock_instance2.refresh = AsyncMock(side_effect=Exception("Refresh error"))

            registry._instances["cat1"] = mock_instance1
            registry._instances["cat2"] = mock_instance2

            result = await registry.refresh_all()

            # Only one succeeded
            assert len(result) == 1

    def test_category_count(self, mock_settings, mock_redis_cache):
        """Test category_count property"""
        with patch.object(
            InsightsCategoryRegistry, "_load_categories", return_value=None
        ):
            registry = InsightsCategoryRegistry(
                settings=mock_settings,
                redis_cache=mock_redis_cache,
            )

            registry._instances["cat1"] = Mock()
            registry._instances["cat2"] = Mock()

            assert registry.category_count == 2

    def test_category_ids(self, mock_settings, mock_redis_cache):
        """Test category_ids property"""
        with patch.object(
            InsightsCategoryRegistry, "_load_categories", return_value=None
        ):
            registry = InsightsCategoryRegistry(
                settings=mock_settings,
                redis_cache=mock_redis_cache,
            )

            registry._instances["cat1"] = Mock()
            registry._instances["cat2"] = Mock()

            assert set(registry.category_ids) == {"cat1", "cat2"}
