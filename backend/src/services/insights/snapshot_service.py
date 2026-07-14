"""Insights Snapshot Service.

Handles automated daily collection of insight metrics with MongoDB persistence
and Redis cache updates. Triggered by local refresh/admin endpoints.

Architecture:
- Phase 1: Pre-fetch all shared data (parallel via DML)
- Phase 2: Calculate metrics in parallel with shared data
- Phase 3: Batch persist to MongoDB + Redis
"""

import time
from datetime import UTC, datetime
from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorCollection

from ...core.config import Settings
from ...database.mongodb import MongoDB
from ...database.redis import RedisCache
from ..data_manager import CacheKeys, DataManager
from ..market_data import FREDService
from .models import CompositeScore, InsightMetric
from .registry import InsightsCategoryRegistry

logger = structlog.get_logger()

# MongoDB collection name for snapshots
SNAPSHOTS_COLLECTION = "insight_snapshots"

# TTL for Redis cache (24 hours)
SNAPSHOT_REDIS_TTL = 86400


def _get_status_from_score(score: float) -> str:
    """Convert score to status string."""
    if score < 25:
        return "low"
    elif score < 50:
        return "normal"
    elif score < 75:
        return "elevated"
    else:
        return "high"


class InsightsSnapshotService:
    """Service for creating and persisting insight snapshots.

    Uses DataManager (DML) as single source of truth for all data access.
    Calculates all 6 metrics in parallel and persists to MongoDB/Redis.
    """

    def __init__(
        self,
        mongodb: MongoDB,
        redis_cache: RedisCache,
        data_manager: DataManager,
        settings: Settings,
        registry: InsightsCategoryRegistry | None = None,
    ) -> None:
        """Initialize snapshot service.

        Args:
            mongodb: MongoDB connection for persistence
            redis_cache: Redis cache for fast access
            data_manager: DataManager (DML) for data fetching
            settings: Application settings
            registry: Optional insights registry (created if not provided)
        """
        self.mongodb = mongodb
        self.redis_cache = redis_cache
        self.data_manager = data_manager
        self.settings = settings
        self._registry = registry

    @property
    def registry(self) -> InsightsCategoryRegistry:
        """Get or create insights registry."""
        if self._registry is None:
            # Create FRED service if API key is available
            fred_service = None
            if self.settings.fred_api_key:
                fred_service = FREDService(api_key=self.settings.fred_api_key)

            self._registry = InsightsCategoryRegistry(
                settings=self.settings,
                redis_cache=self.redis_cache,
                fred_service=fred_service,
            )
        return self._registry

    def _get_snapshots_collection(self) -> AsyncIOMotorCollection:
        """Get MongoDB collection for snapshots."""
        return self.mongodb.get_collection(SNAPSHOTS_COLLECTION)

    async def ensure_indexes(self) -> None:
        """Ensure required MongoDB indexes exist."""
        collection = self._get_snapshots_collection()

        # Compound index for efficient trend queries
        await collection.create_index(
            [("category_id", 1), ("date", -1)],
            name="category_date_idx",
            unique=True,
        )

        logger.info(
            "Snapshot indexes ensured",
            collection=SNAPSHOTS_COLLECTION,
        )

    async def create_snapshot(
        self,
        category_id: str = "ai_sector_risk",
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a snapshot for a category.

        This is the main entry point for snapshot creation.
        Uses 3-phase architecture:
        1. Pre-fetch shared data via DML
        2. Calculate metrics in parallel
        3. Persist to MongoDB + Redis

        Args:
            category_id: Category to snapshot (default: ai_sector_risk)
            run_id: Optional run identifier for logging

        Returns:
            Snapshot result with timing and status
        """
        run_id = run_id or f"snapshot_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
        start_time = time.time()

        logger.info(
            "Starting snapshot creation",
            run_id=run_id,
            category_id=category_id,
        )

        try:
            # Get category instance
            category = self.registry.get_category_instance(category_id)
            if not category:
                raise ValueError(f"Category not found: {category_id}")

            # Phase 1: Pre-fetch shared data via DML
            phase1_start = time.time()
            shared_data = await self._prefetch_shared_data()
            phase1_duration = time.time() - phase1_start

            logger.info(
                "Phase 1 complete: Pre-fetch",
                run_id=run_id,
                duration_seconds=round(phase1_duration, 2),
                data_keys=list(shared_data.keys()) if shared_data else [],
            )

            # Phase 2: Calculate metrics and composite via get_category_data
            phase2_start = time.time()
            category_data = await category.get_category_data(force_refresh=True)
            metrics = category_data.metrics
            composite = category_data.composite
            phase2_duration = time.time() - phase2_start

            logger.info(
                "Phase 2 complete: Calculate",
                run_id=run_id,
                duration_seconds=round(phase2_duration, 2),
                metric_count=len(metrics),
                composite_score=composite.score if composite else None,
            )

            # Phase 3: Persist to MongoDB + Redis
            phase3_start = time.time()
            snapshot_doc = await self._persist_snapshot(
                category_id=category_id,
                metrics=metrics,
                composite=composite,
            )
            phase3_duration = time.time() - phase3_start

            logger.info(
                "Phase 3 complete: Persist",
                run_id=run_id,
                duration_seconds=round(phase3_duration, 2),
            )

            total_duration = time.time() - start_time

            result = {
                "status": "success",
                "run_id": run_id,
                "category_id": category_id,
                "date": snapshot_doc["date"].isoformat(),
                "composite_score": composite.score,
                "composite_status": composite.status.value,
                "metric_count": len(metrics),
                "timing": {
                    "phase1_prefetch_seconds": round(phase1_duration, 2),
                    "phase2_calculate_seconds": round(phase2_duration, 2),
                    "phase3_persist_seconds": round(phase3_duration, 2),
                    "total_seconds": round(total_duration, 2),
                },
            }

            logger.info(
                "Snapshot creation complete",
                **result,
            )

            return result

        except Exception as e:
            total_duration = time.time() - start_time
            logger.error(
                "Snapshot creation failed",
                run_id=run_id,
                category_id=category_id,
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(total_duration, 2),
            )
            return {
                "status": "error",
                "run_id": run_id,
                "category_id": category_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "timing": {
                    "total_seconds": round(total_duration, 2),
                },
            }

    async def _prefetch_shared_data(self) -> dict[str, Any]:
        """Pre-fetch all shared data via DataManager.

        Uses asyncio.gather for parallel fetching.
        Treasury 2Y is fetched once and shared between yield_curve and fed_expectations.

        Returns:
            Shared data context dict
        """
        # Define what we need for AI Sector Risk metrics
        symbols = ["NVDA", "MSFT", "AMD", "PLTR"]  # AI basket
        indicators = ["treasury_2y", "treasury_10y"]

        try:
            # Use DML prefetch_shared for parallel fetching
            shared_context = await self.data_manager.prefetch_shared(
                symbols=symbols,
                indicators=indicators,
                include_news=True,
                include_ipo=True,
            )

            logger.info(
                "Shared data prefetched",
                ohlcv_count=len(shared_context.ohlcv),
                treasury_count=len(shared_context.treasury),
                has_news=len(shared_context.news) > 0,
                has_ipo=len(shared_context.ipo) > 0,
            )

            return {
                "ohlcv": shared_context.ohlcv,
                "treasury": shared_context.treasury,
                "news": shared_context.news,
                "ipo": shared_context.ipo,
            }

        except Exception as e:
            logger.warning(
                "Prefetch partial failure, continuing with available data",
                error=str(e),
            )
            return {}

    async def _persist_snapshot(
        self,
        category_id: str,
        metrics: list[InsightMetric],
        composite: CompositeScore,
    ) -> dict[str, Any]:
        """Persist snapshot to MongoDB and update Redis cache.

        Args:
            category_id: Category identifier
            metrics: List of calculated metrics
            composite: Composite score

        Returns:
            Persisted document
        """
        now = datetime.now(UTC)
        date_only = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Build document
        metrics_dict = {}
        for metric in metrics:
            metrics_dict[metric.id] = {
                "score": metric.score,
                "status": metric.status.value,
            }

        doc = {
            "category_id": category_id,
            "date": date_only,
            "composite_score": composite.score,
            "composite_status": composite.status.value,
            "metrics": metrics_dict,
            "created_at": now,
        }

        # Upsert to MongoDB (replace if same date exists)
        collection = self._get_snapshots_collection()
        await collection.update_one(
            {"category_id": category_id, "date": date_only},
            {"$set": doc},
            upsert=True,
        )

        logger.info(
            "Snapshot saved to MongoDB",
            category_id=category_id,
            date=date_only.isoformat(),
            composite_score=composite.score,
        )

        # Update Redis cache
        cache_key = CacheKeys.insights(category_id, "latest")
        cache_doc = {
            "category_id": category_id,
            "date": date_only.isoformat(),
            "composite_score": composite.score,
            "composite_status": composite.status.value,
            "metrics": metrics_dict,
            "cached_at": now.isoformat(),
        }

        await self.redis_cache.set(cache_key, cache_doc, ttl_seconds=SNAPSHOT_REDIS_TTL)

        logger.info(
            "Snapshot cached in Redis",
            cache_key=cache_key,
            ttl_seconds=SNAPSHOT_REDIS_TTL,
        )

        return doc

    async def get_latest_snapshot(
        self,
        category_id: str = "ai_sector_risk",
    ) -> dict[str, Any] | None:
        """Get the latest snapshot from cache or MongoDB.

        Args:
            category_id: Category to get

        Returns:
            Latest snapshot or None
        """
        # Try Redis first
        cache_key = CacheKeys.insights(category_id, "latest")
        cached = await self.redis_cache.get(cache_key)
        if cached:
            logger.debug(
                "Snapshot cache HIT",
                category_id=category_id,
            )
            return cached

        # Fall back to MongoDB
        collection = self._get_snapshots_collection()
        doc = await collection.find_one(
            {"category_id": category_id},
            sort=[("date", -1)],
        )

        if doc:
            # Remove MongoDB _id for JSON serialization
            doc.pop("_id", None)
            # Convert datetime to string
            if "date" in doc and hasattr(doc["date"], "isoformat"):
                doc["date"] = doc["date"].isoformat()
            if "created_at" in doc and hasattr(doc["created_at"], "isoformat"):
                doc["created_at"] = doc["created_at"].isoformat()

            logger.debug(
                "Snapshot from MongoDB",
                category_id=category_id,
            )

        return doc

    async def get_trend(
        self,
        category_id: str = "ai_sector_risk",
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Get trend data for a category.

        Args:
            category_id: Category to query
            days: Number of days of history

        Returns:
            List of snapshots ordered by date descending
        """
        collection = self._get_snapshots_collection()

        cursor = collection.find(
            {"category_id": category_id},
            sort=[("date", -1)],
            limit=days,
        )

        snapshots = []
        async for doc in cursor:
            doc.pop("_id", None)
            if "date" in doc and hasattr(doc["date"], "isoformat"):
                doc["date"] = doc["date"].isoformat()
            if "created_at" in doc and hasattr(doc["created_at"], "isoformat"):
                doc["created_at"] = doc["created_at"].isoformat()
            snapshots.append(doc)

        logger.info(
            "Trend data retrieved",
            category_id=category_id,
            requested_days=days,
            returned_days=len(snapshots),
        )

        return snapshots
