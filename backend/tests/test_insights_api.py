"""Tests for the Market Insights API endpoints.

Tests cover:
- List categories endpoint
- Get category data endpoint
- Get composite score endpoint
- Get single metric endpoint
- Refresh category endpoint
- Error handling for 404 cases
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.insights.endpoints import router
from src.services.insights import InsightsCategoryRegistry
from src.services.insights.models import (
    CategoryMetadata,
    CompositeScore,
    InsightCategory,
    InsightMetric,
    MetricExplanation,
    MetricStatus,
)


@pytest.fixture
def mock_registry() -> MagicMock:
    """Create mock registry with test data."""
    registry = MagicMock(spec=InsightsCategoryRegistry)

    # Mock list_categories
    registry.list_categories.return_value = [
        CategoryMetadata(
            id="ai_sector_risk",
            name="AI Sector Risk",
            icon="🎯",
            description="Measures bubble risk in AI sector",
            metric_count=6,
            last_updated="2025-01-20T00:00:00Z",
        ),
    ]

    return registry


@pytest.fixture
def mock_category_data() -> InsightCategory:
    """Create mock category data."""
    return InsightCategory(
        id="ai_sector_risk",
        name="AI Sector Risk",
        icon="🎯",
        description="Measures bubble risk in AI sector",
        metrics=[
            InsightMetric(
                id="ai_price_anomaly",
                name="AI Price Anomaly",
                score=65.0,
                status=MetricStatus.ELEVATED,
                explanation=MetricExplanation(
                    summary="Prices 15% above historical average",
                    detail="Analysis shows elevated valuations",
                    methodology="Z-score of 30-day price vs 200-day average",
                    historical_context="Higher than 6-month average",
                    actionable_insight="Consider reducing exposure",
                ),
                data_sources=["Alpha Vantage"],
            ),
        ],
        composite=CompositeScore(
            score=55.0,
            status=MetricStatus.ELEVATED,
            weights={"ai_price_anomaly": 0.2},
            breakdown={"ai_price_anomaly": 13.0},
            interpretation="Elevated risk - monitor positions",
        ),
    )


@pytest.fixture
def mock_snapshot_service():
    from src.services.insights.snapshot_service import InsightsSnapshotService

    service = MagicMock(spec=InsightsSnapshotService)
    service.ensure_indexes = AsyncMock()
    service.create_snapshot = AsyncMock(
        return_value={
            "status": "success",
            "last_updated": "2026-09-09T00:00:00+00:00",
            "prefetch_errors": {},
        }
    )
    return service


@pytest.fixture
def test_app(mock_registry: MagicMock, mock_snapshot_service) -> FastAPI:
    """Create test app with mock registry."""
    app = FastAPI()
    app.state.insights_registry = mock_registry
    app.state.snapshot_service = mock_snapshot_service
    app.include_router(router, prefix="/api/insights")
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(test_app)


class TestListCategories:
    """Tests for GET /api/insights/categories endpoint."""

    def test_list_categories_success(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Test successful category listing."""
        response = client.get("/api/insights/categories")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert len(data["categories"]) == 1
        assert data["categories"][0]["id"] == "ai_sector_risk"
        assert data["categories"][0]["name"] == "AI Sector Risk"

    def test_list_categories_empty(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Test listing when no categories exist."""
        mock_registry.list_categories.return_value = []

        response = client.get("/api/insights/categories")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["categories"] == []


class TestGetCategory:
    """Tests for GET /api/insights/{category_id} endpoint."""

    def test_get_category_success(
        self,
        client: TestClient,
        mock_registry: MagicMock,
        mock_category_data: InsightCategory,
    ) -> None:
        """Test successful category retrieval."""
        mock_registry.get_category_data = AsyncMock(return_value=mock_category_data)

        response = client.get("/api/insights/ai_sector_risk")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "ai_sector_risk"
        assert data["name"] == "AI Sector Risk"
        assert len(data["metrics"]) == 1
        assert data["composite"]["score"] == 55.0

    def test_get_category_not_found(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Test 404 when category doesn't exist."""
        mock_registry.get_category_data = AsyncMock(return_value=None)

        response = client.get("/api/insights/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_category_force_refresh(
        self,
        client: TestClient,
        mock_registry: MagicMock,
        mock_category_data: InsightCategory,
    ) -> None:
        """Test force refresh parameter."""
        mock_registry.get_category_data = AsyncMock(return_value=mock_category_data)

        response = client.get("/api/insights/ai_sector_risk?force_refresh=true")

        assert response.status_code == 200
        mock_registry.get_category_data.assert_called_once_with(
            "ai_sector_risk", force_refresh=True
        )


class TestGetComposite:
    """Tests for GET /api/insights/{category_id}/composite endpoint."""

    def test_get_composite_success(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Test successful composite score retrieval."""
        mock_instance = MagicMock()
        mock_instance.get_composite = AsyncMock(
            return_value=CompositeScore(
                score=55.0,
                status=MetricStatus.ELEVATED,
                weights={"ai_price_anomaly": 0.2},
                breakdown={"ai_price_anomaly": 13.0},
                interpretation="Elevated risk",
            )
        )
        mock_registry.get_category_instance.return_value = mock_instance

        response = client.get("/api/insights/ai_sector_risk/composite")

        assert response.status_code == 200
        data = response.json()
        assert data["score"] == 55.0
        assert data["status"] == "elevated"

    def test_get_composite_not_found(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Test 404 when category doesn't exist."""
        mock_registry.get_category_instance.return_value = None

        response = client.get("/api/insights/nonexistent/composite")

        assert response.status_code == 404


class TestGetMetric:
    """Tests for GET /api/insights/{category_id}/{metric_id} endpoint."""

    def test_get_metric_success(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Test successful metric retrieval."""
        mock_instance = MagicMock()
        mock_instance.get_metric = AsyncMock(
            return_value=InsightMetric(
                id="ai_price_anomaly",
                name="AI Price Anomaly",
                score=65.0,
                status=MetricStatus.ELEVATED,
                explanation=MetricExplanation(
                    summary="Prices elevated",
                    detail="Analysis details",
                    methodology="Z-score calculation",
                    historical_context="Higher than average",
                    actionable_insight="Consider reducing exposure",
                ),
                data_sources=["Alpha Vantage"],
            )
        )
        mock_registry.get_category_instance.return_value = mock_instance

        response = client.get("/api/insights/ai_sector_risk/ai_price_anomaly")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "ai_price_anomaly"
        assert data["score"] == 65.0

    def test_get_metric_category_not_found(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Test 404 when category doesn't exist."""
        mock_registry.get_category_instance.return_value = None

        response = client.get("/api/insights/nonexistent/ai_price_anomaly")

        assert response.status_code == 404
        assert "category" in response.json()["detail"].lower()

    def test_get_metric_metric_not_found(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Test 404 when metric doesn't exist."""
        mock_instance = MagicMock()
        mock_instance.get_metric = AsyncMock(return_value=None)
        mock_registry.get_category_instance.return_value = mock_instance

        response = client.get("/api/insights/ai_sector_risk/nonexistent")

        assert response.status_code == 404
        assert "metric" in response.json()["detail"].lower()


class TestRefreshCategory:
    """Tests for POST /api/insights/{category_id}/refresh endpoint."""

    def test_refresh_success(
        self,
        client: TestClient,
        mock_registry: MagicMock,
        mock_snapshot_service,
    ) -> None:
        """Visible refresh invokes persisted snapshot creation, not registry-only refresh."""

        response = client.post("/api/insights/ai_sector_risk/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["category_id"] == "ai_sector_risk"
        assert "refreshed" in data["message"].lower()
        mock_snapshot_service.create_snapshot.assert_awaited_once_with("ai_sector_risk")
        mock_registry.refresh_category.assert_not_called()

    def test_refresh_not_found(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Test 404 when category doesn't exist."""
        mock_registry.get_category_instance.return_value = None

        response = client.post("/api/insights/nonexistent/refresh")

        assert response.status_code == 404

    def test_snapshot_failure_is_not_success(self, client, mock_snapshot_service):
        mock_snapshot_service.create_snapshot.return_value = {"status": "error"}
        assert client.post("/api/insights/ai_sector_risk/refresh").status_code == 500

    def test_prefetch_degradation_is_explicit(self, client, mock_snapshot_service):
        mock_snapshot_service.create_snapshot.return_value["prefetch_errors"] = {
            "news:technology": "offline"
        }
        response = client.post("/api/insights/ai_sector_risk/refresh")
        assert response.status_code == 200
        assert response.json()["prefetch_errors"] == {"news:technology": "offline"}


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_category_id_with_special_chars(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Test handling of special characters in category ID."""
        mock_registry.get_category_data = AsyncMock(return_value=None)

        response = client.get("/api/insights/invalid%20id")

        # Should return 404, not crash
        assert response.status_code == 404

    def test_internal_error_handling(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Test 500 error on internal exception."""
        mock_registry.get_category_data = AsyncMock(
            side_effect=Exception("Database error")
        )

        response = client.get("/api/insights/ai_sector_risk")

        assert response.status_code == 500
        assert "failed" in response.json()["detail"].lower()

    def test_list_categories_error(
        self, client: TestClient, mock_registry: MagicMock
    ) -> None:
        """Test 500 error on list categories failure."""
        mock_registry.list_categories.side_effect = Exception("Connection error")

        response = client.get("/api/insights/categories")

        assert response.status_code == 500
