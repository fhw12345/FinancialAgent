"""Market Insights API endpoints.

Provides REST API for accessing insight categories, metrics,
and composite scores with caching support.
"""

import time

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from ...database.mongodb import MongoDB
from ...database.redis import RedisCache
from ...services.insights import InsightsCategoryRegistry, InsightsSnapshotService
from ..dependencies.storage import get_mongodb, get_redis_cache
from ..schemas.insights_models import (
    CategoriesListResponse,
    CategoryMetadataResponse,
    CompositeScoreResponse,
    InsightCategoryResponse,
    InsightMetricResponse,
    RefreshResponse,
    TrendDataPoint,
    TrendResponse,
)

logger = structlog.get_logger()
router = APIRouter()

# Rate limiting
limiter = Limiter(key_func=get_remote_address)


def get_insights_registry(request: Request) -> InsightsCategoryRegistry:
    """Get insights registry singleton from app state.

    The registry is initialized once at application startup in main.py lifespan,
    ensuring consistent caching and avoiding per-request instantiation overhead.
    """
    registry = request.app.state.insights_registry
    if not isinstance(registry, InsightsCategoryRegistry):
        raise RuntimeError("Insights registry not initialized")
    return registry


@router.get("/categories", response_model=CategoriesListResponse)
@limiter.limit("60/minute")
async def list_categories(
    request: Request,
    registry: InsightsCategoryRegistry = Depends(get_insights_registry),
) -> CategoriesListResponse:
    """
    List all available insight categories.

    Returns metadata for each category including name, icon, description,
    and metric count. Use the category ID to fetch full category data.

    **Rate Limit**: 60 requests per minute
    """
    request_start = time.time()

    try:
        categories = registry.list_categories()

        response = CategoriesListResponse(
            categories=[
                CategoryMetadataResponse(
                    id=cat.id,
                    name=cat.name,
                    icon=cat.icon,
                    description=cat.description,
                    metric_count=cat.metric_count,
                    last_updated=cat.last_updated,
                )
                for cat in categories
            ],
            count=len(categories),
        )

        duration = time.time() - request_start
        logger.info(
            "Categories listed",
            category_count=len(categories),
            duration_ms=round(duration * 1000, 2),
        )

        return response

    except Exception as e:
        logger.error("Failed to list categories", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to list categories") from e


@router.get("/{category_id}", response_model=InsightCategoryResponse)
@limiter.limit("30/minute")
async def get_category(
    category_id: str,
    request: Request,
    force_refresh: bool = False,
    registry: InsightsCategoryRegistry = Depends(get_insights_registry),
) -> InsightCategoryResponse:
    """
    Get complete data for a category including all metrics.

    Returns all metrics with scores, explanations, and the composite score.
    Results are cached for 30 minutes unless force_refresh=true.

    **Rate Limit**: 30 requests per minute (API-heavy operation)

    Args:
        category_id: The category identifier (e.g., 'ai_sector_risk')
        force_refresh: If true, bypass cache and recalculate

    Returns:
        Complete category data with all metrics
    """
    request_start = time.time()

    try:
        logger.info(
            "Category data requested",
            category_id=category_id,
            force_refresh=force_refresh,
        )

        data = await registry.get_category_data(
            category_id, force_refresh=force_refresh
        )

        if data is None:
            raise HTTPException(
                status_code=404,
                detail=f"Category '{category_id}' not found",
            )

        # Convert to response model
        response = InsightCategoryResponse(
            id=data.id,
            name=data.name,
            icon=data.icon,
            description=data.description,
            metrics=[
                InsightMetricResponse(
                    id=m.id,
                    name=m.name,
                    score=m.score,
                    status=m.status.value,
                    explanation=m.explanation.model_dump(),
                    data_sources=m.data_sources,
                    last_updated=m.last_updated,
                    raw_data=m.raw_data,
                )
                for m in data.metrics
            ],
            composite=(
                CompositeScoreResponse(
                    score=data.composite.score,
                    status=data.composite.status.value,
                    weights=data.composite.weights,
                    breakdown=data.composite.breakdown,
                    interpretation=data.composite.interpretation,
                )
                if data.composite
                else None
            ),
            last_updated=data.last_updated,
        )

        duration = time.time() - request_start
        logger.info(
            "Category data returned",
            category_id=category_id,
            metric_count=len(data.metrics),
            duration_ms=round(duration * 1000, 2),
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get category data", category_id=category_id, error=str(e)
        )
        raise HTTPException(
            status_code=500, detail="Failed to get category data"
        ) from e


@router.get("/{category_id}/composite", response_model=CompositeScoreResponse)
@limiter.limit("60/minute")
async def get_composite(
    category_id: str,
    request: Request,
    registry: InsightsCategoryRegistry = Depends(get_insights_registry),
) -> CompositeScoreResponse:
    """
    Get just the composite score for a category.

    Returns the weighted composite score with breakdown by metric.
    Useful for quick overview without full metric details.

    **Rate Limit**: 60 requests per minute
    """
    request_start = time.time()

    try:
        instance = registry.get_category_instance(category_id)

        if instance is None:
            raise HTTPException(
                status_code=404,
                detail=f"Category '{category_id}' not found",
            )

        composite = await instance.get_composite()

        response = CompositeScoreResponse(
            score=composite.score,
            status=composite.status.value,
            weights=composite.weights,
            breakdown=composite.breakdown,
            interpretation=composite.interpretation,
        )

        duration = time.time() - request_start
        logger.info(
            "Composite score returned",
            category_id=category_id,
            score=composite.score,
            duration_ms=round(duration * 1000, 2),
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get composite", category_id=category_id, error=str(e))
        raise HTTPException(
            status_code=500, detail="Failed to get composite score"
        ) from e


@router.get("/{category_id}/trend", response_model=TrendResponse)
@limiter.limit("60/minute")
async def get_category_trend(
    category_id: str,
    request: Request,
    days: int = Query(default=30, ge=7, le=90, description="Number of days of history"),
    mongodb: MongoDB = Depends(get_mongodb),
    redis_cache: RedisCache = Depends(get_redis_cache),
    registry: InsightsCategoryRegistry = Depends(get_insights_registry),
) -> TrendResponse:
    """
    Get historical trend for a category.

    Returns the composite score trend and individual metric trends
    for the specified number of days. Data comes from daily snapshots
    stored in MongoDB.

    **Rate Limit**: 60 requests per minute

    Args:
        category_id: The category identifier (e.g., 'ai_sector_risk')
        days: Number of days of history (7, 14, 30, 60, or 90)

    Returns:
        Trend data with composite and individual metric trends
    """
    request_start = time.time()

    try:
        # Verify category exists
        if registry.get_category_instance(category_id) is None:
            raise HTTPException(
                status_code=404,
                detail=f"Category '{category_id}' not found",
            )

        # Create snapshot service and get trend data
        snapshot_service = InsightsSnapshotService(
            mongodb=mongodb,
            redis_cache=redis_cache,
            data_manager=None,  # Not needed for read operations
            settings=None,  # Not needed for read operations
            registry=registry,
        )

        snapshots = await snapshot_service.get_trend(category_id, days)

        # Build composite trend
        composite_trend = [
            TrendDataPoint(
                date=(
                    s.get("date", "").strftime("%Y-%m-%d")
                    if hasattr(s.get("date"), "strftime")
                    else str(s.get("date", ""))[:10]
                ),
                score=s.get("composite_score", 0.0),
                status=s.get("composite_status", "unknown"),
            )
            for s in snapshots
        ]

        # Build individual metric trends
        metric_trends: dict[str, list[TrendDataPoint]] = {}
        for s in snapshots:
            metrics_data = s.get("metrics", {})
            for metric_id, metric_info in metrics_data.items():
                if metric_id not in metric_trends:
                    metric_trends[metric_id] = []
                metric_trends[metric_id].append(
                    TrendDataPoint(
                        date=(
                            s.get("date", "").strftime("%Y-%m-%d")
                            if hasattr(s.get("date"), "strftime")
                            else str(s.get("date", ""))[:10]
                        ),
                        score=metric_info.get("score", 0.0),
                        status=metric_info.get("status", "unknown"),
                    )
                )

        response = TrendResponse(
            category_id=category_id,
            days=days,
            trend=composite_trend,
            metrics=metric_trends,
        )

        duration = time.time() - request_start
        logger.info(
            "Trend data returned",
            category_id=category_id,
            days=days,
            datapoints=len(composite_trend),
            duration_ms=round(duration * 1000, 2),
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get trend data",
            category_id=category_id,
            days=days,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Failed to get trend data") from e


@router.get("/{category_id}/{metric_id}", response_model=InsightMetricResponse)
@limiter.limit("60/minute")
async def get_metric(
    category_id: str,
    metric_id: str,
    request: Request,
    registry: InsightsCategoryRegistry = Depends(get_insights_registry),
) -> InsightMetricResponse:
    """
    Get a single metric with full explanation.

    Returns detailed metric data including score, explanation,
    methodology, and raw calculation data.

    **Rate Limit**: 60 requests per minute
    """
    request_start = time.time()

    try:
        instance = registry.get_category_instance(category_id)

        if instance is None:
            raise HTTPException(
                status_code=404,
                detail=f"Category '{category_id}' not found",
            )

        metric = await instance.get_metric(metric_id)

        if metric is None:
            raise HTTPException(
                status_code=404,
                detail=f"Metric '{metric_id}' not found in category '{category_id}'",
            )

        response = InsightMetricResponse(
            id=metric.id,
            name=metric.name,
            score=metric.score,
            status=metric.status.value,
            explanation=metric.explanation.model_dump(),
            data_sources=metric.data_sources,
            last_updated=metric.last_updated,
            raw_data=metric.raw_data,
        )

        duration = time.time() - request_start
        logger.info(
            "Metric returned",
            category_id=category_id,
            metric_id=metric_id,
            score=metric.score,
            duration_ms=round(duration * 1000, 2),
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get metric",
            category_id=category_id,
            metric_id=metric_id,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Failed to get metric") from e


@router.post("/{category_id}/refresh", response_model=RefreshResponse)
@limiter.limit("5/minute")
async def refresh_category(
    category_id: str,
    request: Request,
    registry: InsightsCategoryRegistry = Depends(get_insights_registry),
) -> RefreshResponse:
    """
    Force refresh a category's data.

    Clears the cache and recalculates all metrics from fresh API data.
    Use sparingly as this makes multiple Alpha Vantage API calls.

    **Rate Limit**: 5 requests per minute (API-heavy operation)
    """
    request_start = time.time()

    try:
        logger.info("Category refresh requested", category_id=category_id)

        data = await registry.refresh_category(category_id)

        if data is None:
            raise HTTPException(
                status_code=404,
                detail=f"Category '{category_id}' not found",
            )

        duration = time.time() - request_start
        logger.info(
            "Category refreshed",
            category_id=category_id,
            duration_ms=round(duration * 1000, 2),
        )

        return RefreshResponse(
            success=True,
            category_id=category_id,
            message=f"Category '{category_id}' refreshed successfully",
            last_updated=data.last_updated,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to refresh category", category_id=category_id, error=str(e)
        )
        raise HTTPException(status_code=500, detail="Failed to refresh category") from e
