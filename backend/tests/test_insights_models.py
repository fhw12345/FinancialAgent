"""
Unit tests for Insights models.

Tests Pydantic models and business logic.
"""

from datetime import UTC, datetime

import pytest

from src.services.insights.models import (
    CategoryMetadata,
    CompositeScore,
    InsightCategory,
    InsightMetric,
    MetricExplanation,
    MetricStatus,
    ThresholdConfig,
)

# ===== ThresholdConfig Tests =====


class TestThresholdConfig:
    """Test ThresholdConfig model"""

    def test_default_thresholds(self):
        """Test default threshold values"""
        config = ThresholdConfig()
        assert config.low == 25
        assert config.normal == 50
        assert config.elevated == 75
        assert config.high == 100

    def test_custom_thresholds(self):
        """Test custom threshold values"""
        config = ThresholdConfig(low=20, normal=40, elevated=60, high=80)
        assert config.low == 20
        assert config.normal == 40

    def test_get_status_low(self):
        """Test LOW status determination"""
        config = ThresholdConfig()
        assert config.get_status(10) == MetricStatus.LOW
        assert config.get_status(0) == MetricStatus.LOW
        assert config.get_status(24) == MetricStatus.LOW

    def test_get_status_normal(self):
        """Test NORMAL status determination"""
        config = ThresholdConfig()
        assert config.get_status(25) == MetricStatus.NORMAL
        assert config.get_status(30) == MetricStatus.NORMAL
        assert config.get_status(49) == MetricStatus.NORMAL

    def test_get_status_elevated(self):
        """Test ELEVATED status determination"""
        config = ThresholdConfig()
        assert config.get_status(50) == MetricStatus.ELEVATED
        assert config.get_status(60) == MetricStatus.ELEVATED
        assert config.get_status(74) == MetricStatus.ELEVATED

    def test_get_status_high(self):
        """Test HIGH status determination"""
        config = ThresholdConfig()
        assert config.get_status(75) == MetricStatus.HIGH
        assert config.get_status(90) == MetricStatus.HIGH
        assert config.get_status(100) == MetricStatus.HIGH


# ===== MetricStatus Tests =====


class TestMetricStatus:
    """Test MetricStatus enum"""

    def test_status_values(self):
        """Test enum values"""
        assert MetricStatus.LOW == "low"
        assert MetricStatus.NORMAL == "normal"
        assert MetricStatus.ELEVATED == "elevated"
        assert MetricStatus.HIGH == "high"


# ===== MetricExplanation Tests =====


class TestMetricExplanation:
    """Test MetricExplanation model"""

    def test_create_explanation(self):
        """Test creating explanation"""
        explanation = MetricExplanation(
            summary="Test summary",
            detail="Detailed explanation here",
            methodology="Calculated using XYZ method",
            historical_context="Last seen at this level in 2024",
            actionable_insight="Consider hedging strategies",
        )

        assert explanation.summary == "Test summary"
        assert explanation.formula is None  # Optional field
        assert explanation.thresholds is not None

    def test_explanation_with_formula(self):
        """Test explanation with formula"""
        explanation = MetricExplanation(
            summary="Test",
            detail="Detail",
            methodology="Method",
            formula="(P1 + P2) / 2",
            historical_context="Context",
            actionable_insight="Action",
        )

        assert explanation.formula == "(P1 + P2) / 2"

    def test_explanation_with_custom_thresholds(self):
        """Test explanation with custom thresholds"""
        custom_thresholds = ThresholdConfig(low=10, normal=30)
        explanation = MetricExplanation(
            summary="Test",
            detail="Detail",
            methodology="Method",
            historical_context="Context",
            actionable_insight="Action",
            thresholds=custom_thresholds,
        )

        assert explanation.thresholds.low == 10
        assert explanation.thresholds.normal == 30


# ===== InsightMetric Tests =====


class TestInsightMetric:
    """Test InsightMetric model"""

    @pytest.fixture
    def sample_explanation(self):
        """Sample explanation for tests"""
        return MetricExplanation(
            summary="Test",
            detail="Detail",
            methodology="Method",
            historical_context="Context",
            actionable_insight="Action",
        )

    def test_create_metric(self, sample_explanation):
        """Test creating metric"""
        metric = InsightMetric(
            id="test_metric",
            name="Test Metric",
            score=75.5,
            status=MetricStatus.ELEVATED,
            explanation=sample_explanation,
        )

        assert metric.id == "test_metric"
        assert metric.score == 75.5
        assert metric.status == MetricStatus.ELEVATED
        assert metric.data_sources == []  # Default
        assert metric.raw_data == {}  # Default

    def test_metric_with_data_sources(self, sample_explanation):
        """Test metric with data sources"""
        metric = InsightMetric(
            id="test",
            name="Test",
            score=50,
            status=MetricStatus.NORMAL,
            explanation=sample_explanation,
            data_sources=["Alpha Vantage", "FRED"],
        )

        assert len(metric.data_sources) == 2

    def test_metric_score_validation(self, sample_explanation):
        """Test score must be 0-100"""
        with pytest.raises(ValueError):
            InsightMetric(
                id="test",
                name="Test",
                score=150,  # Invalid - over 100
                status=MetricStatus.HIGH,
                explanation=sample_explanation,
            )

        with pytest.raises(ValueError):
            InsightMetric(
                id="test",
                name="Test",
                score=-10,  # Invalid - negative
                status=MetricStatus.LOW,
                explanation=sample_explanation,
            )


# ===== CompositeScore Tests =====


class TestCompositeScore:
    """Test CompositeScore model"""

    def test_create_composite_score(self):
        """Test creating composite score"""
        composite = CompositeScore(
            score=65.5,
            status=MetricStatus.ELEVATED,
            weights={"metric1": 0.6, "metric2": 0.4},
            breakdown={"metric1": 40.0, "metric2": 25.5},
            interpretation="Overall elevated risk",
        )

        assert composite.score == 65.5
        assert composite.status == MetricStatus.ELEVATED
        assert composite.weights["metric1"] == 0.6
        assert composite.breakdown["metric2"] == 25.5


# ===== InsightCategory Tests =====


class TestInsightCategory:
    """Test InsightCategory model"""

    @pytest.fixture
    def sample_metric(self):
        """Sample metric for tests"""
        return InsightMetric(
            id="test_metric",
            name="Test Metric",
            score=50,
            status=MetricStatus.NORMAL,
            explanation=MetricExplanation(
                summary="Test",
                detail="Detail",
                methodology="Method",
                historical_context="Context",
                actionable_insight="Action",
            ),
        )

    def test_create_category(self, sample_metric):
        """Test creating category"""
        category = InsightCategory(
            id="test_category",
            name="Test Category",
            icon="📊",
            description="A test category",
            metrics=[sample_metric],
        )

        assert category.id == "test_category"
        assert category.icon == "📊"
        assert len(category.metrics) == 1
        assert category.composite is None

    def test_category_with_composite(self, sample_metric):
        """Test category with composite score"""
        composite = CompositeScore(
            score=50,
            status=MetricStatus.NORMAL,
            weights={"test_metric": 1.0},
            breakdown={"test_metric": 50},
            interpretation="Normal levels",
        )

        category = InsightCategory(
            id="test",
            name="Test",
            icon="📈",
            description="Test",
            metrics=[sample_metric],
            composite=composite,
        )

        assert category.composite.score == 50

    def test_category_empty_metrics(self):
        """Test category with no metrics"""
        category = InsightCategory(
            id="empty",
            name="Empty",
            icon="⚠️",
            description="Empty category",
        )

        assert category.metrics == []


# ===== CategoryMetadata Tests =====


class TestCategoryMetadata:
    """Test CategoryMetadata model"""

    def test_create_metadata(self):
        """Test creating metadata"""
        metadata = CategoryMetadata(
            id="test",
            name="Test Category",
            icon="📊",
            description="A test category",
            metric_count=5,
        )

        assert metadata.id == "test"
        assert metadata.metric_count == 5
        assert metadata.last_updated is None

    def test_metadata_with_timestamp(self):
        """Test metadata with last_updated"""
        now = datetime.now(UTC)
        metadata = CategoryMetadata(
            id="test",
            name="Test",
            icon="📊",
            description="Test",
            metric_count=3,
            last_updated=now,
        )

        assert metadata.last_updated == now
