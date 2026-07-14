"""
Unit tests for Health API endpoints.

Tests health check, readiness, and liveness probes.
"""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.health import get_mongodb, get_redis, router
from src.core.config import get_settings

# ===== Fixtures =====


@pytest.fixture
def mock_mongodb():
    """Mock MongoDB instance."""
    mongodb = Mock()
    mongodb.health_check = AsyncMock(return_value={"connected": True})
    return mongodb


@pytest.fixture
def mock_redis():
    """Mock Redis instance."""
    redis = Mock()
    redis.health_check = AsyncMock(return_value={"connected": True})
    return redis


@pytest.fixture
def mock_settings():
    """Mock Settings instance."""
    settings = Mock()
    settings.environment = "test"
    settings.database_name = "test_db"
    settings.langfuse_public_key = "test_key"
    settings.langfuse_secret_key = "test_secret"
    return settings


@pytest.fixture
def client(mock_mongodb, mock_redis, mock_settings):
    """Create test client with mocked dependencies."""
    app = FastAPI()
    app.include_router(router)

    # Override dependencies
    app.dependency_overrides[get_mongodb] = lambda: mock_mongodb
    app.dependency_overrides[get_redis] = lambda: mock_redis
    app.dependency_overrides[get_settings] = lambda: mock_settings

    return TestClient(app)


# ===== health_check Tests =====


class TestHealthCheck:
    """Test main health check endpoint."""

    def test_health_all_healthy(self, client, mock_mongodb, mock_redis):
        """Test health check when all services are healthy."""
        mock_mongodb.health_check.return_value = {"connected": True}
        mock_redis.health_check.return_value = {"connected": True}

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["environment"] == "test"
        assert "dependencies" in data
        assert "configuration" in data

    def test_health_mongodb_unhealthy(self, client, mock_mongodb, mock_redis):
        """Test health check when MongoDB is unhealthy."""
        mock_mongodb.health_check.return_value = {
            "connected": False,
            "error": "Connection failed",
        }
        mock_redis.health_check.return_value = {"connected": True}

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"

    def test_health_redis_unhealthy(self, client, mock_mongodb, mock_redis):
        """Test health check when Redis is unhealthy."""
        mock_mongodb.health_check.return_value = {"connected": True}
        mock_redis.health_check.return_value = {
            "connected": False,
            "error": "Connection failed",
        }

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"

    def test_health_both_unhealthy(self, client, mock_mongodb, mock_redis):
        """Test health check when both services are unhealthy."""
        mock_mongodb.health_check.return_value = {"connected": False}
        mock_redis.health_check.return_value = {"connected": False}

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"


# ===== mongodb_health Tests =====


class TestMongodbHealth:
    """Test MongoDB-specific health endpoint."""

    def test_mongodb_healthy(self, client, mock_mongodb):
        """Test MongoDB health when connected."""
        mock_mongodb.health_check.return_value = {"connected": True, "ping": "pong"}

        response = client.get("/health/mongodb")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True

    def test_mongodb_unhealthy(self, client, mock_mongodb):
        """Test MongoDB health when disconnected."""
        mock_mongodb.health_check.return_value = {
            "connected": False,
            "error": "Connection timeout",
        }

        response = client.get("/health/mongodb")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert "error" in data


# ===== redis_health Tests =====


class TestRedisHealth:
    """Test Redis-specific health endpoint."""

    def test_redis_healthy(self, client, mock_redis):
        """Test Redis health when connected."""
        mock_redis.health_check.return_value = {"connected": True, "ping": "PONG"}

        response = client.get("/health/redis")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True

    def test_redis_unhealthy(self, client, mock_redis):
        """Test Redis health when disconnected."""
        mock_redis.health_check.return_value = {
            "connected": False,
            "error": "Connection refused",
        }

        response = client.get("/health/redis")

        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False


# ===== readiness_check Tests =====


class TestReadinessCheck:
    """Test Kubernetes readiness probe."""

    def test_ready_all_connected(self, client, mock_mongodb, mock_redis):
        """Test readiness when all dependencies are connected."""
        mock_mongodb.health_check.return_value = {"connected": True}
        mock_redis.health_check.return_value = {"connected": True}

        response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is True
        assert data["dependencies"]["mongodb"] is True
        assert data["dependencies"]["redis"] is True

    def test_not_ready_mongodb_disconnected(self, client, mock_mongodb, mock_redis):
        """Test readiness when MongoDB is disconnected."""
        mock_mongodb.health_check.return_value = {"connected": False}
        mock_redis.health_check.return_value = {"connected": True}

        response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is False
        assert data["dependencies"]["mongodb"] is False

    def test_not_ready_redis_disconnected(self, client, mock_mongodb, mock_redis):
        """Test readiness when Redis is disconnected."""
        mock_mongodb.health_check.return_value = {"connected": True}
        mock_redis.health_check.return_value = {"connected": False}

        response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is False
        assert data["dependencies"]["redis"] is False


# ===== liveness_check Tests =====


class TestLivenessCheck:
    """Test Kubernetes liveness probe."""

    def test_liveness(self, client):
        """Test liveness check always returns alive."""
        response = client.get("/health/live")

        assert response.status_code == 200
        data = response.json()
        assert data["alive"] is True
        assert data["status"] == "ok"
