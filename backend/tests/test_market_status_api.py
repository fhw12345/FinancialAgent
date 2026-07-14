"""
Unit tests for Market Status API.

Tests market status endpoint and response models.
"""

from unittest.mock import patch

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.market.status import MarketStatusResponse, router

# ===== Test Client Setup =====


@pytest.fixture
def client():
    """Create test client."""
    app = FastAPI()
    app.include_router(router, prefix="/market")

    return TestClient(app)


# ===== MarketStatusResponse Tests =====


class TestMarketStatusResponse:
    """Test MarketStatusResponse model"""

    def test_create_response(self):
        """Test creating response"""
        response = MarketStatusResponse(
            is_open=True,
            current_session="regular",
            next_open=None,
            next_close="2025-01-10T16:00:00-05:00",
            timestamp="2025-01-10T10:30:00-05:00",
        )

        assert response.is_open is True
        assert response.current_session == "regular"
        assert response.next_close is not None

    def test_closed_session_response(self):
        """Test closed session response"""
        response = MarketStatusResponse(
            is_open=False,
            current_session="closed",
            next_open="2025-01-11T04:00:00-05:00",
            next_close=None,
            timestamp="2025-01-10T22:00:00-05:00",
        )

        assert response.is_open is False
        assert response.next_open is not None


# ===== get_market_status Tests =====


class TestGetMarketStatus:
    """Test get_market_status endpoint"""

    def test_regular_hours(self, client):
        """Test market status during regular hours"""
        # Mock regular trading hours (Tuesday 10:30 AM ET)
        mock_now = pd.Timestamp("2025-01-14 10:30:00", tz="America/New_York")

        with patch("src.api.market.status.pd.Timestamp") as mock_ts:
            mock_ts.now.return_value = mock_now
            with patch("src.api.market.status.get_market_session") as mock_session:
                mock_session.return_value = "regular"

                response = client.get("/market/status")

                assert response.status_code == 200
                data = response.json()
                assert data["is_open"] is True
                assert data["current_session"] == "regular"
                assert data["next_close"] is not None
                assert data["next_open"] is None

    def test_pre_market(self, client):
        """Test market status during pre-market"""
        mock_now = pd.Timestamp("2025-01-14 07:00:00", tz="America/New_York")

        with patch("src.api.market.status.pd.Timestamp") as mock_ts:
            mock_ts.now.return_value = mock_now
            with patch("src.api.market.status.get_market_session") as mock_session:
                mock_session.return_value = "pre"

                response = client.get("/market/status")

                assert response.status_code == 200
                data = response.json()
                assert data["is_open"] is True
                assert data["current_session"] == "pre"

    def test_post_market(self, client):
        """Test market status during post-market"""
        mock_now = pd.Timestamp("2025-01-14 17:30:00", tz="America/New_York")

        with patch("src.api.market.status.pd.Timestamp") as mock_ts:
            mock_ts.now.return_value = mock_now
            with patch("src.api.market.status.get_market_session") as mock_session:
                mock_session.return_value = "post"

                response = client.get("/market/status")

                assert response.status_code == 200
                data = response.json()
                assert data["is_open"] is True
                assert data["current_session"] == "post"

    def test_closed_weeknight(self, client):
        """Test market status during closed weeknight"""
        mock_now = pd.Timestamp("2025-01-14 22:00:00", tz="America/New_York")

        with patch("src.api.market.status.pd.Timestamp") as mock_ts:
            mock_ts.now.return_value = mock_now
            with patch("src.api.market.status.get_market_session") as mock_session:
                mock_session.return_value = "closed"

                response = client.get("/market/status")

                assert response.status_code == 200
                data = response.json()
                assert data["is_open"] is False
                assert data["current_session"] == "closed"
                assert data["next_open"] is not None

    def test_closed_weekend(self, client):
        """Test market status during weekend (Saturday)"""
        # Saturday
        mock_now = pd.Timestamp("2025-01-18 12:00:00", tz="America/New_York")

        with patch("src.api.market.status.pd.Timestamp") as mock_ts:
            mock_ts.now.return_value = mock_now
            with patch("src.api.market.status.get_market_session") as mock_session:
                mock_session.return_value = "closed"

                response = client.get("/market/status")

                assert response.status_code == 200
                data = response.json()
                assert data["is_open"] is False
                # Next open should be Monday
                assert data["next_open"] is not None

    def test_market_status_error(self, client):
        """Test market status with error"""
        with patch("src.api.market.status.pd.Timestamp") as mock_ts:
            mock_ts.now.side_effect = Exception("Timezone error")

            response = client.get("/market/status")

            assert response.status_code == 500
            assert "Failed to check market status" in response.json()["detail"]
