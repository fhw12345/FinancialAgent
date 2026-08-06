"""
LangChain tools for Market Insights Platform.
Enables the LLM agent to query and explain market insight categories and metrics.

Story 2.5: Redis Integration
- get_insight_category reads from Redis cache first (< 100ms)
- get_insight_trend returns formatted 30-day history with trend indicators
- Graceful fallback to MongoDB if cache miss
"""

import time
import typing
from typing import TYPE_CHECKING

import structlog
from langchain_core.tools import tool

from ...services.insights import InsightsCategoryRegistry

if TYPE_CHECKING:
    from ...services.insights.snapshot_service import InsightsSnapshotService

logger = structlog.get_logger()


def create_insights_tools(
    registry: InsightsCategoryRegistry,
    snapshot_service: "InsightsSnapshotService | None" = None,
) -> list[typing.Any]:
    """
    Create Market Insights tools for the LLM agent.

    These tools allow the agent to:
    1. List available insight categories
    2. Get detailed metrics for a category (cache-first for < 100ms response)
    3. Get individual metric explanations
    4. Get historical trend data with direction indicators

    Args:
        registry: InsightsCategoryRegistry instance with dependencies
        snapshot_service: InsightsSnapshotService for cache-first reads (Story 2.5)

    Returns:
        List of LangChain tools
    """

    @tool
    async def list_insight_categories() -> str:
        """
        List all available market insight categories.

        Returns the names and descriptions of insight categories
        that can be queried for detailed metrics and analysis.

        Use this when the user asks about what insights are available
        or wants an overview of market analysis capabilities.

        Returns:
            List of categories with names, icons, and descriptions
        """
        try:
            categories = registry.list_categories()

            if not categories:
                return "No insight categories are currently available."

            lines = ["## Available Market Insight Categories\n"]
            for cat in categories:
                lines.append(f"**{cat.icon} {cat.name}** (`{cat.id}`)")
                lines.append(f"  {cat.description}")
                lines.append(f"  Metrics: {cat.metric_count}\n")

            return "\n".join(lines)

        except Exception as e:
            logger.error("Failed to list insight categories", error=str(e))
            return f"Error listing insight categories: {str(e)}"

    @tool
    async def get_insight_category(category_id: str) -> str:
        """
        Get detailed metrics and composite score for a market insight category.

        This tool provides comprehensive analysis including:
        - Composite score (0-100) with interpretation
        - Individual metric scores with status levels
        - Actionable insights for each metric

        Uses Redis cache for fast response (< 100ms when cached).

        Args:
            category_id: Category identifier (e.g., "ai_sector_risk")
                        Use list_insight_categories to see available categories.

        Returns:
            Formatted analysis with scores, status, and recommendations

        Example:
            get_insight_category("ai_sector_risk")
        """
        start_time = time.time()

        try:
            # Story 2.5: Try cache-first via SnapshotService
            cached_data = None
            if snapshot_service:
                cached_data = await snapshot_service.get_latest_snapshot(category_id)
                if cached_data:
                    elapsed_ms = (time.time() - start_time) * 1000
                    logger.info(
                        "Insight category from cache",
                        category_id=category_id,
                        elapsed_ms=round(elapsed_ms, 1),
                        source="redis" if cached_data.get("cached_at") else "mongodb",
                    )
                    return _format_cached_insight(category_id, cached_data)

            # Fallback: Calculate via registry (slower path)
            logger.debug(
                "Cache miss, calculating via registry",
                category_id=category_id,
            )
            data = await registry.get_category_data(category_id)

            if data is None:
                available = [c.id for c in registry.list_categories()]
                return (
                    f"Category '{category_id}' not found. "
                    f"Available categories: {', '.join(available)}"
                )

            lines = [f"## {data.icon} {data.name}\n"]

            # Composite score
            if data.composite:
                lines.append("### Overall Assessment")
                lines.append(
                    f"**Composite Score: {data.composite.score:.0f}/100** "
                    f"({data.composite.status.upper()})"
                )
                lines.append(f"\n{data.composite.interpretation}\n")

            # Individual metrics
            lines.append("### Metrics\n")
            for metric in data.metrics:
                status_emoji = _get_status_emoji(metric.status.value)
                lines.append(
                    f"{status_emoji} **{metric.name}**: "
                    f"{metric.score:.0f}/100 ({metric.status.value})"
                )
                lines.append(f"   {metric.explanation.summary}")
                lines.append(f"   💡 *{metric.explanation.actionable_insight}*\n")

            # Data timestamp
            lines.append(f"\n---\n*Last updated: {data.last_updated.isoformat()}*")

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "Insight category calculated",
                category_id=category_id,
                elapsed_ms=round(elapsed_ms, 1),
                source="registry",
            )

            return "\n".join(lines)

        except Exception as e:
            logger.error(
                "Failed to get insight category",
                category_id=category_id,
                error=str(e),
            )
            return f"Error retrieving category '{category_id}': {str(e)}"

    @tool
    async def get_insight_metric(category_id: str, metric_id: str) -> str:
        """
        Get detailed explanation for a specific market insight metric.

        Provides in-depth analysis including:
        - Score with historical context
        - Methodology explanation
        - Calculation formula (if applicable)
        - Actionable recommendations
        - Data sources used

        Args:
            category_id: Category identifier (e.g., "ai_sector_risk")
            metric_id: Metric identifier within the category
                      (e.g., "ai_price_anomaly", "news_sentiment")

        Returns:
            Rich explanation with methodology and recommendations

        Example:
            get_insight_metric("ai_sector_risk", "ai_price_anomaly")
        """
        try:
            instance = registry.get_category_instance(category_id)

            if instance is None:
                available = [c.id for c in registry.list_categories()]
                return (
                    f"Category '{category_id}' not found. "
                    f"Available: {', '.join(available)}"
                )

            metric = await instance.get_metric(metric_id)

            if metric is None:
                # List available metrics
                data = await instance.get_category_data()
                available_metrics = [m.id for m in data.metrics]
                return (
                    f"Metric '{metric_id}' not found in category '{category_id}'. "
                    f"Available metrics: {', '.join(available_metrics)}"
                )

            status_emoji = _get_status_emoji(metric.status.value)
            lines = [
                f"## {metric.name} {status_emoji}",
                f"**Score: {metric.score:.0f}/100** | Status: {metric.status.value.upper()}\n",
                f"### Summary\n{metric.explanation.summary}\n",
                f"### Detailed Analysis\n{metric.explanation.detail}\n",
                f"### Methodology\n{metric.explanation.methodology}",
            ]

            if metric.explanation.formula:
                lines.append(f"\n**Formula**: `{metric.explanation.formula}`")

            lines.extend(
                [
                    f"\n### Historical Context\n{metric.explanation.historical_context}\n",
                    f"### What This Means For You\n💡 {metric.explanation.actionable_insight}\n",
                    "### Data Sources\n" + ", ".join(metric.data_sources),
                    f"\n---\n*Last updated: {metric.last_updated.isoformat()}*",
                ]
            )

            return "\n".join(lines)

        except Exception as e:
            logger.error(
                "Failed to get insight metric",
                category_id=category_id,
                metric_id=metric_id,
                error=str(e),
            )
            return (
                f"Error retrieving metric '{metric_id}' "
                f"from category '{category_id}': {str(e)}"
            )

    @tool
    async def get_insight_trend(category_id: str, days: int = 30) -> str:
        """
        Get historical trend for a market insight category.

        Shows how the composite score and individual metrics
        have changed over the specified number of days.

        Args:
            category_id: Category identifier (e.g., "ai_sector_risk")
            days: Number of days of history (default: 30, max: 90)

        Returns:
            Trend analysis with score changes and patterns

        Example:
            get_insight_trend("ai_sector_risk", 30)
        """
        start_time = time.time()

        # Cap days at 90
        days = min(max(days, 1), 90)

        try:
            if not snapshot_service:
                return (
                    "Trend data is not available. "
                    "The snapshot service is not configured."
                )

            # Fetch trend from MongoDB via SnapshotService
            snapshots = await snapshot_service.get_trend(category_id, days)

            if not snapshots:
                return (
                    f"No trend data available for '{category_id}'. "
                    "Please check if insights have been collected."
                )

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "Insight trend retrieved",
                category_id=category_id,
                days=days,
                snapshot_count=len(snapshots),
                elapsed_ms=round(elapsed_ms, 1),
            )

            return _format_trend_response(category_id, snapshots, days)

        except Exception as e:
            logger.error(
                "Failed to get insight trend",
                category_id=category_id,
                days=days,
                error=str(e),
            )
            return f"Error retrieving trend for '{category_id}': {str(e)}"

    # Build tool list
    tools = [list_insight_categories, get_insight_category, get_insight_metric]

    # Add trend tool only if snapshot_service is available
    if snapshot_service:
        tools.append(get_insight_trend)

    return tools


def _get_status_emoji(status: str) -> str:
    """Get emoji for metric status level."""
    return {
        "low": "🟢",
        "normal": "🔵",
        "elevated": "🟠",
        "high": "🔴",
    }.get(status, "⚪")


def _format_cached_insight(category_id: str, cached_data: dict[str, typing.Any]) -> str:
    """Format cached insight data for display.

    Args:
        category_id: Category identifier
        cached_data: Cached snapshot from Redis/MongoDB

    Returns:
        Formatted markdown string
    """
    # Category name mapping
    category_names = {
        "ai_sector_risk": "AI Sector Risk",
    }
    name = category_names.get(category_id, category_id.replace("_", " ").title())

    lines = [f"## 📊 {name}\n"]

    # Composite score
    composite_score = cached_data.get("composite_score", 0)
    composite_status = cached_data.get("composite_status", "normal")
    status_emoji = _get_status_emoji(composite_status)

    lines.append("### Overall Assessment")
    lines.append(
        f"**Composite Score: {composite_score:.0f}/100** "
        f"{status_emoji} ({composite_status.upper()})"
    )
    lines.append("")

    # Individual metrics
    metrics = cached_data.get("metrics", {})
    if metrics:
        lines.append("### Metrics\n")
        lines.append("| Metric | Score | Status |")
        lines.append("|--------|-------|--------|")

        for metric_id, metric_data in metrics.items():
            score = metric_data.get("score", 0)
            status = metric_data.get("status", "normal")
            emoji = _get_status_emoji(status)
            metric_name = metric_id.replace("_", " ").title()
            lines.append(f"| {metric_name} | {score:.0f}/100 | {emoji} {status} |")

        lines.append("")

    # Data timestamp
    date_str = cached_data.get("date", "")
    if date_str:
        lines.append(f"\n---\n*Data as of: {date_str}*")

    return "\n".join(lines)


def _get_trend_direction(change: float) -> tuple[str, str]:
    """Get trend direction indicator and label.

    Args:
        change: Score change value

    Returns:
        Tuple of (direction symbol, direction label)
    """
    if change > 2:
        return "↑", "Rising"
    elif change < -2:
        return "↓", "Falling"
    else:
        return "→", "Stable"


def _format_trend_response(
    category_id: str, snapshots: list[dict[str, typing.Any]], days: int
) -> str:
    """Format trend response with direction indicators.

    Args:
        category_id: Category identifier
        snapshots: List of snapshots ordered by date descending
        days: Number of days requested

    Returns:
        Formatted markdown string with trend analysis
    """
    # Category name mapping
    category_names = {
        "ai_sector_risk": "AI Sector Risk",
    }
    name = category_names.get(category_id, category_id.replace("_", " ").title())

    if len(snapshots) < 2:
        # Not enough data for trend
        lines = [f"## {name} - {days} Day Trend 📊\n"]
        if snapshots:
            score = snapshots[0].get("composite_score", 0)
            status = snapshots[0].get("composite_status", "normal")
            lines.append(
                f"**Current Score**: {score:.1f}/100 ({_get_status_emoji(status)} {status.title()})"
            )
            lines.append("\n*Not enough historical data for trend analysis.*")
        else:
            lines.append("*No data available for trend analysis.*")
        return "\n".join(lines)

    # Calculate composite trend
    current = snapshots[0]
    oldest = snapshots[-1]
    current_score = current.get("composite_score", 0)
    oldest_score = oldest.get("composite_score", 0)
    score_change = current_score - oldest_score

    direction, direction_label = _get_trend_direction(score_change)
    status = current.get("composite_status", "normal")

    lines = [f"## {name} - {days} Day Trend 📊\n"]
    lines.append(
        f"**Current Score**: {current_score:.1f}/100 ({_get_status_emoji(status)} {status.title()})"
    )
    lines.append(f"**{days}-Day Change**: {direction} {score_change:+.1f} points\n")

    # Metric trends
    current_metrics = current.get("metrics", {})
    oldest_metrics = oldest.get("metrics", {})

    if current_metrics:
        lines.append("### Metric Trends\n")
        lines.append("| Metric | Current | Change | Direction |")
        lines.append("|--------|---------|--------|-----------|")

        for metric_id, metric_data in current_metrics.items():
            metric_score = metric_data.get("score", 0)
            metric_status = metric_data.get("status", "normal")
            emoji = _get_status_emoji(metric_status)

            # Calculate change
            old_metric = oldest_metrics.get(metric_id, {})
            old_score = old_metric.get("score", metric_score)
            metric_change = metric_score - old_score
            m_dir, m_label = _get_trend_direction(metric_change)

            metric_name = metric_id.replace("_", " ").title()
            lines.append(
                f"| {metric_name} | {metric_score:.0f} {emoji} | "
                f"{metric_change:+.0f} | {m_dir} {m_label} |"
            )

        lines.append("")

    # Interpretation
    lines.append("### Interpretation\n")
    if abs(score_change) < 5:
        lines.append(
            f"The {name.lower()} has remained relatively stable over the past {days} days."
        )
    elif score_change > 0:
        lines.append(
            f"The {name.lower()} has increased by {score_change:.1f} points over "
            f"the past {days} days, indicating growing risk in this sector."
        )
    else:
        lines.append(
            f"The {name.lower()} has decreased by {abs(score_change):.1f} points over "
            f"the past {days} days, suggesting reduced risk in this sector."
        )

    return "\n".join(lines)
