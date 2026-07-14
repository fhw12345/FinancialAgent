"""Abstract base class for insight categories.

All insight categories must inherit from InsightCategoryBase
and implement the required methods. This enables the plugin
architecture where new categories can be added by creating
a single file in the categories/ directory.
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import structlog

from ...core.config import Settings
from ...database.redis import RedisCache
from .models import (
    CategoryMetadata,
    CompositeScore,
    InsightCategory,
    InsightMetric,
    MetricStatus,
    ThresholdConfig,
)

logger = structlog.get_logger()


class InsightCategoryBase(ABC):
    """Abstract base class for all insight categories.

    To create a new category:
    1. Create a new file in categories/ (e.g., sector_rotation.py)
    2. Inherit from InsightCategoryBase
    3. Implement all abstract methods
    4. The registry will auto-discover your category on startup

    Example:
        class SectorRotationCategory(InsightCategoryBase):
            CATEGORY_ID = "sector_rotation"
            CATEGORY_NAME = "Sector Rotation"
            CATEGORY_ICON = "🏭"
            CATEGORY_DESCRIPTION = "Tracks sector rotation patterns..."

            async def calculate_metrics(self) -> list[InsightMetric]:
                # Implementation here
                pass
    """

    # Subclasses must override these class attributes
    CATEGORY_ID: str = ""
    CATEGORY_NAME: str = ""
    CATEGORY_ICON: str = ""
    CATEGORY_DESCRIPTION: str = ""

    # Default cache TTL for calculated metrics (uses settings.cache_ttl_insights)
    # This class attribute is kept for backward compatibility but settings takes precedence
    CACHE_TTL_SECONDS: int = 86400

    def __init__(
        self,
        settings: Settings,
        redis_cache: RedisCache | None = None,
        market_service: Any | None = None,
        fred_service: Any | None = None,
    ) -> None:
        """Initialize category with dependencies.

        Args:
            settings: Application settings with API keys
            redis_cache: Optional Redis cache for caching results
            market_service: AlphaVantageMarketDataService for data fetching
            fred_service: FREDService for liquidity metrics (SOFR, EFFR, RRP)
        """
        self.settings = settings
        self.redis_cache = redis_cache
        self.market_service = market_service
        self.fred_service = fred_service

    @property
    def cache_key_prefix(self) -> str:
        """Cache key prefix for this category."""
        return f"insights:{self.CATEGORY_ID}"

    def get_metadata(self) -> CategoryMetadata:
        """Get lightweight category metadata for listing."""
        return CategoryMetadata(
            id=self.CATEGORY_ID,
            name=self.CATEGORY_NAME,
            icon=self.CATEGORY_ICON,
            description=self.CATEGORY_DESCRIPTION,
            metric_count=len(self.get_metric_definitions()),
        )

    @abstractmethod
    def get_metric_definitions(self) -> list[dict[str, Any]]:
        """Return metric definitions for this category.

        Each definition should include:
        - id: Unique metric identifier
        - name: Display name
        - weight: Weight in composite score (0.0-1.0)
        - data_sources: List of Alpha Vantage endpoints used

        Returns:
            List of metric definition dictionaries
        """
        ...

    @abstractmethod
    async def calculate_metrics(self) -> list[InsightMetric]:
        """Calculate all metrics for this category.

        This is the main calculation method that each category
        must implement. It should:
        1. Fetch required data from Alpha Vantage
        2. Calculate each metric score (0-100)
        3. Generate explanations for each metric
        4. Return list of InsightMetric objects

        Returns:
            List of calculated InsightMetric objects
        """
        ...

    @abstractmethod
    def get_composite_weights(self) -> dict[str, float]:
        """Return weight for each metric in composite score.

        Weights should sum to 1.0 (100%).

        Returns:
            Dict mapping metric_id to weight (0.0-1.0)
        """
        ...

    async def get_category_data(self, force_refresh: bool = False) -> InsightCategory:
        """Get complete category data with metrics and composite.

        Uses caching to reduce API calls. Set force_refresh=True
        to bypass cache and recalculate.

        Args:
            force_refresh: If True, bypass cache and recalculate

        Returns:
            Complete InsightCategory with all metrics
        """
        cache_key = f"{self.cache_key_prefix}:full"

        # Check cache unless force refresh
        if not force_refresh and self.redis_cache:
            cached = await self.redis_cache.get(cache_key)
            if cached:
                logger.info(
                    "Category cache HIT",
                    category_id=self.CATEGORY_ID,
                    cache_key=cache_key,
                )
                return InsightCategory.model_validate(cached)

            logger.info(
                "Category cache MISS",
                category_id=self.CATEGORY_ID,
                cache_key=cache_key,
            )

        # Calculate fresh metrics
        metrics = await self.calculate_metrics()
        composite = self._calculate_composite(metrics)

        category = InsightCategory(
            id=self.CATEGORY_ID,
            name=self.CATEGORY_NAME,
            icon=self.CATEGORY_ICON,
            description=self.CATEGORY_DESCRIPTION,
            metrics=metrics,
            composite=composite,
            last_updated=datetime.now(UTC),
        )

        # Cache result using centralized settings TTL
        if self.redis_cache:
            cache_ttl = self.settings.cache_ttl_insights
            await self.redis_cache.set(
                cache_key,
                category.model_dump(mode="json"),
                ttl_seconds=cache_ttl,
            )
            logger.info(
                "Category cached",
                category_id=self.CATEGORY_ID,
                cache_key=cache_key,
                ttl_seconds=cache_ttl,
            )

        return category

    async def get_metric(self, metric_id: str) -> InsightMetric | None:
        """Get a single metric by ID.

        Args:
            metric_id: The metric identifier

        Returns:
            InsightMetric if found, None otherwise
        """
        category = await self.get_category_data()
        for metric in category.metrics:
            if metric.id == metric_id:
                return metric
        return None

    async def get_composite(self) -> CompositeScore:
        """Get just the composite score.

        Returns:
            CompositeScore for this category
        """
        category = await self.get_category_data()
        if category.composite is None:
            raise ValueError(f"Category {self.CATEGORY_ID} has no composite score")
        return category.composite

    async def refresh(self) -> InsightCategory:
        """Force refresh all metrics and clear cache.

        Returns:
            Fresh InsightCategory data
        """
        # Clear cache
        if self.redis_cache:
            cache_key = f"{self.cache_key_prefix}:full"
            await self.redis_cache.delete(cache_key)
            logger.info(
                "Category cache cleared",
                category_id=self.CATEGORY_ID,
            )

        return await self.get_category_data(force_refresh=True)

    def _calculate_composite(self, metrics: list[InsightMetric]) -> CompositeScore:
        """Calculate weighted composite score from metrics.

        Args:
            metrics: List of calculated metrics

        Returns:
            CompositeScore with weighted average
        """
        weights = self.get_composite_weights()
        breakdown: dict[str, float] = {}
        total_score = 0.0

        for metric in metrics:
            weight = weights.get(metric.id, 0.0)
            contribution = metric.score * weight
            breakdown[metric.id] = round(contribution, 2)
            total_score += contribution

        final_score = round(total_score, 2)

        # Determine status using default thresholds
        thresholds = ThresholdConfig()
        status = thresholds.get_status(final_score)

        # Generate interpretation
        interpretation = self._generate_composite_interpretation(final_score, status)

        return CompositeScore(
            score=final_score,
            status=status,
            weights=weights,
            breakdown=breakdown,
            interpretation=interpretation,
        )

    def _generate_composite_interpretation(
        self,
        score: float,
        status: MetricStatus,
    ) -> str:
        """Generate human-readable interpretation of composite score.

        Override in subclass for category-specific interpretations.
        """
        interpretations = {
            MetricStatus.LOW: f"The {self.CATEGORY_NAME} index is at {score:.1f}, indicating low risk / accumulation zone.",
            MetricStatus.NORMAL: f"The {self.CATEGORY_NAME} index is at {score:.1f}, suggesting normal market conditions.",
            MetricStatus.ELEVATED: f"The {self.CATEGORY_NAME} index is at {score:.1f}, showing elevated caution levels.",
            MetricStatus.HIGH: f"The {self.CATEGORY_NAME} index is at {score:.1f}, signaling high risk / euphoria conditions.",
        }
        return interpretations.get(status, f"{self.CATEGORY_NAME} score: {score:.1f}")

    @staticmethod
    def normalize_score(
        value: float,
        min_val: float,
        max_val: float,
        invert: bool = False,
    ) -> float:
        """Normalize a value to 0-100 scale.

        Args:
            value: Raw value to normalize
            min_val: Expected minimum value
            max_val: Expected maximum value
            invert: If True, higher raw values = lower scores

        Returns:
            Normalized score 0-100
        """
        if max_val == min_val:
            return 50.0

        normalized = (value - min_val) / (max_val - min_val) * 100
        normalized = max(0.0, min(100.0, normalized))

        if invert:
            normalized = 100.0 - normalized

        return round(normalized, 2)
