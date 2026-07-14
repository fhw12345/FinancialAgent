"""
Unit tests for BarsBasicMixin - intraday, daily, weekly, monthly bars.

Tests Alpha Vantage API interactions with mocked HTTP responses.
"""

from unittest.mock import AsyncMock, Mock, patch

import pandas as pd
import pytest

from src.services.market_data.bars_basic import BarsBasicMixin

# ===== Fixtures =====


@pytest.fixture
def mock_settings():
    """Mock Settings"""
    settings = Mock()
    settings.alpha_vantage_api_key = "test_api_key"
    return settings


@pytest.fixture
def bars_service(mock_settings):
    """Create BarsBasicMixin instance with mocked settings"""
    with patch("src.services.market_data.base.httpx.AsyncClient"):
        service = BarsBasicMixin(mock_settings)
        service.client = AsyncMock()
        return service


@pytest.fixture
def mock_intraday_response():
    """Mock intraday API response"""
    return {
        "Meta Data": {
            "1. Information": "Intraday (1min) prices",
            "2. Symbol": "AAPL",
        },
        "Time Series (1min)": {
            "2025-01-10 16:00:00": {
                "1. open": "150.00",
                "2. high": "151.00",
                "3. low": "149.50",
                "4. close": "150.50",
                "5. volume": "1000000",
            },
            "2025-01-10 15:59:00": {
                "1. open": "149.80",
                "2. high": "150.10",
                "3. low": "149.70",
                "4. close": "150.00",
                "5. volume": "500000",
            },
        },
    }


@pytest.fixture
def mock_daily_response():
    """Mock daily adjusted API response"""
    return {
        "Meta Data": {
            "1. Information": "Daily Time Series with Splits and Dividend Events",
            "2. Symbol": "AAPL",
        },
        "Time Series (Daily)": {
            "2025-01-10": {
                "1. open": "150.00",
                "2. high": "152.00",
                "3. low": "149.00",
                "4. close": "151.50",
                "5. adjusted close": "151.50",
                "6. volume": "50000000",
                "7. dividend amount": "0.0000",
                "8. split coefficient": "1.0",
            },
            "2025-01-09": {
                "1. open": "148.00",
                "2. high": "150.50",
                "3. low": "147.50",
                "4. close": "150.00",
                "5. adjusted close": "150.00",
                "6. volume": "45000000",
                "7. dividend amount": "0.0000",
                "8. split coefficient": "1.0",
            },
        },
    }


@pytest.fixture
def mock_weekly_response():
    """Mock weekly adjusted API response"""
    return {
        "Meta Data": {
            "1. Information": "Weekly Adjusted Prices",
            "2. Symbol": "AAPL",
        },
        "Weekly Adjusted Time Series": {
            "2025-01-10": {
                "1. open": "145.00",
                "2. high": "152.00",
                "3. low": "144.00",
                "4. close": "151.50",
                "5. adjusted close": "151.50",
                "6. volume": "200000000",
                "7. dividend amount": "0.0000",
            },
            "2025-01-03": {
                "1. open": "142.00",
                "2. high": "146.00",
                "3. low": "141.00",
                "4. close": "145.00",
                "5. adjusted close": "145.00",
                "6. volume": "180000000",
                "7. dividend amount": "0.0000",
            },
        },
    }


@pytest.fixture
def mock_monthly_response():
    """Mock monthly adjusted API response"""
    return {
        "Meta Data": {
            "1. Information": "Monthly Adjusted Prices",
            "2. Symbol": "AAPL",
        },
        "Monthly Adjusted Time Series": {
            "2024-12-31": {
                "1. open": "140.00",
                "2. high": "155.00",
                "3. low": "138.00",
                "4. close": "152.00",
                "5. adjusted close": "152.00",
                "6. volume": "800000000",
                "7. dividend amount": "0.2400",
            },
            "2024-11-30": {
                "1. open": "135.00",
                "2. high": "142.00",
                "3. low": "133.00",
                "4. close": "140.00",
                "5. adjusted close": "140.00",
                "6. volume": "750000000",
                "7. dividend amount": "0.0000",
            },
        },
    }


# ===== get_intraday_bars Tests =====


class TestGetIntradayBars:
    """Test get_intraday_bars method"""

    @pytest.mark.asyncio
    async def test_intraday_bars_success(self, bars_service, mock_intraday_response):
        """Test successful intraday bars fetch"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_intraday_response
        bars_service.client.get = AsyncMock(return_value=mock_response)

        df = await bars_service.get_intraday_bars("AAPL", interval="1min")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
        # Check data is sorted chronologically
        assert df.index[0] < df.index[1]
        # Check timezone localization
        assert df.index.tz is not None

    @pytest.mark.asyncio
    async def test_intraday_bars_with_interval(
        self, bars_service, mock_intraday_response
    ):
        """Test intraday bars with different intervals"""
        mock_response = Mock()
        mock_response.status_code = 200
        # Update response key to match requested interval
        mock_intraday_response["Time Series (5min)"] = mock_intraday_response.pop(
            "Time Series (1min)"
        )
        mock_response.json.return_value = mock_intraday_response
        bars_service.client.get = AsyncMock(return_value=mock_response)

        df = await bars_service.get_intraday_bars("AAPL", interval="5min")

        assert len(df) == 2
        # Verify API was called with correct interval
        call_args = bars_service.client.get.call_args
        assert call_args[1]["params"]["interval"] == "5min"

    @pytest.mark.asyncio
    async def test_intraday_bars_api_error(self, bars_service):
        """Test intraday bars with API error"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        bars_service.client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError) as exc_info:
            await bars_service.get_intraday_bars("AAPL")

        assert "Alpha Vantage API error: 500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_intraday_bars_no_data(self, bars_service):
        """Test intraday bars when no data available"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Error Message": "Invalid API call"}
        bars_service.client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError) as exc_info:
            await bars_service.get_intraday_bars("INVALID")

        assert "No intraday data for symbol" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_intraday_bars_outputsize_parameter(
        self, bars_service, mock_intraday_response
    ):
        """Test intraday bars with outputsize parameter"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_intraday_response
        bars_service.client.get = AsyncMock(return_value=mock_response)

        await bars_service.get_intraday_bars("AAPL", outputsize="full")

        call_args = bars_service.client.get.call_args
        assert call_args[1]["params"]["outputsize"] == "full"


# ===== get_daily_bars Tests =====


class TestGetDailyBars:
    """Test get_daily_bars method"""

    @pytest.mark.asyncio
    async def test_daily_bars_success(self, bars_service, mock_daily_response):
        """Test successful daily bars fetch"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_daily_response
        bars_service.client.get = AsyncMock(return_value=mock_response)

        df = await bars_service.get_daily_bars("AAPL")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
        # Check data is sorted chronologically
        assert df.index[0] < df.index[1]

    @pytest.mark.asyncio
    async def test_daily_bars_split_adjustment(self, bars_service):
        """Test that daily bars are split-adjusted correctly"""
        # Simulate a 10:1 stock split
        mock_response_data = {
            "Time Series (Daily)": {
                "2025-01-10": {
                    "1. open": "1700.00",  # Raw pre-split price
                    "2. high": "1720.00",
                    "3. low": "1680.00",
                    "4. close": "1700.00",  # Raw close
                    "5. adjusted close": "170.00",  # Split-adjusted
                    "6. volume": "10000000",
                    "7. dividend amount": "0.0000",
                    "8. split coefficient": "10.0",
                },
            },
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        bars_service.client.get = AsyncMock(return_value=mock_response)

        df = await bars_service.get_daily_bars("NVDA")

        # All OHLC should be split-adjusted (divided by 10)
        assert df.loc["2025-01-10", "Open"] == pytest.approx(170.0, rel=0.01)
        assert df.loc["2025-01-10", "High"] == pytest.approx(172.0, rel=0.01)
        assert df.loc["2025-01-10", "Low"] == pytest.approx(168.0, rel=0.01)
        assert df.loc["2025-01-10", "Close"] == pytest.approx(170.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_daily_bars_api_error(self, bars_service):
        """Test daily bars with API error"""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        bars_service.client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError) as exc_info:
            await bars_service.get_daily_bars("AAPL")

        assert "Alpha Vantage API error: 429" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_daily_bars_no_data(self, bars_service):
        """Test daily bars when no data available"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Information": "Invalid symbol"}
        bars_service.client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError) as exc_info:
            await bars_service.get_daily_bars("INVALID")

        assert "No daily data for symbol" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_daily_bars_zero_close_handling(self, bars_service):
        """Test daily bars handles zero close (edge case)"""
        mock_response_data = {
            "Time Series (Daily)": {
                "2025-01-10": {
                    "1. open": "0.00",
                    "2. high": "0.00",
                    "3. low": "0.00",
                    "4. close": "0.00",  # Zero close - edge case
                    "5. adjusted close": "0.00",
                    "6. volume": "0",
                    "7. dividend amount": "0.0000",
                    "8. split coefficient": "1.0",
                },
            },
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        bars_service.client.get = AsyncMock(return_value=mock_response)

        # Should not raise division by zero
        df = await bars_service.get_daily_bars("DELISTED")
        assert len(df) == 1


# ===== get_weekly_bars Tests =====


class TestGetWeeklyBars:
    """Test get_weekly_bars method"""

    @pytest.mark.asyncio
    async def test_weekly_bars_success(self, bars_service, mock_weekly_response):
        """Test successful weekly bars fetch"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_weekly_response
        bars_service.client.get = AsyncMock(return_value=mock_response)

        df = await bars_service.get_weekly_bars("AAPL")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
        # Check data is sorted chronologically
        assert df.index[0] < df.index[1]

    @pytest.mark.asyncio
    async def test_weekly_bars_split_adjustment(self, bars_service):
        """Test that weekly bars are split-adjusted correctly"""
        mock_response_data = {
            "Weekly Adjusted Time Series": {
                "2025-01-10": {
                    "1. open": "3400.00",  # Pre-split
                    "2. high": "3500.00",
                    "3. low": "3300.00",
                    "4. close": "3400.00",
                    "5. adjusted close": "170.00",  # 20:1 split adjusted
                    "6. volume": "50000000",
                    "7. dividend amount": "0.0000",
                },
            },
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        bars_service.client.get = AsyncMock(return_value=mock_response)

        df = await bars_service.get_weekly_bars("AMZN")

        # Adjustment factor is 170/3400 = 0.05
        assert df.loc["2025-01-10", "Open"] == pytest.approx(170.0, rel=0.01)
        assert df.loc["2025-01-10", "High"] == pytest.approx(175.0, rel=0.01)
        assert df.loc["2025-01-10", "Low"] == pytest.approx(165.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_weekly_bars_api_error(self, bars_service):
        """Test weekly bars with API error"""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        bars_service.client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError) as exc_info:
            await bars_service.get_weekly_bars("AAPL")

        assert "Alpha Vantage API error: 403" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_weekly_bars_no_data(self, bars_service):
        """Test weekly bars when no data available"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        bars_service.client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError) as exc_info:
            await bars_service.get_weekly_bars("INVALID")

        assert "No weekly data for symbol" in str(exc_info.value)


# ===== get_monthly_bars Tests =====


class TestGetMonthlyBars:
    """Test get_monthly_bars method"""

    @pytest.mark.asyncio
    async def test_monthly_bars_success(self, bars_service, mock_monthly_response):
        """Test successful monthly bars fetch"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_monthly_response
        bars_service.client.get = AsyncMock(return_value=mock_response)

        df = await bars_service.get_monthly_bars("AAPL")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
        # Check data is sorted chronologically
        assert df.index[0] < df.index[1]

    @pytest.mark.asyncio
    async def test_monthly_bars_split_adjustment(self, bars_service):
        """Test that monthly bars are split-adjusted correctly"""
        mock_response_data = {
            "Monthly Adjusted Time Series": {
                "2024-12-31": {
                    "1. open": "500.00",
                    "2. high": "550.00",
                    "3. low": "480.00",
                    "4. close": "500.00",
                    "5. adjusted close": "250.00",  # 2:1 split adjusted
                    "6. volume": "100000000",
                    "7. dividend amount": "0.0000",
                },
            },
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        bars_service.client.get = AsyncMock(return_value=mock_response)

        df = await bars_service.get_monthly_bars("GOOG")

        # Adjustment factor is 250/500 = 0.5
        assert df.loc["2024-12-31", "Open"] == pytest.approx(250.0, rel=0.01)
        assert df.loc["2024-12-31", "High"] == pytest.approx(275.0, rel=0.01)
        assert df.loc["2024-12-31", "Low"] == pytest.approx(240.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_monthly_bars_api_error(self, bars_service):
        """Test monthly bars with API error"""
        mock_response = Mock()
        mock_response.status_code = 502
        mock_response.text = "Bad Gateway"
        bars_service.client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError) as exc_info:
            await bars_service.get_monthly_bars("AAPL")

        assert "Alpha Vantage API error: 502" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_monthly_bars_no_data(self, bars_service):
        """Test monthly bars when no data available"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Note": "API rate limit"}
        bars_service.client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError) as exc_info:
            await bars_service.get_monthly_bars("INVALID")

        assert "No monthly data for symbol" in str(exc_info.value)


# ===== Edge Cases and Integration Tests =====


class TestBarsEdgeCases:
    """Test edge cases for bars methods"""

    @pytest.mark.asyncio
    async def test_bars_data_types(self, bars_service, mock_daily_response):
        """Test that returned data has correct types"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_daily_response
        bars_service.client.get = AsyncMock(return_value=mock_response)

        df = await bars_service.get_daily_bars("AAPL")

        # Check column types
        assert df["Open"].dtype == "float64"
        assert df["High"].dtype == "float64"
        assert df["Low"].dtype == "float64"
        assert df["Close"].dtype == "float64"
        assert df["Volume"].dtype == "int64"

    @pytest.mark.asyncio
    async def test_exception_handling(self, bars_service):
        """Test exception handling for network errors"""
        bars_service.client.get = AsyncMock(side_effect=Exception("Connection timeout"))

        with pytest.raises(Exception) as exc_info:
            await bars_service.get_daily_bars("AAPL")

        assert "Connection timeout" in str(exc_info.value)
