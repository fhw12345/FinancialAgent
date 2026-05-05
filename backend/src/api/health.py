"""
Health check endpoints for monitoring and connectivity verification.
Following Factor 9: Error Handling and observability.
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request

from ..core.config import Settings, get_settings
from ..database.mongodb import MongoDB
from ..database.redis import RedisCache

logger = structlog.get_logger()

router = APIRouter()


def get_mongodb(request: Request) -> MongoDB:
    """Dependency to get MongoDB instance from app state."""
    mongodb: MongoDB = request.app.state.mongodb
    return mongodb


def get_redis(request: Request) -> RedisCache:
    """Dependency to get Redis instance from app state."""
    redis: RedisCache = request.app.state.redis
    return redis


@router.get("/health")
async def health_check(
    mongodb: MongoDB = Depends(get_mongodb),
    redis_cache: RedisCache = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """
    Comprehensive health check endpoint.

    Tests connectivity to all critical dependencies:
    - MongoDB database
    - Redis cache
    - Application configuration

    Returns detailed status for each component.
    """
    logger.info("Health check requested")

    # Check MongoDB connection
    mongodb_status = await mongodb.health_check()

    # Check Redis connection
    redis_status = await redis_cache.health_check()

    # Overall system status
    all_healthy = mongodb_status.get("connected", False) and redis_status.get(
        "connected", False
    )

    health_response = {
        "status": "ok" if all_healthy else "degraded",
        "environment": settings.environment,
        "version": "0.1.0",
        "timestamp": datetime.now(UTC).isoformat(),
        "dependencies": {
            "mongodb": mongodb_status,
            "redis": redis_status,
        },
        "configuration": {
            "langfuse_enabled": bool(
                getattr(settings, "langfuse_enabled", False)
                and settings.langfuse_public_key
                and settings.langfuse_secret_key
            ),
            "database_name": settings.database_name,
        },
    }

    if all_healthy:
        logger.info("Health check passed", status="healthy")
    else:
        logger.warning(
            "Health check failed",
            status="degraded",
            dependencies=health_response["dependencies"],
        )

    return health_response


@router.get("/health/mongodb")
async def mongodb_health(mongodb: MongoDB = Depends(get_mongodb)) -> dict[str, Any]:
    """Specific MongoDB health check endpoint."""
    return await mongodb.health_check()


@router.get("/health/redis")
async def redis_health(redis_cache: RedisCache = Depends(get_redis)) -> dict[str, Any]:
    """Specific Redis health check endpoint."""
    return await redis_cache.health_check()


@router.get("/health/ready")
async def readiness_check(
    mongodb: MongoDB = Depends(get_mongodb),
    redis_cache: RedisCache = Depends(get_redis),
) -> dict[str, Any]:
    """
    Kubernetes readiness probe endpoint.

    Returns 200 only when all dependencies are ready to serve traffic.
    """
    mongodb_status = await mongodb.health_check()
    redis_status = await redis_cache.health_check()

    ready = mongodb_status.get("connected", False) and redis_status.get(
        "connected", False
    )

    return {
        "ready": ready,
        "dependencies": {
            "mongodb": mongodb_status.get("connected", False),
            "redis": redis_status.get("connected", False),
        },
    }


@router.get("/health/live")
async def liveness_check() -> dict[str, Any]:
    """
    Kubernetes liveness probe endpoint.

    Simple check that the application is running.
    """
    return {"alive": True, "status": "ok"}
