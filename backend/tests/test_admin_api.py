"""
Unit tests for Admin API endpoints.

Tests admin health check, database stats, timing metrics, and background task triggers.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

from src.api.admin import (
    get_cache_warming_service,
    get_data_manager,
    get_database_stats_service,
    get_insights_registry,
    get_kubernetes_metrics_service,
    get_tool_execution_repository,
    router,
)
from src.api.dependencies.auth import (
    get_current_user,
    get_mongodb,
    get_redis_cache,
    require_admin,
)
from src.api.schemas.admin_models import DatabaseStats, NodeMetrics, PodMetrics
from src.models.user import User


# ===== Fixtures =====


@pytest.fixture
def mock_admin_user():
    """Mock admin User object."""
    user = Mock(spec=User)
    user.user_id = "admin_123"
    user.username = "admin"
    user.email = "admin@example.com"
    user.role = "admin"
    return user


@pytest.fixture
def mock_mongodb():
    """Mock MongoDB instance."""
    mongodb = Mock()
    mock_collection = Mock()
    mock_collection.aggregate = Mock()
    mongodb.get_collection = Mock(return_value=mock_collection)
    mongodb.database = Mock()
    return mongodb


@pytest.fixture
def mock_redis():
    """Mock Redis instance."""
    redis = Mock()
    redis.get_cache_stats = AsyncMock(
        return_value={
            "memory": {"used": "100MB", "peak": "200MB"},
            "keys": {"total": 1000},
            "cache_efficiency": {"hit_ratio": 0.85},
        }
    )
    return redis


@pytest.fixture
def mock_db_stats_service():
    """Mock DatabaseStatsService."""
    service = Mock()
    service.get_collection_stats = AsyncMock(
        return_value=[
            DatabaseStats(
                collection="users",
                document_count=100,
                size_bytes=10240,
                size_mb=0.01,
                avg_document_size_bytes=102,
            ),
            DatabaseStats(
                collection="messages",
                document_count=5000,
                size_bytes=512000,
                size_mb=0.5,
                avg_document_size_bytes=102,
            ),
        ]
    )
    return service


@pytest.fixture
def mock_k8s_service():
    """Mock KubernetesMetricsService."""
    service = Mock()
    service.available = False  # Default to unavailable for simpler tests
    service.get_pod_metrics = AsyncMock(return_value=[])
    service.get_node_metrics = AsyncMock(return_value=[])
    return service


@pytest.fixture
def mock_tool_repo():
    """Mock ToolExecutionRepository."""
    repo = Mock()
    repo.get_tool_performance_metrics = AsyncMock(
        return_value={
            "summary": {"total_executions": 100, "avg_duration_ms": 250},
            "by_tool": [],
        }
    )
    repo.get_slowest_tools = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_cache_warming_service():
    """Mock CacheWarmingService."""
    service = Mock()
    service.DEFAULT_SYMBOLS = ["AAPL", "GOOGL", "MSFT"]
    service.warm_startup_cache = AsyncMock()
    service.warm_market_movers = AsyncMock()
    service.get_warming_status = AsyncMock(
        return_value={"status": "idle", "last_run": None}
    )
    return service


@pytest.fixture
def client(
    mock_admin_user,
    mock_mongodb,
    mock_redis,
    mock_db_stats_service,
    mock_k8s_service,
    mock_tool_repo,
):
    """Create test client with mocked dependencies."""
    app = FastAPI()
    app.include_router(router)

    # Override dependencies
    app.dependency_overrides[require_admin] = lambda: mock_admin_user
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[get_mongodb] = lambda: mock_mongodb
    app.dependency_overrides[get_redis_cache] = lambda: mock_redis
    app.dependency_overrides[get_database_stats_service] = lambda: mock_db_stats_service
    app.dependency_overrides[get_kubernetes_metrics_service] = lambda: mock_k8s_service
    app.dependency_overrides[get_tool_execution_repository] = lambda: mock_tool_repo

    return TestClient(app)


# ===== Dependency Factory Tests =====


class TestDependencyFactories:
    """Test dependency factory functions."""

    def test_get_database_stats_service(self, mock_mongodb):
        """Test database stats service creation."""
        service = get_database_stats_service(mock_mongodb)
        assert service is not None

    def test_get_kubernetes_metrics_service(self):
        """Test K8s metrics service creation."""
        with patch("src.api.admin.get_settings") as mock_settings:
            mock_settings.return_value.kubernetes_namespace = "test-namespace"
            service = get_kubernetes_metrics_service()
            assert service is not None

    def test_get_data_manager(self):
        """Test data manager retrieval from request."""
        mock_request = Mock()
        mock_dm = Mock()
        mock_request.app.state.data_manager = mock_dm

        result = get_data_manager(mock_request)
        assert result is mock_dm

    def test_get_data_manager_not_initialized(self):
        """Test data manager returns None if not set."""
        mock_request = Mock()
        mock_request.app.state = Mock(spec=[])  # No data_manager attribute

        result = get_data_manager(mock_request)
        assert result is None

    def test_get_insights_registry(self):
        """Test insights registry retrieval from request."""
        mock_request = Mock()
        mock_registry = Mock()
        mock_request.app.state.insights_registry = mock_registry

        result = get_insights_registry(mock_request)
        assert result is mock_registry

    def test_get_cache_warming_service(self):
        """Test cache warming service retrieval from request."""
        mock_request = Mock()
        mock_service = Mock()
        mock_request.app.state.cache_warming_service = mock_service

        result = get_cache_warming_service(mock_request)
        assert result is mock_service


# ===== get_system_health Tests =====


class TestGetSystemHealth:
    """Test get_system_health endpoint."""

    def test_health_no_k8s(self, client, mock_db_stats_service, mock_k8s_service):
        """Test health check when K8s is unavailable."""
        mock_k8s_service.available = False

        response = client.get("/api/admin/health")

        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data
        assert "database" in data
        assert data["kubernetes_available"] is False
        assert data["health_status"] == "healthy"

    def test_health_with_k8s(self, client, mock_db_stats_service, mock_k8s_service):
        """Test health check when K8s is available."""
        mock_k8s_service.available = True

        pod_metrics = PodMetrics(
            name="backend-pod",
            cpu_usage="150m",
            memory_usage="256Mi",
            cpu_percentage=50.0,
            memory_percentage=60.0,
        )
        mock_k8s_service.get_pod_metrics.return_value = [pod_metrics]

        node_metrics = NodeMetrics(
            name="node-1",
            cpu_usage="500m",
            memory_usage="2Gi",
            cpu_capacity="2000m",
            memory_capacity="8Gi",
            cpu_percentage=25.0,
            memory_percentage=25.0,
        )
        mock_k8s_service.get_node_metrics.return_value = [node_metrics]

        response = client.get("/api/admin/health")

        assert response.status_code == 200
        data = response.json()
        assert data["kubernetes_available"] is True
        assert len(data["pods"]) == 1
        assert len(data["nodes"]) == 1

    def test_health_warning_status(self, client, mock_k8s_service):
        """Test health check returns warning when resources high."""
        mock_k8s_service.available = True

        pod_metrics = PodMetrics(
            name="backend-pod",
            cpu_usage="750m",
            memory_usage="256Mi",
            cpu_percentage=75.0,  # Above 70% threshold
            memory_percentage=60.0,
        )
        mock_k8s_service.get_pod_metrics.return_value = [pod_metrics]
        mock_k8s_service.get_node_metrics.return_value = []

        response = client.get("/api/admin/health")

        assert response.status_code == 200
        data = response.json()
        assert data["health_status"] == "warning"

    def test_health_critical_status(self, client, mock_k8s_service):
        """Test health check returns critical when resources very high."""
        mock_k8s_service.available = True

        pod_metrics = PodMetrics(
            name="backend-pod",
            cpu_usage="950m",
            memory_usage="256Mi",
            cpu_percentage=95.0,  # Above 90% threshold
            memory_percentage=60.0,
        )
        mock_k8s_service.get_pod_metrics.return_value = [pod_metrics]
        mock_k8s_service.get_node_metrics.return_value = []

        response = client.get("/api/admin/health")

        assert response.status_code == 200
        data = response.json()
        assert data["health_status"] == "critical"

    def test_health_k8s_error(self, client, mock_k8s_service):
        """Test health check handles K8s errors gracefully."""
        mock_k8s_service.available = True
        mock_k8s_service.get_pod_metrics.side_effect = Exception("K8s error")

        response = client.get("/api/admin/health")

        assert response.status_code == 200
        data = response.json()
        assert data["kubernetes_available"] is False  # Should be marked unavailable


# ===== get_database_stats Tests =====


class TestGetDatabaseStats:
    """Test get_database_stats endpoint."""

    def test_get_database_stats(self, client, mock_db_stats_service):
        """Test getting database statistics."""
        response = client.get("/api/admin/database")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["collection"] == "users"
        assert data[1]["collection"] == "messages"


# ===== get_timing_metrics Tests =====


class TestGetTimingMetrics:
    """Test get_timing_metrics endpoint."""

    def test_get_timing_metrics(self, client):
        """Test getting timing metrics."""
        with patch("src.api.admin.TimingMiddleware") as mock_middleware:
            mock_middleware.get_all_metrics.return_value = {
                "/api/chat": {"p50": 100, "p95": 250, "p99": 500, "count": 1000},
                "/api/health": {"p50": 10, "p95": 25, "p99": 50, "count": 5000},
            }

            response = client.get("/api/admin/timing-metrics")

            assert response.status_code == 200
            data = response.json()
            assert "/api/chat" in data
            assert "/api/health" in data
            # Should be sorted by P95 descending
            keys = list(data.keys())
            assert keys[0] == "/api/chat"  # Higher P95 first

    def test_get_timing_metrics_empty(self, client):
        """Test getting timing metrics when empty."""
        with patch("src.api.admin.TimingMiddleware") as mock_middleware:
            mock_middleware.get_all_metrics.return_value = {}

            response = client.get("/api/admin/timing-metrics")

            assert response.status_code == 200
            assert response.json() == {}


# ===== trigger_insights_snapshot Tests =====


class TestTriggerInsightsSnapshot:
    """Test trigger_insights_snapshot endpoint."""

    def test_trigger_snapshot_no_data_manager(
        self, mock_admin_user, mock_mongodb, mock_redis
    ):
        """Test snapshot trigger when data manager not initialized."""
        app = FastAPI()
        app.include_router(router)
        app.state = Mock(spec=[])  # No data_manager

        app.dependency_overrides[require_admin] = lambda: mock_admin_user
        app.dependency_overrides[get_mongodb] = lambda: mock_mongodb
        app.dependency_overrides[get_redis_cache] = lambda: mock_redis

        client = TestClient(app)
        response = client.post("/api/admin/insights/trigger-snapshot")

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "error"
        assert "DataManager not initialized" in data["message"]

    def test_trigger_snapshot_success(
        self, mock_admin_user, mock_mongodb, mock_redis
    ):
        """Test snapshot trigger when properly initialized."""
        app = FastAPI()
        app.include_router(router)

        # Set up app state with mocks
        mock_data_manager = Mock()
        mock_registry = Mock()
        app.state.data_manager = mock_data_manager
        app.state.insights_registry = mock_registry

        app.dependency_overrides[require_admin] = lambda: mock_admin_user
        app.dependency_overrides[get_mongodb] = lambda: mock_mongodb
        app.dependency_overrides[get_redis_cache] = lambda: mock_redis

        client = TestClient(app)
        response = client.post("/api/admin/insights/trigger-snapshot")

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "started"
        assert "run_id" in data
        assert data["run_id"].startswith("snapshot_")


# ===== Cache Warming Endpoints Tests =====


class TestCacheWarmingEndpoints:
    """Test cache warming endpoints."""

    def test_warm_cache_not_initialized(self, mock_admin_user, mock_mongodb, mock_redis):
        """Test warm cache when service not initialized."""
        app = FastAPI()
        app.include_router(router)
        app.state = Mock(spec=[])  # No cache_warming_service

        app.dependency_overrides[require_admin] = lambda: mock_admin_user

        client = TestClient(app)
        response = client.post("/api/admin/cache/warm")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not initialized" in data["message"]

    def test_warm_cache_success(
        self, mock_admin_user, mock_cache_warming_service
    ):
        """Test successful cache warming trigger."""
        app = FastAPI()
        app.include_router(router)
        app.state.cache_warming_service = mock_cache_warming_service

        app.dependency_overrides[require_admin] = lambda: mock_admin_user

        client = TestClient(app)
        response = client.post("/api/admin/cache/warm")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert "symbols" in data
        assert data["symbols"] == ["AAPL", "GOOGL", "MSFT"]

    def test_warm_market_movers_not_initialized(
        self, mock_admin_user
    ):
        """Test market movers warming when service not initialized."""
        app = FastAPI()
        app.include_router(router)
        app.state = Mock(spec=[])

        app.dependency_overrides[require_admin] = lambda: mock_admin_user

        client = TestClient(app)
        response = client.post("/api/admin/cache/warm-market-movers")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

    def test_warm_market_movers_success(
        self, mock_admin_user, mock_cache_warming_service
    ):
        """Test successful market movers warming trigger."""
        app = FastAPI()
        app.include_router(router)
        app.state.cache_warming_service = mock_cache_warming_service

        app.dependency_overrides[require_admin] = lambda: mock_admin_user

        client = TestClient(app)
        response = client.post("/api/admin/cache/warm-market-movers")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"

    def test_get_warming_status_not_initialized(self, mock_admin_user):
        """Test warming status when service not initialized."""
        app = FastAPI()
        app.include_router(router)
        app.state = Mock(spec=[])

        app.dependency_overrides[require_admin] = lambda: mock_admin_user

        client = TestClient(app)
        response = client.get("/api/admin/cache/warming-status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

    def test_get_warming_status_success(
        self, mock_admin_user, mock_cache_warming_service
    ):
        """Test getting warming status."""
        app = FastAPI()
        app.include_router(router)
        app.state.cache_warming_service = mock_cache_warming_service

        app.dependency_overrides[require_admin] = lambda: mock_admin_user

        client = TestClient(app)
        response = client.get("/api/admin/cache/warming-status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "idle"


# ===== Cache Stats Tests =====


class TestGetCacheStats:
    """Test get_cache_stats endpoint."""

    def test_get_cache_stats(self, client, mock_redis):
        """Test getting cache statistics."""
        response = client.get("/api/admin/cache/stats")

        assert response.status_code == 200
        data = response.json()
        assert "memory" in data
        assert "cache_efficiency" in data
        mock_redis.get_cache_stats.assert_called_once()

    def test_get_cache_stats_error(self, client, mock_redis):
        """Test cache stats error handling."""
        mock_redis.get_cache_stats.side_effect = Exception("Redis error")

        response = client.get("/api/admin/cache/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "Redis error" in data["message"]


# ===== LLM/Tool Performance Tests =====


class TestLLMToolPerformance:
    """Test LLM tool performance endpoints."""

    def test_get_tool_performance_metrics(self, client, mock_tool_repo):
        """Test getting tool performance metrics."""
        response = client.get("/api/admin/llm/tool-performance")

        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        mock_tool_repo.get_tool_performance_metrics.assert_called_once()

    def test_get_tool_performance_with_params(self, client, mock_tool_repo):
        """Test tool performance with custom parameters."""
        response = client.get("/api/admin/llm/tool-performance?days=14&limit=25")

        assert response.status_code == 200
        mock_tool_repo.get_tool_performance_metrics.assert_called_once()
        # Verify limit parameter was passed
        call_args = mock_tool_repo.get_tool_performance_metrics.call_args
        assert call_args.kwargs["limit"] == 25

    def test_get_tool_performance_error(self, client, mock_tool_repo):
        """Test tool performance error handling."""
        mock_tool_repo.get_tool_performance_metrics.side_effect = Exception("DB error")

        response = client.get("/api/admin/llm/tool-performance")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

    def test_get_slowest_tools(self, client, mock_tool_repo):
        """Test getting slowest tools."""
        mock_tool_repo.get_slowest_tools.return_value = [
            {"tool_name": "get_stock_data", "avg_duration_ms": 500},
            {"tool_name": "get_news", "avg_duration_ms": 300},
        ]

        response = client.get("/api/admin/llm/slowest-tools")

        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert "period_days" in data
        assert len(data["tools"]) == 2

    def test_get_slowest_tools_with_params(self, client, mock_tool_repo):
        """Test slowest tools with custom parameters."""
        response = client.get("/api/admin/llm/slowest-tools?days=30&limit=5")

        assert response.status_code == 200
        call_args = mock_tool_repo.get_slowest_tools.call_args
        assert call_args.kwargs["limit"] == 5

    def test_get_slowest_tools_error(self, client, mock_tool_repo):
        """Test slowest tools error handling."""
        mock_tool_repo.get_slowest_tools.side_effect = Exception("Query failed")

        response = client.get("/api/admin/llm/slowest-tools")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"


# ===== Token Usage Tests =====


class TestTokenUsage:
    """Test token usage endpoint."""

    def test_get_token_usage(self, client, mock_mongodb):
        """Test getting token usage metrics."""
        # Set up mock aggregation result
        mock_cursor = Mock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": "qwen-max",
                    "total_messages": 100,
                    "total_tokens": 50000,
                    "total_input_tokens": 30000,
                    "total_output_tokens": 20000,
                    "avg_tokens_per_message": 500.0,
                }
            ]
        )
        mock_mongodb.get_collection.return_value.aggregate.return_value = mock_cursor

        with patch("src.api.admin.get_settings") as mock_settings:
            mock_settings.return_value.token_budget_chat = 10000
            mock_settings.return_value.token_budget_analysis = 20000
            mock_settings.return_value.token_budget_portfolio = 30000
            mock_settings.return_value.token_budget_summary = 5000
            mock_settings.return_value.token_warning_threshold = 0.8

            response = client.get("/api/admin/llm/token-usage")

        assert response.status_code == 200
        data = response.json()
        assert "period" in data
        assert "summary" in data
        assert "by_model" in data
        assert "budgets" in data
        assert data["summary"]["total_tokens"] == 50000

    def test_get_token_usage_with_days_param(self, client, mock_mongodb):
        """Test token usage with custom days parameter."""
        mock_cursor = Mock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_mongodb.get_collection.return_value.aggregate.return_value = mock_cursor

        with patch("src.api.admin.get_settings") as mock_settings:
            mock_settings.return_value.token_budget_chat = 10000
            mock_settings.return_value.token_budget_analysis = 20000
            mock_settings.return_value.token_budget_portfolio = 30000
            mock_settings.return_value.token_budget_summary = 5000
            mock_settings.return_value.token_warning_threshold = 0.8

            response = client.get("/api/admin/llm/token-usage?days=30")

        assert response.status_code == 200
        data = response.json()
        assert data["period"]["days"] == 30

    def test_get_token_usage_error(self, client, mock_mongodb):
        """Test token usage error handling."""
        mock_mongodb.get_collection.return_value.aggregate.side_effect = Exception(
            "Aggregation failed"
        )

        response = client.get("/api/admin/llm/token-usage")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

    def test_get_token_usage_empty_results(self, client, mock_mongodb):
        """Test token usage with no data."""
        mock_cursor = Mock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_mongodb.get_collection.return_value.aggregate.return_value = mock_cursor

        with patch("src.api.admin.get_settings") as mock_settings:
            mock_settings.return_value.token_budget_chat = 10000
            mock_settings.return_value.token_budget_analysis = 20000
            mock_settings.return_value.token_budget_portfolio = 30000
            mock_settings.return_value.token_budget_summary = 5000
            mock_settings.return_value.token_warning_threshold = 0.8

            response = client.get("/api/admin/llm/token-usage")

        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["total_tokens"] == 0
        assert data["summary"]["avg_tokens_per_message"] == 0
