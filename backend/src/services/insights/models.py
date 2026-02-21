"""Pydantic models for the Market Insights Platform.

This module defines the core data models for metrics, explanations,
and categories used throughout the insights service.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MetricStatus(StrEnum):
    """Status levels for insight metrics."""

    LOW = "low"
    NORMAL = "normal"
    ELEVATED = "elevated"
    HIGH = "high"


class ThresholdConfig(BaseModel):
    """Threshold configuration for metric interpretation zones."""

    low: int = Field(default=25, description="Upper bound for 'low' zone (0-25)")
    normal: int = Field(default=50, description="Upper bound for 'normal' zone (25-50)")
    elevated: int = Field(
        default=75, description="Upper bound for 'elevated' zone (50-75)"
    )
    high: int = Field(default=100, description="Upper bound for 'high' zone (75-100)")

    def get_status(self, score: float) -> MetricStatus:
        """Determine status based on score and thresholds."""
        if score < self.low:
            return MetricStatus.LOW
        elif score < self.normal:
            return MetricStatus.NORMAL
        elif score < self.elevated:
            return MetricStatus.ELEVATED
        else:
            return MetricStatus.HIGH


class MetricExplanation(BaseModel):
    """Rich explanation for a metric - core UX feature.

    Every metric must have comprehensive explanation to be
    both human-readable and LLM-interpretable ("talkable").
    """

    summary: str = Field(..., description="One-liner for quick scan")
    detail: str = Field(..., description="2-3 sentences with specifics")
    methodology: str = Field(..., description="How the metric is calculated")
    formula: str | None = Field(default=None, description="Optional math formula")
    historical_context: str = Field(..., description="Last time this high...")
    actionable_insight: str = Field(..., description="What to consider based on this")
    thresholds: ThresholdConfig = Field(
        default_factory=ThresholdConfig,
        description="Score interpretation zones",
    )


class InsightMetric(BaseModel):
    """Individual metric within a category."""

    id: str = Field(
        ..., description="Unique metric identifier (e.g., 'ai_price_anomaly')"
    )
    name: str = Field(..., description="Human-readable name (e.g., 'AI Price Anomaly')")
    score: float = Field(..., ge=0, le=100, description="Normalized score 0-100")
    status: MetricStatus = Field(..., description="Interpreted status level")
    explanation: MetricExplanation = Field(..., description="Rich explanation")
    data_sources: list[str] = Field(
        default_factory=list,
        description="Alpha Vantage endpoints used",
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this metric was calculated",
    )
    raw_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw calculation data for debugging/agent use",
    )


class CompositeScore(BaseModel):
    """Weighted composite score for a category."""

    score: float = Field(..., ge=0, le=100, description="Weighted composite score")
    status: MetricStatus = Field(..., description="Overall status")
    weights: dict[str, float] = Field(..., description="Weight per metric")
    breakdown: dict[str, float] = Field(
        ...,
        description="Score contribution per metric",
    )
    interpretation: str = Field(..., description="Human-readable interpretation")


class InsightCategory(BaseModel):
    """Complete insight category with all metrics."""

    id: str = Field(..., description="Category identifier (e.g., 'ai_sector_risk')")
    name: str = Field(..., description="Display name (e.g., 'AI Sector Risk')")
    icon: str = Field(..., description="Emoji icon for UI")
    description: str = Field(..., description="Category purpose explanation")
    metrics: list[InsightMetric] = Field(
        default_factory=list, description="All metrics"
    )
    composite: CompositeScore | None = Field(
        default=None,
        description="Weighted composite score",
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Last calculation time",
    )


class CategoryMetadata(BaseModel):
    """Lightweight category info for listing."""

    id: str
    name: str
    icon: str
    description: str
    metric_count: int
    last_updated: datetime | None = None
