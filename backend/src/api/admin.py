"""
Admin-only API endpoints for system monitoring and health checks.
"""

from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Request

from src.core.utils.date_utils import utcnow

from ..core.config import get_settings
from ..database.mongodb import MongoDB
from ..database.redis import RedisCache
from ..database.repositories.tool_execution_repository import ToolExecutionRepository
from ..services.cache_warming_service import CacheWarmingService
from ..services.data_manager import DataManager
from ..services.database_stats_service import DatabaseStatsService
from ..services.insights import InsightsCategoryRegistry, InsightsSnapshotService
from .dependencies.storage import get_mongodb, get_redis_cache
from .dependencies.timing_middleware import TimingMiddleware
from .schemas.admin_models import DatabaseStats, HealthResponse, SystemMetrics

logger = structlog.get_logger()

router = APIRouter(prefix="/api/admin", tags=["admin"])


def get_database_stats_service(
    mongodb: MongoDB = Depends(get_mongodb),
) -> DatabaseStatsService:
    """Get database statistics service instance."""
    if mongodb.database is None:
        raise RuntimeError("MongoDB database is not initialized")
    return DatabaseStatsService(mongodb.database)


@router.get("/health", response_model=HealthResponse)
async def get_system_health(
    db_stats_service: DatabaseStatsService = Depends(get_database_stats_service),
) -> SystemMetrics:
    """Get local application and database health metrics."""
    database_stats = await db_stats_service.get_collection_stats()

    metrics = SystemMetrics(
        timestamp=utcnow(),
        database=database_stats,
        health_status="healthy",
    )

    logger.info(
        "System health metrics collected",
        db_collections=len(database_stats),
        status=metrics.health_status,
    )

    return metrics


@router.get("/database", response_model=list)
async def get_database_stats(
    db_stats_service: DatabaseStatsService = Depends(get_database_stats_service),
) -> list[DatabaseStats]:
    """
    Get database collection statistics only.

    Returns:
        List of database collection statistics
    """
    return await db_stats_service.get_collection_stats()


@router.get("/timing-metrics")
async def get_timing_metrics() -> dict[str, dict[str, float | None]]:
    """
    Get API endpoint timing metrics (P50, P95, P99 response times).

    Returns:
        Dictionary mapping endpoints to their percentile metrics:
        - p50: Median response time in ms
        - p95: 95th percentile response time in ms
        - p99: 99th percentile response time in ms
        - count: Number of samples
        - min, max, avg: Additional statistics
    """
    metrics = TimingMiddleware.get_all_metrics()

    # Sort by P95 descending to show slowest endpoints first
    sorted_metrics = dict(
        sorted(
            metrics.items(),
            key=lambda x: x[1].get("p95") or 0,
            reverse=True,
        )
    )

    logger.info(
        "Timing metrics requested",
        endpoint_count=len(sorted_metrics),
    )

    return sorted_metrics


# =============================================================================
# Insights Snapshot Endpoints
# =============================================================================


def get_data_manager(request: Request) -> DataManager:
    """Get DataManager from app state."""
    manager = getattr(request.app.state, "data_manager", None)
    if not isinstance(manager, DataManager):
        raise RuntimeError("DataManager not initialized")
    return manager


def get_insights_registry(request: Request) -> InsightsCategoryRegistry:
    """Get insights registry from app state."""
    registry = getattr(request.app.state, "insights_registry", None)
    if not isinstance(registry, InsightsCategoryRegistry):
        raise RuntimeError("Insights registry not initialized")
    return registry


@router.post("/insights/trigger-snapshot", status_code=202)
async def trigger_insights_snapshot(
    background_tasks: BackgroundTasks,
    request: Request,
    mongodb: MongoDB = Depends(get_mongodb),
    redis_cache: RedisCache = Depends(get_redis_cache),
) -> dict[str, Any]:
    """
    Trigger local insights snapshot creation.

    Returns immediately with 202 Accepted. Snapshot creation runs in background.

    Returns:
        dict: Status message with run_id

    """
    run_id = f"snapshot_{utcnow().strftime('%Y%m%d_%H%M%S')}"

    logger.info(
        "Insights snapshot triggered via API",
        run_id=run_id,
        trigger_source="admin_endpoint",
    )

    # Get services from app state
    data_manager = get_data_manager(request)
    insights_registry = get_insights_registry(request)

    if not data_manager:
        return {
            "status": "error",
            "message": "DataManager not initialized",
        }

    # Add background task
    background_tasks.add_task(
        run_insights_snapshot_background,
        mongodb=mongodb,
        redis_cache=redis_cache,
        data_manager=data_manager,
        insights_registry=insights_registry,
        run_id=run_id,
    )

    return {
        "status": "started",
        "run_id": run_id,
        "message": "Insights snapshot running in background",
        "note": "Check backend logs for progress and results",
    }


async def run_insights_snapshot_background(
    mongodb: MongoDB,
    redis_cache: RedisCache,
    data_manager: DataManager,
    insights_registry: InsightsCategoryRegistry,
    run_id: str,
) -> None:
    """
    Background task for insights snapshot creation.

    Args:
        mongodb: MongoDB connection
        redis_cache: Redis cache connection
        data_manager: DataManager (DML) instance
        insights_registry: Insights category registry
        run_id: Unique run identifier
    """
    logger.info(
        "Insights snapshot background task started",
        run_id=run_id,
    )

    try:
        settings = get_settings()

        # Create snapshot service
        snapshot_service = InsightsSnapshotService(
            mongodb=mongodb,
            redis_cache=redis_cache,
            data_manager=data_manager,
            settings=settings,
            registry=insights_registry,
        )

        # Ensure indexes exist
        await snapshot_service.ensure_indexes()

        # Create snapshot
        result = await snapshot_service.create_snapshot(
            category_id="ai_sector_risk",
            run_id=run_id,
        )

        # Log summary
        logger.info(
            "Insights snapshot completed",
            run_id=run_id,
            status=result.get("status"),
            composite_score=result.get("composite_score"),
            total_seconds=result.get("timing", {}).get("total_seconds"),
        )

        # Print summary (appears in pod logs)
        print("\n" + "=" * 60)
        print("INSIGHTS SNAPSHOT SUMMARY")
        print("=" * 60)
        print(f"Run ID: {run_id}")
        print(f"Status: {result.get('status')}")
        print(f"Composite Score: {result.get('composite_score')}")
        print(f"Duration: {result.get('timing', {}).get('total_seconds', 0):.2f}s")
        print("=" * 60)

    except Exception as e:
        logger.error(
            "Insights snapshot background task failed",
            run_id=run_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        # Don't raise - background task failure shouldn't crash the API


# =============================================================================
# Cache Warming Endpoints
# =============================================================================


def get_cache_warming_service(request: Request) -> CacheWarmingService:
    """Get cache warming service from app state."""
    service = getattr(request.app.state, "cache_warming_service", None)
    if not isinstance(service, CacheWarmingService):
        raise RuntimeError("Cache warming service not initialized")
    return service


@router.post("/cache/warm")
async def warm_cache(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Trigger cache warming for common symbols.

    Warms the cache with data for popular stocks and market movers.
    Runs in background and returns immediately.

    **Admin only**: Requires admin privileges.

    Returns:
        dict: Status message
    """
    cache_warming_service = get_cache_warming_service(request)

    if not cache_warming_service:
        return {"status": "error", "message": "Cache warming service not initialized"}

    logger.info("Manual cache warming triggered via API")

    # Run warming in background
    background_tasks.add_task(cache_warming_service.warm_startup_cache)

    return {
        "status": "started",
        "message": "Cache warming running in background",
        "symbols": cache_warming_service.DEFAULT_SYMBOLS,
    }


@router.post("/cache/warm-market-movers")
async def warm_market_movers_cache(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Trigger cache warming for current market movers.

    Fetches and caches top gainers, losers, and most active stocks.
    Runs in background and returns immediately.

    **Admin only**: Requires admin privileges.

    Returns:
        dict: Status message
    """
    cache_warming_service = get_cache_warming_service(request)

    if not cache_warming_service:
        return {"status": "error", "message": "Cache warming service not initialized"}

    logger.info("Market movers cache warming triggered via API")

    background_tasks.add_task(cache_warming_service.warm_market_movers)

    return {
        "status": "started",
        "message": "Market movers cache warming running in background",
    }


@router.get("/cache/warming-status")
async def get_cache_warming_status(
    request: Request,
) -> dict[str, Any]:
    """
    Get current cache warming status.

    **Admin only**: Requires admin privileges.

    Returns:
        dict: Cache warming status and statistics
    """
    cache_warming_service = get_cache_warming_service(request)

    if not cache_warming_service:
        return {"status": "error", "message": "Cache warming service not initialized"}

    return await cache_warming_service.get_warming_status()


@router.get("/cache/stats")
async def get_cache_stats(
    redis_cache: RedisCache = Depends(get_redis_cache),
) -> dict[str, Any]:
    """
    Get comprehensive Redis cache statistics.

    Returns memory usage, hit/miss ratio, key counts, and performance metrics.
    Useful for monitoring cache efficiency and optimization decisions.

    **Admin only**: Requires admin privileges.

    Returns:
        dict: Cache statistics including:
        - memory: Used/peak memory, fragmentation ratio
        - keys: Total, with expiry, expired, evicted counts
        - cache_efficiency: Hits, misses, hit ratio percentage
        - connections: Connected and blocked clients
        - performance: Operations per second, total commands
    """
    logger.info("Cache stats requested via admin endpoint")

    try:
        stats = await redis_cache.get_cache_stats()
        return stats
    except Exception as e:
        logger.error("Failed to get cache stats", error=str(e))
        return {"status": "error", "message": str(e)}


# =============================================================================
# LLM/Agent Performance Metrics Endpoints
# =============================================================================


def get_tool_execution_repository(
    mongodb: MongoDB = Depends(get_mongodb),
) -> ToolExecutionRepository:
    """Get tool execution repository instance."""
    return ToolExecutionRepository(mongodb.get_collection("tool_executions"))


@router.get("/llm/tool-performance")
async def get_tool_performance_metrics(
    days: int = 7,
    limit: int = 50,
    tool_repo: ToolExecutionRepository = Depends(get_tool_execution_repository),
) -> dict[str, Any]:
    """
    Get LLM tool execution performance metrics.

    Returns aggregated performance data for all tools used by the ReAct agent,
    including average execution times, percentiles, success rates, and cache hit rates.

    **Admin only**: Requires admin privileges.

    Args:
        days: Number of days to analyze (default: 7)
        limit: Maximum number of tools to return (default: 50)

    Returns:
        dict: Performance metrics including:
        - period: Start and end dates
        - summary: Overall averages (executions, duration, success rate, cache hit rate)
        - by_tool: Per-tool metrics with percentiles (P50, P95, P99)
    """
    from datetime import timedelta

    end_date = utcnow()
    start_date = end_date - timedelta(days=days)

    logger.info(
        "Tool performance metrics requested",
        days=days,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )

    try:
        metrics = await tool_repo.get_tool_performance_metrics(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        return metrics
    except Exception as e:
        logger.error("Failed to get tool performance metrics", error=str(e))
        return {"status": "error", "message": str(e)}


@router.get("/llm/slowest-tools")
async def get_slowest_tools(
    days: int = 7,
    limit: int = 10,
    tool_repo: ToolExecutionRepository = Depends(get_tool_execution_repository),
) -> dict[str, Any]:
    """
    Get the slowest tools by average execution time.

    Identifies optimization targets by showing tools with highest latency.

    **Admin only**: Requires admin privileges.

    Args:
        days: Number of days to analyze (default: 7)
        limit: Number of tools to return (default: 10)

    Returns:
        list: Slowest tools sorted by avg_duration_ms descending
    """
    from datetime import timedelta

    end_date = utcnow()
    start_date = end_date - timedelta(days=days)

    logger.info(
        "Slowest tools requested",
        days=days,
        limit=limit,
    )

    try:
        slowest = await tool_repo.get_slowest_tools(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        return {"period_days": days, "tools": slowest}
    except Exception as e:
        logger.error("Failed to get slowest tools", error=str(e))
        return {"status": "error", "message": str(e)}


@router.get("/llm/token-usage")
async def get_token_usage_metrics(
    days: int = 7,
    mongodb: MongoDB = Depends(get_mongodb),
) -> dict[str, Any]:
    """
    Get token usage metrics aggregated from message metadata.

    Provides insights into token consumption for cost optimization.

    **Admin only**: Requires admin privileges.

    Args:
        days: Number of days to analyze (default: 7)

    Returns:
        dict: Token usage metrics including:
        - period: Start and end dates
        - summary: Total tokens consumed
        - by_model: Token usage breakdown by LLM model
        - budgets: Current token budget configuration
    """
    from datetime import timedelta

    end_date = utcnow()
    start_date = end_date - timedelta(days=days)

    logger.info(
        "Token usage metrics requested",
        days=days,
    )

    try:
        messages_collection = mongodb.get_collection("messages")

        # Aggregation pipeline for token usage from message metadata
        pipeline: list[dict[str, Any]] = [
            {
                "$match": {
                    "timestamp": {"$gte": start_date, "$lte": end_date},
                    "metadata.tokens": {"$exists": True, "$gt": 0},
                }
            },
            {
                "$group": {
                    "_id": "$metadata.model",
                    "total_messages": {"$sum": 1},
                    "total_tokens": {"$sum": "$metadata.tokens"},
                    "total_input_tokens": {"$sum": "$metadata.input_tokens"},
                    "total_output_tokens": {"$sum": "$metadata.output_tokens"},
                    "avg_tokens_per_message": {"$avg": "$metadata.tokens"},
                }
            },
            {"$sort": {"total_tokens": -1}},
        ]

        results = await messages_collection.aggregate(pipeline).to_list(100)

        # Calculate totals
        total_tokens = sum(r.get("total_tokens", 0) or 0 for r in results)
        total_input = sum(r.get("total_input_tokens", 0) or 0 for r in results)
        total_output = sum(r.get("total_output_tokens", 0) or 0 for r in results)
        total_messages = sum(r.get("total_messages", 0) for r in results)

        # Get current budget settings
        settings = get_settings()

        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": days,
            },
            "summary": {
                "total_messages_with_tokens": total_messages,
                "total_tokens": total_tokens,
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "avg_tokens_per_message": round(
                    total_tokens / total_messages if total_messages > 0 else 0, 2
                ),
            },
            "by_model": [
                {
                    "model": r["_id"] or "unknown",
                    "total_messages": r["total_messages"],
                    "total_tokens": r.get("total_tokens", 0) or 0,
                    "total_input_tokens": r.get("total_input_tokens", 0) or 0,
                    "total_output_tokens": r.get("total_output_tokens", 0) or 0,
                    "avg_tokens_per_message": round(
                        r.get("avg_tokens_per_message", 0) or 0, 2
                    ),
                }
                for r in results
            ],
            "budgets": {
                "chat": settings.token_budget_chat,
                "analysis": settings.token_budget_analysis,
                "portfolio": settings.token_budget_portfolio,
                "summary": settings.token_budget_summary,
                "warning_threshold": settings.token_warning_threshold,
            },
        }
    except Exception as e:
        logger.error("Failed to get token usage metrics", error=str(e))
        return {"status": "error", "message": str(e)}
