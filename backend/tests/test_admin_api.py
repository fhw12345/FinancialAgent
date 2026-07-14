"""Tests for the local administration endpoints."""

from unittest.mock import AsyncMock

import pytest

from src.api.admin import get_database_stats, get_system_health, get_timing_metrics
from src.api.dependencies.timing_middleware import TimingMiddleware
from src.api.schemas.admin_models import DatabaseStats


@pytest.fixture
def database_stats() -> list[DatabaseStats]:
    return [
        DatabaseStats(
            collection="messages",
            document_count=10,
            size_bytes=2048,
            size_mb=0.002,
            avg_document_size_bytes=204,
        )
    ]


@pytest.mark.asyncio
async def test_system_health_returns_database_metrics(database_stats):
    service = AsyncMock()
    service.get_collection_stats.return_value = database_stats

    result = await get_system_health(service)

    assert result.health_status == "healthy"
    assert result.database == database_stats


@pytest.mark.asyncio
async def test_database_stats_endpoint(database_stats):
    service = AsyncMock()
    service.get_collection_stats.return_value = database_stats

    assert await get_database_stats(service) == database_stats


@pytest.mark.asyncio
async def test_timing_metrics_sorted_by_p95(monkeypatch):
    monkeypatch.setattr(
        TimingMiddleware,
        "get_all_metrics",
        lambda: {
            "/fast": {"p95": 10.0},
            "/slow": {"p95": 250.0},
        },
    )

    result = await get_timing_metrics()

    assert list(result) == ["/slow", "/fast"]
