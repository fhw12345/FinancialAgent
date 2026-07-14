"""
Unit tests for caching utilities.

Tests caching key generation and TTL strategies for:
- Cache key generation (consistent, sorted parameters)
- Tool-specific TTL configuration
- Interval-dependent TTL for technical indicators
- API cost tracking
"""

from src.core.utils.cache_utils import (
    INTERVAL_TTL_MAP,
    generate_tool_cache_key,
    get_api_cost,
    get_tool_ttl,
)

# ===== Cache Key Generation Tests =====


class TestGenerateToolCacheKey:
    """Test cache key generation"""

    def test_generate_simple_cache_key(self):
        """Test basic cache key generation with single parameter"""
        # Arrange
        tool_source = "mcp_alphavantage"
        tool_name = "GLOBAL_QUOTE"
        params = {"symbol": "AAPL"}

        # Act
        cache_key = generate_tool_cache_key(tool_source, tool_name, params)

        # Assert
        assert cache_key == "mcp_alphavantage:GLOBAL_QUOTE:symbol=AAPL"

    def test_generate_cache_key_multiple_params(self):
        """Test cache key generation with multiple parameters"""
        # Arrange
        tool_source = "mcp_alphavantage"
        tool_name = "RSI"
        params = {"symbol": "AAPL", "interval": "daily", "time_period": "14"}

        # Act
        cache_key = generate_tool_cache_key(tool_source, tool_name, params)

        # Assert
        # Parameters should be sorted alphabetically
        assert (
            cache_key
            == "mcp_alphavantage:RSI:interval=daily:symbol=AAPL:time_period=14"
        )

    def test_generate_cache_key_params_sorted_alphabetically(self):
        """Test that parameters are consistently sorted"""
        # Arrange
        tool_source = "1st_party"
        tool_name = "fibonacci_analysis_tool"

        # Same params, different order
        params1 = {"symbol": "AAPL", "timeframe": "1d", "start_date": "2025-01-01"}
        params2 = {"start_date": "2025-01-01", "symbol": "AAPL", "timeframe": "1d"}

        # Act
        key1 = generate_tool_cache_key(tool_source, tool_name, params1)
        key2 = generate_tool_cache_key(tool_source, tool_name, params2)

        # Assert - both should produce identical keys
        assert key1 == key2
        assert (
            key1
            == "1st_party:fibonacci_analysis_tool:start_date=2025-01-01:symbol=AAPL:timeframe=1d"
        )

    def test_generate_cache_key_empty_params(self):
        """Test cache key generation with empty parameters"""
        # Arrange
        tool_source = "mcp_alphavantage"
        tool_name = "MARKET_STATUS"
        params = {}

        # Act
        cache_key = generate_tool_cache_key(tool_source, tool_name, params)

        # Assert - should end with empty param string
        assert cache_key == "mcp_alphavantage:MARKET_STATUS:"

    def test_generate_cache_key_different_sources(self):
        """Test that different tool sources generate different keys"""
        # Arrange
        params = {"symbol": "AAPL"}

        # Act
        key_alphavantage = generate_tool_cache_key(
            "mcp_alphavantage", "GLOBAL_QUOTE", params
        )
        key_first_party = generate_tool_cache_key("1st_party", "GLOBAL_QUOTE", params)

        # Assert
        assert key_alphavantage != key_first_party
        assert key_alphavantage.startswith("mcp_alphavantage:")
        assert key_first_party.startswith("1st_party:")

    def test_generate_cache_key_different_tool_names(self):
        """Test that different tool names generate different keys"""
        # Arrange
        tool_source = "mcp_alphavantage"
        params = {"symbol": "AAPL"}

        # Act
        key_quote = generate_tool_cache_key(tool_source, "GLOBAL_QUOTE", params)
        key_overview = generate_tool_cache_key(tool_source, "COMPANY_OVERVIEW", params)

        # Assert
        assert key_quote != key_overview
        assert "GLOBAL_QUOTE" in key_quote
        assert "COMPANY_OVERVIEW" in key_overview

    def test_generate_cache_key_numeric_param_values(self):
        """Test cache key generation with numeric parameter values"""
        # Arrange
        tool_source = "mcp_alphavantage"
        tool_name = "RSI"
        params = {"symbol": "AAPL", "time_period": 14, "series_type": "close"}

        # Act
        cache_key = generate_tool_cache_key(tool_source, tool_name, params)

        # Assert
        assert "time_period=14" in cache_key

    def test_generate_cache_key_special_characters(self):
        """Test cache key with special characters in parameters"""
        # Arrange
        tool_source = "mcp_alphavantage"
        tool_name = "NEWS_SENTIMENT"
        params = {"tickers": "COIN,CRYPTO:BTC,FOREX:USD"}

        # Act
        cache_key = generate_tool_cache_key(tool_source, tool_name, params)

        # Assert
        assert (
            cache_key
            == "mcp_alphavantage:NEWS_SENTIMENT:tickers=COIN,CRYPTO:BTC,FOREX:USD"
        )


# ===== Tool TTL Tests =====


class TestGetToolTTL:
    """Test TTL retrieval for different tool types"""

    def test_get_ttl_realtime_data(self):
        """Test TTL for real-time data (5 minutes)"""
        # Arrange & Act
        ttl_quote = get_tool_ttl("GLOBAL_QUOTE")
        ttl_bulk = get_tool_ttl("REALTIME_BULK_QUOTES")
        ttl_market = get_tool_ttl("MARKET_STATUS")

        # Assert - Real-time data should refresh every 5 minutes
        assert ttl_quote == 300
        assert ttl_bulk == 300
        assert ttl_market == 300

    def test_get_ttl_news_data(self):
        """Test TTL for news and sentiment data"""
        # Arrange & Act
        ttl_news = get_tool_ttl("NEWS_SENTIMENT")
        ttl_transcript = get_tool_ttl("EARNINGS_CALL_TRANSCRIPT")

        # Assert
        assert ttl_news == 3600  # 1 hour
        assert ttl_transcript == 86400  # 24 hours

    def test_get_ttl_fundamental_data(self):
        """Test TTL for fundamental data (24 hours)"""
        # Arrange & Act
        ttl_overview = get_tool_ttl("COMPANY_OVERVIEW")
        ttl_earnings = get_tool_ttl("EARNINGS")
        ttl_balance = get_tool_ttl("BALANCE_SHEET")
        ttl_cashflow = get_tool_ttl("CASH_FLOW")
        ttl_income = get_tool_ttl("INCOME_STATEMENT")

        # Assert - Fundamental data changes rarely
        assert ttl_overview == 86400
        assert ttl_earnings == 86400
        assert ttl_balance == 86400
        assert ttl_cashflow == 86400
        assert ttl_income == 86400

    def test_get_ttl_historical_time_series(self):
        """Test TTL for historical time series data"""
        # Arrange & Act
        ttl_intraday = get_tool_ttl("TIME_SERIES_INTRADAY")
        ttl_daily = get_tool_ttl("TIME_SERIES_DAILY")
        ttl_weekly = get_tool_ttl("TIME_SERIES_WEEKLY")
        ttl_monthly = get_tool_ttl("TIME_SERIES_MONTHLY")

        # Assert
        assert ttl_intraday == 1800  # 30 minutes
        assert ttl_daily == 3600  # 1 hour
        assert ttl_weekly == 7200  # 2 hours
        assert ttl_monthly == 14400  # 4 hours

    def test_get_ttl_interval_dependent_daily(self):
        """Test interval-dependent TTL for daily data"""
        # Arrange & Act
        ttl = get_tool_ttl("RSI", "daily")

        # Assert - Daily interval should cache for 1 hour
        assert ttl == 3600

    def test_get_ttl_interval_dependent_5min(self):
        """Test interval-dependent TTL for 5-minute data"""
        # Arrange & Act
        ttl = get_tool_ttl("MACD", "5min")

        # Assert - 5-minute interval should cache for 5 minutes
        assert ttl == 300

    def test_get_ttl_interval_dependent_1min(self):
        """Test interval-dependent TTL for 1-minute data"""
        # Arrange & Act
        ttl = get_tool_ttl("STOCHASTIC", "1min")

        # Assert - 1-minute interval should cache for 1 minute
        assert ttl == 60

    def test_get_ttl_interval_dependent_hourly(self):
        """Test interval-dependent TTL for hourly data"""
        # Arrange & Act
        ttl = get_tool_ttl("SMA", "60min")

        # Assert - 60-minute interval should cache for 1 hour
        assert ttl == 3600

    def test_get_ttl_interval_dependent_weekly(self):
        """Test interval-dependent TTL for weekly data"""
        # Arrange & Act
        ttl = get_tool_ttl("EMA", "weekly")

        # Assert - Weekly interval should cache for 2 hours
        assert ttl == 7200

    def test_get_ttl_interval_dependent_no_interval_defaults(self):
        """Test that interval-dependent tool without interval uses default"""
        # Arrange & Act
        ttl = get_tool_ttl("RSI")  # No interval provided

        # Assert - Should use default (30 minutes)
        assert ttl == 1800

    def test_get_ttl_unknown_tool_uses_default(self):
        """Test that unknown tool name uses default TTL"""
        # Arrange & Act
        ttl = get_tool_ttl("UNKNOWN_TOOL_NAME")

        # Assert - Should default to 30 minutes
        assert ttl == 1800

    def test_get_ttl_first_party_tools(self):
        """Test TTL for 1st-party analysis tools"""
        # Arrange & Act
        ttl_fib = get_tool_ttl("fibonacci_analysis_tool")
        ttl_stoch = get_tool_ttl("stochastic_analysis_tool")

        # Assert - 1st-party tools use moderate caching (30 minutes)
        assert ttl_fib == 1800
        assert ttl_stoch == 1800

    def test_get_ttl_economic_indicators(self):
        """Test TTL for economic indicators"""
        # Arrange & Act
        ttl_gdp = get_tool_ttl("REAL_GDP")
        ttl_cpi = get_tool_ttl("CPI")
        ttl_unemployment = get_tool_ttl("UNEMPLOYMENT")

        # Assert - Economic indicators change infrequently (24 hours)
        assert ttl_gdp == 86400
        assert ttl_cpi == 86400
        assert ttl_unemployment == 86400

    def test_get_ttl_commodities(self):
        """Test TTL for commodity prices"""
        # Arrange & Act
        ttl_wti = get_tool_ttl("WTI")

        # Assert - Commodities update every 30 minutes
        assert ttl_wti == 1800

    def test_interval_ttl_map_completeness(self):
        """Test that all common intervals are covered"""
        # Assert - Check that standard intervals exist
        assert "1min" in INTERVAL_TTL_MAP
        assert "5min" in INTERVAL_TTL_MAP
        assert "15min" in INTERVAL_TTL_MAP
        assert "30min" in INTERVAL_TTL_MAP
        assert "60min" in INTERVAL_TTL_MAP
        assert "daily" in INTERVAL_TTL_MAP
        assert "weekly" in INTERVAL_TTL_MAP
        assert "monthly" in INTERVAL_TTL_MAP


# ===== API Cost Tracking Tests =====


class TestGetAPICost:
    """Test API cost estimation"""

    def test_get_cost_alphavantage(self):
        """Test API cost for Alpha Vantage calls"""
        # Arrange & Act
        cost = get_api_cost("mcp_alphavantage", "GLOBAL_QUOTE")

        # Assert - Alpha Vantage free tier (tracking only)
        assert cost == 0.00004

    def test_get_cost_first_party_tools(self):
        """Test that 1st-party tools have no API cost"""
        # Arrange & Act
        cost = get_api_cost("1st_party", "fibonacci_analysis_tool")

        # Assert - Local tools have no external API cost
        assert cost == 0.0

    def test_get_cost_unknown_source(self):
        """Test that unknown tool source defaults to zero cost"""
        # Arrange & Act
        cost = get_api_cost("unknown_source", "some_tool")

        # Assert - Unknown sources should default to zero
        assert cost == 0.0


# ===== Integration Tests =====


class TestCacheUtilsIntegration:
    """Test integration scenarios"""

    def test_cache_key_and_ttl_consistency(self):
        """Test that cache key generation works with TTL retrieval"""
        # Arrange
        tool_source = "mcp_alphavantage"
        tool_name = "RSI"
        params = {"symbol": "AAPL", "interval": "daily"}

        # Act
        cache_key = generate_tool_cache_key(tool_source, tool_name, params)
        ttl = get_tool_ttl(tool_name, params.get("interval"))

        # Assert
        assert isinstance(cache_key, str)
        assert isinstance(ttl, int)
        assert ttl > 0
        assert "RSI" in cache_key

    def test_same_params_different_order_produces_same_key(self):
        """Test cache key consistency with different parameter orders"""
        # Arrange
        tool_source = "mcp_alphavantage"
        tool_name = "NEWS_SENTIMENT"

        params1 = {"symbol": "AAPL", "time_from": "20250101T0000", "limit": 10}
        params2 = {"limit": 10, "symbol": "AAPL", "time_from": "20250101T0000"}
        params3 = {"time_from": "20250101T0000", "limit": 10, "symbol": "AAPL"}

        # Act
        key1 = generate_tool_cache_key(tool_source, tool_name, params1)
        key2 = generate_tool_cache_key(tool_source, tool_name, params2)
        key3 = generate_tool_cache_key(tool_source, tool_name, params3)

        # Assert - all keys should be identical
        assert key1 == key2 == key3

    def test_interval_affects_ttl_but_not_key_format(self):
        """Test that interval parameter affects TTL but key format remains valid"""
        # Arrange
        tool_source = "mcp_alphavantage"
        tool_name = "RSI"
        params_1min = {"symbol": "AAPL", "interval": "1min"}
        params_daily = {"symbol": "AAPL", "interval": "daily"}

        # Act
        key_1min = generate_tool_cache_key(tool_source, tool_name, params_1min)
        key_daily = generate_tool_cache_key(tool_source, tool_name, params_daily)
        ttl_1min = get_tool_ttl(tool_name, "1min")
        ttl_daily = get_tool_ttl(tool_name, "daily")

        # Assert
        assert key_1min != key_daily  # Different intervals → different keys
        assert ttl_1min < ttl_daily  # Higher frequency → shorter TTL
        assert "interval=1min" in key_1min
        assert "interval=daily" in key_daily

    def test_cost_tracking_for_all_tool_types(self):
        """Test cost tracking for various tool types"""
        # Arrange
        tools = [
            ("mcp_alphavantage", "GLOBAL_QUOTE"),
            ("mcp_alphavantage", "NEWS_SENTIMENT"),
            ("1st_party", "fibonacci_analysis_tool"),
            ("1st_party", "stochastic_analysis_tool"),
        ]

        # Act & Assert
        for source, name in tools:
            cost = get_api_cost(source, name)
            assert isinstance(cost, float)
            assert cost >= 0  # Cost should never be negative
