"""
Unit tests for InsightCategoryBase.

Tests abstract base class functionality using a concrete test implementation.
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from src.services.insights.base import InsightCategoryBase
from src.services.insights.models import (
    InsightMetric,
    MetricExplanation,
    MetricStatus,
)

# ===== Concrete Test Implementation =====


class TestInsightCategory(InsightCategoryBase):
    """Concrete implementation for testing."""

    CATEGORY_ID = "test_category"
    CATEGORY_NAME = "Test Category"
    CATEGORY_ICON = "📊"
    CATEGORY_DESCRIPTION = "A test category"

    def get_metric_definitions(self) -> list[dict[str, Any]]:
        return [
            {"id": "metric1", "name": "Metric 1", "weight": 0.6},
            {"id": "metric2", "name": "Metric 2", "weight": 0.4},
        ]

    async def calculate_metrics(self) -> list[InsightMetric]:
        return [
            InsightMetric(
                id="metric1",
                name="Metric 1",
                score=75.0,
                status=MetricStatus.ELEVATED,
                explanation=MetricExplanation(
                    summary="Test metric 1",
                    detail="Detail",
                    methodology="Method",
                    historical_context="Context",
                    actionable_insight="Action",
                ),
            ),
            InsightMetric(
                id="metric2",
                name="Metric 2",
                score=50.0,
                status=MetricStatus.NORMAL,
                explanation=MetricExplanation(
                    summary="Test metric 2",
                    detail="Detail",
                    methodology="Method",
                    historical_context="Context",
                    actionable_insight="Action",
                ),
            ),
        ]

    def get_composite_weights(self) -> dict[str, float]:
        return {"metric1": 0.6, "metric2": 0.4}


# ===== Fixtures =====


@pytest.fixture
def mock_settings():
    """Mock Settings object."""
    settings = Mock()
    settings.cache_ttl_insights = 86400
    return settings


@pytest.fixture
def mock_redis_cache():
    """Mock RedisCache object."""
    cache = Mock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    cache.delete = AsyncMock(return_value=True)
    return cache


@pytest.fixture
def test_category(mock_settings, mock_redis_cache):
    """Create test category instance."""
    return TestInsightCategory(
        settings=mock_settings,
        redis_cache=mock_redis_cache,
    )


# ===== Property Tests =====


class TestProperties:
    """Test property methods."""

    def test_cache_key_prefix(self, test_category):
        """Test cache key prefix generation."""
        assert test_category.cache_key_prefix == "insights:test_category"

    def test_get_metadata(self, test_category):
        """Test metadata generation."""
        metadata = test_category.get_metadata()

        assert metadata.id == "test_category"
        assert metadata.name == "Test Category"
        assert metadata.icon == "📊"
        assert metadata.description == "A test category"
        assert metadata.metric_count == 2


# ===== get_category_data Tests =====


class TestGetCategoryData:
    """Test get_category_data method."""

    @pytest.mark.asyncio
    async def test_cache_hit(self, test_category, mock_redis_cache):
        """Test returning cached data."""
        cached_data = {
            "id": "test_category",
            "name": "Test Category",
            "icon": "📊",
            "description": "A test category",
            "metrics": [],
            "composite": None,
            "last_updated": datetime.now(UTC).isoformat(),
        }
        mock_redis_cache.get.return_value = cached_data

        result = await test_category.get_category_data()

        assert result.id == "test_category"
        mock_redis_cache.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_miss(self, test_category, mock_redis_cache):
        """Test calculating fresh data on cache miss."""
        mock_redis_cache.get.return_value = None

        result = await test_category.get_category_data()

        assert result.id == "test_category"
        assert len(result.metrics) == 2
        assert result.composite is not None
        mock_redis_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_force_refresh(self, test_category, mock_redis_cache):
        """Test force refresh bypasses cache."""
        cached_data = {"id": "test_category", "name": "Old Data"}
        mock_redis_cache.get.return_value = cached_data

        result = await test_category.get_category_data(force_refresh=True)

        # Should calculate fresh metrics, not return cached
        assert len(result.metrics) == 2
        mock_redis_cache.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_cache(self, mock_settings):
        """Test without Redis cache."""
        category = TestInsightCategory(settings=mock_settings, redis_cache=None)

        result = await category.get_category_data()

        assert result.id == "test_category"
        assert len(result.metrics) == 2


# ===== get_metric Tests =====


class TestGetMetric:
    """Test get_metric method."""

    @pytest.mark.asyncio
    async def test_get_existing_metric(self, test_category, mock_redis_cache):
        """Test getting an existing metric."""
        mock_redis_cache.get.return_value = None

        result = await test_category.get_metric("metric1")

        assert result is not None
        assert result.id == "metric1"
        assert result.name == "Metric 1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_metric(self, test_category, mock_redis_cache):
        """Test getting a metric that doesn't exist."""
        mock_redis_cache.get.return_value = None

        result = await test_category.get_metric("nonexistent")

        assert result is None


# ===== get_composite Tests =====


class TestGetComposite:
    """Test get_composite method."""

    @pytest.mark.asyncio
    async def test_get_composite_success(self, test_category, mock_redis_cache):
        """Test getting composite score."""
        mock_redis_cache.get.return_value = None

        result = await test_category.get_composite()

        assert result is not None
        # Composite: 75.0 * 0.6 + 50.0 * 0.4 = 45.0 + 20.0 = 65.0
        assert result.score == 65.0
        assert result.status == MetricStatus.ELEVATED


# ===== refresh Tests =====


class TestRefresh:
    """Test refresh method."""

    @pytest.mark.asyncio
    async def test_refresh_clears_cache(self, test_category, mock_redis_cache):
        """Test that refresh clears cache."""
        result = await test_category.refresh()

        mock_redis_cache.delete.assert_called_once_with("insights:test_category:full")
        assert result.id == "test_category"

    @pytest.mark.asyncio
    async def test_refresh_without_cache(self, mock_settings):
        """Test refresh without Redis cache."""
        category = TestInsightCategory(settings=mock_settings, redis_cache=None)

        result = await category.refresh()

        assert result.id == "test_category"


# ===== _calculate_composite Tests =====


class TestCalculateComposite:
    """Test _calculate_composite method."""

    def test_calculate_composite(self, test_category):
        """Test composite calculation."""
        metrics = [
            InsightMetric(
                id="metric1",
                name="Metric 1",
                score=80.0,
                status=MetricStatus.HIGH,
                explanation=MetricExplanation(
                    summary="Test",
                    detail="Detail",
                    methodology="Method",
                    historical_context="Context",
                    actionable_insight="Action",
                ),
            ),
            InsightMetric(
                id="metric2",
                name="Metric 2",
                score=40.0,
                status=MetricStatus.NORMAL,
                explanation=MetricExplanation(
                    summary="Test",
                    detail="Detail",
                    methodology="Method",
                    historical_context="Context",
                    actionable_insight="Action",
                ),
            ),
        ]

        composite = test_category._calculate_composite(metrics)

        # 80 * 0.6 + 40 * 0.4 = 48 + 16 = 64
        assert composite.score == 64.0
        assert composite.breakdown["metric1"] == 48.0
        assert composite.breakdown["metric2"] == 16.0


# ===== _generate_composite_interpretation Tests =====


class TestGenerateCompositeInterpretation:
    """Test _generate_composite_interpretation method."""

    def test_low_interpretation(self, test_category):
        """Test LOW status interpretation."""
        result = test_category._generate_composite_interpretation(
            20.0, MetricStatus.LOW
        )

        assert "low risk" in result.lower()
        assert "20.0" in result

    def test_normal_interpretation(self, test_category):
        """Test NORMAL status interpretation."""
        result = test_category._generate_composite_interpretation(
            45.0, MetricStatus.NORMAL
        )

        assert "normal" in result.lower()
        assert "45.0" in result

    def test_elevated_interpretation(self, test_category):
        """Test ELEVATED status interpretation."""
        result = test_category._generate_composite_interpretation(
            65.0, MetricStatus.ELEVATED
        )

        assert "elevated" in result.lower()
        assert "65.0" in result

    def test_high_interpretation(self, test_category):
        """Test HIGH status interpretation."""
        result = test_category._generate_composite_interpretation(
            85.0, MetricStatus.HIGH
        )

        assert "high risk" in result.lower()
        assert "85.0" in result


# ===== normalize_score Tests =====


class TestNormalizeScore:
    """Test normalize_score static method."""

    def test_normalize_middle(self):
        """Test normalizing a middle value."""
        result = InsightCategoryBase.normalize_score(50, 0, 100)
        assert result == 50.0

    def test_normalize_min(self):
        """Test normalizing minimum value."""
        result = InsightCategoryBase.normalize_score(0, 0, 100)
        assert result == 0.0

    def test_normalize_max(self):
        """Test normalizing maximum value."""
        result = InsightCategoryBase.normalize_score(100, 0, 100)
        assert result == 100.0

    def test_normalize_inverted(self):
        """Test inverted normalization."""
        result = InsightCategoryBase.normalize_score(25, 0, 100, invert=True)
        assert result == 75.0

    def test_normalize_clamp_high(self):
        """Test clamping values above max."""
        result = InsightCategoryBase.normalize_score(150, 0, 100)
        assert result == 100.0

    def test_normalize_clamp_low(self):
        """Test clamping values below min."""
        result = InsightCategoryBase.normalize_score(-50, 0, 100)
        assert result == 0.0

    def test_normalize_equal_min_max(self):
        """Test when min equals max."""
        result = InsightCategoryBase.normalize_score(50, 50, 50)
        assert result == 50.0

    def test_normalize_custom_range(self):
        """Test with custom min/max range."""
        result = InsightCategoryBase.normalize_score(15, 10, 20)
        assert result == 50.0
