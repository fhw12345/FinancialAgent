"""
Comprehensive unit tests for AlphaVantageMarketDataService.

Tests Alpha Vantage API integration including:
- Symbol search
- Quote retrieval
- Historical data (intraday, daily, weekly, monthly)
- Company overview
- News sentiment
- Cash flow and balance sheet
- Market movers (top gainers/losers)
- Utility functions (market session detection, date validation)
"""

from unittest.mock import AsyncMock, Mock, patch

import pandas as pd
import pytest

from src.core.config import Settings
from src.services.alphavantage_market_data import (
    AlphaVantageMarketDataService,
    get_market_session,
    validate_date_range,
)

# ===== Fixtures =====


@pytest.fixture
def settings():
    """Mock settings with Alpha Vantage API key"""
    settings = Mock(spec=Settings)
    settings.alpha_vantage_api_key = "TEST_API_KEY_1234567890"
    return settings


@pytest.fixture
def service(settings):
    """Create AlphaVantageMarketDataService instance"""
    return AlphaVantageMarketDataService(settings)


@pytest.fixture
def mock_httpx_response():
    """Mock httpx response"""
    response = Mock()
    response.status_code = 200
    response.json = Mock()
    return response


# ===== Utility Function Tests =====


class TestGetMarketSession:
    """Test get_market_session utility function"""

    def test_regular_hours_weekday(self):
        """Test regular market hours (9:30 AM - 4:00 PM ET)"""
        # Wednesday at 10:00 AM ET (regular hours)
        timestamp = pd.Timestamp("2024-01-10 10:00:00", tz="America/New_York")
        assert get_market_session(timestamp) == "regular"

    def test_pre_market_hours(self):
        """Test pre-market hours (4:00 AM - 9:30 AM ET)"""
        # Wednesday at 8:00 AM ET (pre-market)
        timestamp = pd.Timestamp("2024-01-10 08:00:00", tz="America/New_York")
        assert get_market_session(timestamp) == "pre"

    def test_post_market_hours(self):
        """Test post-market hours (4:00 PM - 8:00 PM ET)"""
        # Wednesday at 6:00 PM ET (post-market)
        timestamp = pd.Timestamp("2024-01-10 18:00:00", tz="America/New_York")
        assert get_market_session(timestamp) == "post"

    def test_closed_hours_overnight(self):
        """Test closed hours overnight"""
        # Wednesday at 2:00 AM ET (closed)
        timestamp = pd.Timestamp("2024-01-10 02:00:00", tz="America/New_York")
        assert get_market_session(timestamp) == "closed"

    def test_weekend_closed(self):
        """Test weekend is always closed"""
        # Saturday at 10:00 AM ET (weekend)
        timestamp = pd.Timestamp("2024-01-13 10:00:00", tz="America/New_York")
        assert get_market_session(timestamp) == "closed"

        # Sunday at 10:00 AM ET (weekend)
        timestamp = pd.Timestamp("2024-01-14 10:00:00", tz="America/New_York")
        assert get_market_session(timestamp) == "closed"

    def test_timezone_conversion_from_utc(self):
        """Test automatic timezone conversion from UTC"""
        # 15:00 UTC = 10:00 AM ET (regular hours)
        timestamp = pd.Timestamp("2024-01-10 15:00:00", tz="UTC")
        assert get_market_session(timestamp) == "regular"

    def test_naive_timestamp_treated_as_utc(self):
        """Test naive timestamp is treated as UTC"""
        # 15:00 (naive, treated as UTC) = 10:00 AM ET (regular hours)
        timestamp = pd.Timestamp("2024-01-10 15:00:00")
        assert get_market_session(timestamp) == "regular"


class TestValidateDateRange:
    """Test validate_date_range utility function"""

    def test_no_dates_always_valid(self):
        """Test that None dates are always valid"""
        is_valid, error = validate_date_range(None, None, "1d")
        assert is_valid is True
        assert error is None

    def test_valid_date_range_daily(self):
        """Test valid date range for daily interval"""
        is_valid, error = validate_date_range("2024-01-01", "2024-01-31", "1d")
        assert is_valid is True
        assert error is None

    def test_invalid_date_format(self):
        """Test invalid date format"""
        is_valid, error = validate_date_range("2024/01/01", "2024-01-31", "1d")
        assert is_valid is False
        assert "Invalid date format" in error

    def test_start_after_end(self):
        """Test start date after end date"""
        is_valid, error = validate_date_range("2024-01-31", "2024-01-01", "1d")
        assert is_valid is False
        assert "Start date must be before" in error

    def test_intraday_future_date(self):
        """Test intraday interval with future date"""
        future_date = (
            pd.Timestamp.now(tz="America/New_York") + pd.Timedelta(days=5)
        ).strftime("%Y-%m-%d")
        today = pd.Timestamp.now(tz="America/New_York").strftime("%Y-%m-%d")

        is_valid, error = validate_date_range(today, future_date, "1m")
        assert is_valid is False
        assert "cannot be in the future" in error

    def test_intraday_too_old(self):
        """Test intraday interval with date older than 30 days"""
        old_date = (
            pd.Timestamp.now(tz="America/New_York") - pd.Timedelta(days=35)
        ).strftime("%Y-%m-%d")
        today = pd.Timestamp.now(tz="America/New_York").strftime("%Y-%m-%d")

        is_valid, error = validate_date_range(old_date, today, "1m")
        assert is_valid is False
        assert "only available for last 30 days" in error

    def test_intraday_within_30_days_valid(self):
        """Test intraday interval within 30-day window is valid"""
        date_7_days_ago = (
            pd.Timestamp.now(tz="America/New_York") - pd.Timedelta(days=7)
        ).strftime("%Y-%m-%d")
        today = pd.Timestamp.now(tz="America/New_York").strftime("%Y-%m-%d")

        is_valid, error = validate_date_range(date_7_days_ago, today, "1m")
        assert is_valid is True
        assert error is None


# ===== Service Method Tests =====


class TestAlphaVantageMarketDataService:
    """Test AlphaVantageMarketDataService methods"""

    @pytest.fixture(autouse=True)
    def _force_av_quote_path(self):
        """yfinance is the primary quote/fundamentals source; force it to fail
        so AV tests exercise the AV fallback contract."""
        with (
            patch(
                "src.services.market_data.quotes._yf_quote_sync",
                side_effect=RuntimeError("forced miss for AV fallback test"),
            ),
            patch(
                "src.services.market_data.yfinance_fundamentals.get_company_overview",
                AsyncMock(side_effect=RuntimeError("forced miss")),
            ),
            patch(
                "src.services.market_data.yfinance_fundamentals.get_cash_flow",
                AsyncMock(side_effect=RuntimeError("forced miss")),
            ),
            patch(
                "src.services.market_data.yfinance_fundamentals.get_balance_sheet",
                AsyncMock(side_effect=RuntimeError("forced miss")),
            ),
            patch(
                "src.services.market_data.yfinance_fundamentals.get_news_sentiment",
                AsyncMock(side_effect=RuntimeError("forced miss")),
            ),
            patch(
                "src.services.market_data.yfinance_movers.get_market_movers",
                AsyncMock(side_effect=RuntimeError("forced miss")),
            ),
        ):
            yield

    def test_initialization(self, service, settings):
        """Test service initialization"""
        assert service.api_key == "TEST_API_KEY_1234567890"
        assert service.settings == settings
        assert service.base_url == "https://www.alphavantage.co/query"

    def test_sanitize_text(self, service):
        """Test API key sanitization in text"""
        text = "Error with apikey=ABCD1234567890XYZ in request"
        sanitized = service._sanitize_text(text)
        assert "ABCD1234567890XYZ" not in sanitized
        assert "****" in sanitized  # Implementation uses 4 asterisks

    def test_sanitize_response(self, service):
        """Test API key sanitization in response dict"""
        response = {
            "Error Message": "Invalid apikey=ABCD1234567890XYZ",
            "data": {"info": "Some data"},
        }
        sanitized = service._sanitize_response(response)
        assert "ABCD1234567890XYZ" not in str(sanitized)
        assert "****" in sanitized["Error Message"]

    @pytest.mark.asyncio
    async def test_close(self, service):
        """Test service cleanup/close method"""
        service.client = Mock()
        service.client.aclose = AsyncMock()

        await service.close()

        service.client.aclose.assert_called_once()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_search_symbols_success(self, mock_get, service):
        """Test successful symbol search"""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "bestMatches": [
                {
                    "1. symbol": "AAPL",
                    "2. name": "Apple Inc.",
                    "3. type": "Equity",
                    "4. region": "United States",
                    "8. currency": "USD",
                },
                {
                    "1. symbol": "AAPLF",
                    "2. name": "Apple Inc. (Frankfurt)",
                    "3. type": "Equity",
                    "4. region": "Germany",
                    "8. currency": "EUR",
                },
            ]
        }
        mock_get.return_value = mock_response

        # Call method
        results = await service.search_symbols("AAPL", limit=2)

        # Assertions
        assert len(results) == 2
        assert (
            results[0]["symbol"] == "AAPL"
        )  # Method transforms "1. symbol" to "symbol"
        assert (
            results[0]["name"] == "Apple Inc."
        )  # Method transforms "2. name" to "name"
        mock_get.assert_called_once()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_search_symbols_empty_query(self, mock_get, service):
        """Test symbol search with empty query"""
        # Mock API response with no matches
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"bestMatches": []}
        mock_get.return_value = mock_response

        results = await service.search_symbols("", limit=10)

        # Should return empty list
        assert results == []
        mock_get.assert_called_once()

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_get_quote_success(self, mock_get, service):
        """Test successful quote retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Global Quote": {
                "01. symbol": "AAPL",
                "05. price": "150.25",
                "06. volume": "50000000",
                "09. change": "2.50",
                "10. change percent": "1.69%",
            }
        }
        mock_get.return_value = mock_response

        quote = await service.get_quote("AAPL")

        # Method transforms response to simpler dict
        assert quote["symbol"] == "AAPL"
        assert quote["price"] == 150.25
        assert quote["volume"] == 50000000
        assert quote["change"] == 2.50

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_get_company_overview_success(self, mock_get, service):
        """Test successful company overview retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Symbol": "AAPL",
            "Name": "Apple Inc.",
            "Description": "Technology company",
            "Sector": "Technology",
            "MarketCapitalization": "3000000000000",
            "PERatio": "28.5",
        }
        mock_get.return_value = mock_response

        overview = await service.get_company_overview("AAPL")

        assert overview["Symbol"] == "AAPL"
        assert overview["Name"] == "Apple Inc."
        assert "MarketCapitalization" in overview

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_get_news_sentiment_success(self, mock_get, service):
        """Test successful news sentiment retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "feed": [
                {
                    "title": "Apple announces new product",
                    "url": "https://example.com/news",
                    "time_published": "20240110T120000",
                    "overall_sentiment_score": 0.75,
                    "overall_sentiment_label": "Bullish",
                }
            ],
            "sentiment_score_definition": "x <= -0.35: Bearish",
        }
        mock_get.return_value = mock_response

        news = await service.get_news_sentiment("AAPL", limit=10)

        assert "feed" in news
        assert len(news["feed"]) == 1
        assert news["feed"][0]["title"] == "Apple announces new product"

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_get_cash_flow_success(self, mock_get, service):
        """Test successful cash flow retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "symbol": "AAPL",
            "annualReports": [
                {
                    "fiscalDateEnding": "2023-12-31",
                    "operatingCashflow": "100000000000",
                    "capitalExpenditures": "10000000000",
                }
            ],
        }
        mock_get.return_value = mock_response

        cash_flow = await service.get_cash_flow("AAPL")

        assert cash_flow["symbol"] == "AAPL"
        assert "annualReports" in cash_flow
        assert len(cash_flow["annualReports"]) == 1

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_get_balance_sheet_success(self, mock_get, service):
        """Test successful balance sheet retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "symbol": "AAPL",
            "annualReports": [
                {
                    "fiscalDateEnding": "2023-12-31",
                    "totalAssets": "500000000000",
                    "totalLiabilities": "200000000000",
                }
            ],
        }
        mock_get.return_value = mock_response

        balance_sheet = await service.get_balance_sheet("AAPL")

        assert balance_sheet["symbol"] == "AAPL"
        assert "annualReports" in balance_sheet

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_get_top_gainers_losers_success(self, mock_get, service):
        """Test successful market movers retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "top_gainers": [
                {"ticker": "XYZ", "price": "100.00", "change_percentage": "15.5%"}
            ],
            "top_losers": [
                {"ticker": "ABC", "price": "50.00", "change_percentage": "-10.2%"}
            ],
            "most_actively_traded": [
                {"ticker": "DEF", "price": "75.00", "volume": "10000000"}
            ],
        }
        mock_get.return_value = mock_response

        movers = await service.get_top_gainers_losers()

        assert "top_gainers" in movers
        assert "top_losers" in movers
        assert "most_actively_traded" in movers
        assert len(movers["top_gainers"]) == 1

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_get_daily_bars_success(self, mock_get, service):
        """Test successful daily bars retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Time Series (Daily)": {
                "2024-01-10": {
                    "1. open": "150.00",
                    "2. high": "155.00",
                    "3. low": "149.00",
                    "4. close": "153.00",
                    "5. adjusted close": "153.00",
                    "6. volume": "50000000",
                },
                "2024-01-09": {
                    "1. open": "148.00",
                    "2. high": "152.00",
                    "3. low": "147.00",
                    "4. close": "150.00",
                    "5. adjusted close": "150.00",
                    "6. volume": "45000000",
                },
            }
        }
        mock_get.return_value = mock_response

        bars = await service.get_daily_bars("AAPL", outputsize="compact")

        # bars is a DataFrame indexed by date, sorted chronologically
        assert len(bars) == 2
        assert bars.iloc[0]["Open"] == 148.00  # First row (2024-01-09), Open column
        assert "Volume" in bars.columns

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_api_error_handling(self, mock_get, service):
        """Test API error handling"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"Error Message": "API limit reached"}
        mock_get.return_value = mock_response

        # Should raise exception or return error dict
        with pytest.raises(Exception):
            await service.get_quote("AAPL")

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.get")
    async def test_rate_limit_handling(self, mock_get, service):
        """Test rate limit error handling"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Note": "Thank you for using Alpha Vantage! Please visit https://www.alphavantage.co/premium/ if you would like to access more."
        }
        mock_get.return_value = mock_response

        # Should raise ValueError when Global Quote is missing (rate limit hit)
        with pytest.raises(ValueError, match="No quote data for symbol"):
            await service.get_quote("AAPL")
