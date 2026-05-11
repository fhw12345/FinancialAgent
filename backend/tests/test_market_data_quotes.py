"""
Unit tests for QuotesMixin - symbol search, quotes, and market status.

Tests Alpha Vantage API interactions with mocked HTTP responses.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.market_data.quotes import QuotesMixin


# ===== Fixtures =====


@pytest.fixture
def mock_settings():
    """Mock Settings"""
    settings = Mock()
    settings.alpha_vantage_api_key = "test_api_key"
    return settings


@pytest.fixture
def quotes_service(mock_settings):
    """Create QuotesMixin instance with mocked settings"""
    with patch("src.services.market_data.base.httpx.AsyncClient"):
        service = QuotesMixin(mock_settings)
        service.client = AsyncMock()
        return service


@pytest.fixture
def mock_symbol_search_response():
    """Mock symbol search API response"""
    return {
        "bestMatches": [
            {
                "1. symbol": "AAPL",
                "2. name": "Apple Inc",
                "3. type": "Equity",
                "4. region": "United States",
                "5. marketOpen": "09:30",
                "6. marketClose": "16:00",
                "7. timezone": "UTC-04",
                "8. currency": "USD",
                "9. matchScore": "1.0000",
            },
            {
                "1. symbol": "AAPB",
                "2. name": "Apple Bank",
                "3. type": "Equity",
                "4. region": "United States",
                "5. marketOpen": "09:30",
                "6. marketClose": "16:00",
                "7. timezone": "UTC-04",
                "8. currency": "USD",
                "9. matchScore": "0.7500",
            },
        ]
    }


@pytest.fixture
def mock_quote_response():
    """Mock global quote API response"""
    return {
        "Global Quote": {
            "01. symbol": "AAPL",
            "02. open": "150.00",
            "03. high": "152.50",
            "04. low": "149.50",
            "05. price": "151.75",
            "06. volume": "75000000",
            "07. latest trading day": "2025-01-10",
            "08. previous close": "149.00",
            "09. change": "2.75",
            "10. change percent": "1.85%",
        }
    }


@pytest.fixture
def mock_market_status_response():
    """Mock market status API response"""
    return {
        "endpoint": "Market Open/Close Status",
        "markets": [
            {
                "market_type": "Equity",
                "region": "United States",
                "primary_exchanges": "NYSE, NASDAQ",
                "local_open": "09:30",
                "local_close": "16:00",
                "current_status": "closed",
                "notes": "",
            },
            {
                "market_type": "Equity",
                "region": "Hong Kong",
                "primary_exchanges": "HKEX",
                "local_open": "09:30",
                "local_close": "16:00",
                "current_status": "open",
                "notes": "Lunch break: 12:00-13:00",
            },
        ],
    }


# ===== search_symbols Tests =====


class TestSearchSymbols:
    """Test search_symbols method"""

    @pytest.mark.asyncio
    async def test_search_symbols_success(
        self, quotes_service, mock_symbol_search_response
    ):
        """Test successful symbol search"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_symbol_search_response
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        results = await quotes_service.search_symbols("AAPL")

        assert len(results) == 2
        assert results[0]["symbol"] == "AAPL"
        assert results[0]["name"] == "Apple Inc"
        assert results[0]["match_type"] == "exact_symbol"  # Score >= 0.9
        assert results[0]["confidence"] == 1.0
        assert results[1]["match_type"] == "fuzzy"  # Score < 0.9

    @pytest.mark.asyncio
    async def test_search_symbols_with_limit(
        self, quotes_service, mock_symbol_search_response
    ):
        """Test symbol search with result limit"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_symbol_search_response
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        results = await quotes_service.search_symbols("AAPL", limit=1)

        assert len(results) == 1
        assert results[0]["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_search_symbols_no_matches(self, quotes_service):
        """Test symbol search with no matches"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Information": "No matches found"}
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        results = await quotes_service.search_symbols("XYZXYZ")

        assert results == []

    @pytest.mark.asyncio
    async def test_search_symbols_api_error(self, quotes_service):
        """Test symbol search with API error"""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError) as exc_info:
            await quotes_service.search_symbols("AAPL")

        assert "Alpha Vantage API error: 429" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_symbols_exception(self, quotes_service):
        """Test symbol search with network exception"""
        quotes_service.client.get = AsyncMock(
            side_effect=Exception("Connection error")
        )

        with pytest.raises(Exception) as exc_info:
            await quotes_service.search_symbols("AAPL")

        assert "Connection error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_symbols_missing_fields(self, quotes_service):
        """Test symbol search with missing optional fields"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "bestMatches": [
                {
                    "1. symbol": "TEST",
                    # Missing other fields
                }
            ]
        }
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        results = await quotes_service.search_symbols("TEST")

        assert len(results) == 1
        assert results[0]["symbol"] == "TEST"
        assert results[0]["name"] == ""
        assert results[0]["confidence"] == 0.0


# ===== get_quote Tests =====


class TestGetQuote:
    """Test get_quote method"""

    @pytest.fixture(autouse=True)
    def _force_av_path(self):
        """yfinance is the primary quote source; these tests target the AV
        fallback contract, so make yfinance always raise to fall through."""
        with patch(
            "src.services.market_data.quotes._yf_quote_sync",
            side_effect=RuntimeError("forced miss for AV fallback test"),
        ):
            yield

    @pytest.mark.asyncio
    async def test_get_quote_success(self, quotes_service, mock_quote_response):
        """Test successful quote fetch"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_quote_response
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        result = await quotes_service.get_quote("AAPL")

        assert result["symbol"] == "AAPL"
        assert result["price"] == 151.75
        assert result["volume"] == 75000000
        assert result["change"] == 2.75
        assert result["change_percent"] == "1.85"
        assert result["open"] == 150.00
        assert result["high"] == 152.50
        assert result["low"] == 149.50

    @pytest.mark.asyncio
    async def test_get_quote_delayed_format(self, quotes_service):
        """Test quote with delayed data format"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Global Quote - DATA DELAYED BY 15 MINUTES": {
                "01. symbol": "TSLA",
                "02. open": "200.00",
                "03. high": "205.00",
                "04. low": "198.00",
                "05. price": "202.50",
                "06. volume": "50000000",
                "07. latest trading day": "2025-01-10",
                "08. previous close": "199.00",
                "09. change": "3.50",
                "10. change percent": "1.76%",
            }
        }
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        result = await quotes_service.get_quote("TSLA")

        assert result["symbol"] == "TSLA"
        assert result["price"] == 202.50

    @pytest.mark.asyncio
    async def test_get_quote_no_data(self, quotes_service):
        """Test quote when no data available"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Global Quote": {}  # Empty quote
        }
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError) as exc_info:
            await quotes_service.get_quote("INVALID")

        assert "No quote data for symbol" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_quote_no_key(self, quotes_service):
        """When api_key is empty, yfinance failure must propagate (no AV fallback)."""
        quotes_service.api_key = ""
        with pytest.raises(RuntimeError, match="forced miss"):
            await quotes_service.get_quote("INVALID")

    @pytest.mark.asyncio
    async def test_get_quote_api_error(self, quotes_service):
        """Test quote with API error"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError) as exc_info:
            await quotes_service.get_quote("AAPL")

        assert "Alpha Vantage API error: 500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_quote_missing_fields(self, quotes_service):
        """Test quote with missing optional fields"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Global Quote": {
                "01. symbol": "TEST",
                "05. price": "100.00",
                "06. volume": "1000000",
                # Missing other fields
            }
        }
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        result = await quotes_service.get_quote("TEST")

        assert result["symbol"] == "TEST"
        assert result["price"] == 100.0
        assert result["open"] == 0  # Default value
        assert result["change"] == 0
        assert result["change_percent"] == "0"

    @pytest.mark.asyncio
    async def test_get_quote_exception(self, quotes_service):
        """Test quote with network exception"""
        quotes_service.client.get = AsyncMock(side_effect=Exception("Timeout"))

        with pytest.raises(Exception) as exc_info:
            await quotes_service.get_quote("AAPL")

        assert "Timeout" in str(exc_info.value)


# ===== get_market_status Tests =====


class TestGetMarketStatus:
    """Test get_market_status method"""

    @pytest.mark.asyncio
    async def test_get_market_status_us(
        self, quotes_service, mock_market_status_response
    ):
        """Test US market status"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_market_status_response
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        result = await quotes_service.get_market_status("United States")

        assert result["region"] == "United States"
        assert result["current_status"] == "closed"
        assert result["local_open"] == "09:30"
        assert result["local_close"] == "16:00"
        assert result["primary_exchanges"] == "NYSE, NASDAQ"
        assert "local_time" in result
        assert "utc_time" in result

    @pytest.mark.asyncio
    async def test_get_market_status_hong_kong(
        self, quotes_service, mock_market_status_response
    ):
        """Test Hong Kong market status"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_market_status_response
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        result = await quotes_service.get_market_status("Hong Kong")

        assert result["region"] == "Hong Kong"
        assert result["current_status"] == "open"
        assert result["notes"] == "Lunch break: 12:00-13:00"

    @pytest.mark.asyncio
    async def test_get_market_status_region_not_found(
        self, quotes_service, mock_market_status_response
    ):
        """Test market status for unknown region"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_market_status_response
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError) as exc_info:
            await quotes_service.get_market_status("Unknown Region")

        assert "Market region not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_market_status_api_error(self, quotes_service):
        """Test market status with API error"""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError) as exc_info:
            await quotes_service.get_market_status()

        assert "Alpha Vantage API error: 403" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_market_status_empty_markets(self, quotes_service):
        """Test market status with empty markets list"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"markets": []}
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError) as exc_info:
            await quotes_service.get_market_status("United States")

        assert "Market region not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_market_status_exception(self, quotes_service):
        """Test market status with network exception"""
        quotes_service.client.get = AsyncMock(
            side_effect=Exception("Network error")
        )

        with pytest.raises(Exception) as exc_info:
            await quotes_service.get_market_status()

        assert "Network error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_market_status_unknown_timezone(
        self, quotes_service
    ):
        """Test market status with region not in timezone map"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "markets": [
                {
                    "market_type": "Equity",
                    "region": "Antarctica",  # Not in timezone map
                    "primary_exchanges": "FAKE",
                    "local_open": "10:00",
                    "local_close": "15:00",
                    "current_status": "open",
                    "notes": "",
                }
            ]
        }
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        result = await quotes_service.get_market_status("Antarctica")

        # Should use UTC as fallback
        assert result["region"] == "Antarctica"
        assert "UTC" in result["local_time"]


# ===== Integration Tests =====


class TestQuotesEdgeCases:
    """Test edge cases for quotes methods"""

    @pytest.fixture(autouse=True)
    def _force_av_path(self):
        with patch(
            "src.services.market_data.quotes._yf_quote_sync",
            side_effect=RuntimeError("forced miss for AV fallback test"),
        ):
            yield

    @pytest.mark.asyncio
    async def test_quote_change_percent_without_percent_sign(self, quotes_service):
        """Test quote change percent parsing without % sign"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Global Quote": {
                "01. symbol": "TEST",
                "05. price": "100.00",
                "06. volume": "1000",
                "10. change percent": "5.25",  # No % sign
            }
        }
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        result = await quotes_service.get_quote("TEST")

        assert result["change_percent"] == "5.25"

    @pytest.mark.asyncio
    async def test_search_respects_api_call_params(self, quotes_service):
        """Test that search passes correct parameters to API"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"bestMatches": []}
        quotes_service.client.get = AsyncMock(return_value=mock_response)

        await quotes_service.search_symbols("MSFT")

        call_args = quotes_service.client.get.call_args
        assert call_args[1]["params"]["function"] == "SYMBOL_SEARCH"
        assert call_args[1]["params"]["keywords"] == "MSFT"
