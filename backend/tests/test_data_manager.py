"""
Unit tests for the Data Manager Layer (DML).

Tests cover:
- Cache key generation and consistency
- OHLCV data fetching with correct cache behavior
- Treasury data caching
- Pre-fetch shared data pattern
- Cache hit/miss logging
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from src.services.data_manager import (
    CacheKeys,
    CacheOperations,
    DataManager,
    Granularity,
    OHLCVData,
    OptionContract,
    QuoteData,
    SharedDataContext,
    SymbolPCRData,
    TreasuryData,
)


class TestCacheKeys:
    """Test cache key generation."""

    def test_market_key_format(self):
        """Verify market key follows {domain}:{granularity}:{symbol} format."""
        key = CacheKeys.market("daily", "AAPL")
        assert key == "market:daily:AAPL"

    def test_market_key_normalizes_case(self):
        """Verify symbol is uppercased, granularity lowercased."""
        key = CacheKeys.market("DAILY", "aapl")
        assert key == "market:daily:AAPL"

    def test_treasury_key_format(self):
        """Verify treasury key format."""
        key = CacheKeys.treasury("2y")
        assert key == "macro:treasury:2y"

    def test_treasury_key_normalizes(self):
        """Verify treasury maturity is lowercased."""
        key = CacheKeys.treasury("10Y")
        assert key == "macro:treasury:10y"

    def test_news_sentiment_key(self):
        """Verify news sentiment key format."""
        key = CacheKeys.news_sentiment("technology")
        assert key == "sentiment:news:technology"

    def test_ipo_calendar_key(self):
        """Verify IPO calendar key format."""
        key = CacheKeys.ipo_calendar()
        assert key == "macro:ipo:calendar"

    def test_insights_key_default_suffix(self):
        """Verify insights key with default suffix."""
        key = CacheKeys.insights("ai_sector_risk")
        assert key == "insights:ai_sector_risk:latest"

    def test_insights_key_custom_suffix(self):
        """Verify insights key with custom suffix."""
        key = CacheKeys.insights("ai_sector_risk", "trend")
        assert key == "insights:ai_sector_risk:trend"

    def test_quote_key_format(self):
        """Verify quote key format."""
        key = CacheKeys.quote("NVDA")
        assert key == "market:quote:NVDA"

    def test_quote_key_normalizes_case(self):
        """Verify symbol is uppercased."""
        key = CacheKeys.quote("nvda")
        assert key == "market:quote:NVDA"

    def test_options_key_format(self):
        """Verify options key format."""
        key = CacheKeys.options("NVDA")
        assert key == "market:options:NVDA"

    def test_options_key_normalizes_case(self):
        """Verify symbol is uppercased."""
        key = CacheKeys.options("nvda")
        assert key == "market:options:NVDA"

    def test_pcr_symbol_key_format(self):
        """Verify PCR symbol key format."""
        key = CacheKeys.pcr_symbol("NVDA")
        assert key == "market:pcr:NVDA"

    def test_pcr_symbol_key_normalizes_case(self):
        """Verify symbol is uppercased."""
        key = CacheKeys.pcr_symbol("nvda")
        assert key == "market:pcr:NVDA"

    def test_parse_key(self):
        """Verify key parsing."""
        parsed = CacheKeys.parse("market:daily:AAPL")
        assert parsed["domain"] == "market"
        assert parsed["type"] == "daily"
        assert parsed["identifier"] == "AAPL"

    def test_pattern_generation(self):
        """Verify pattern generation for invalidation."""
        pattern = CacheKeys.pattern("market", "daily")
        assert pattern == "market:daily:*"


class TestGranularity:
    """Test granularity enum behavior."""

    def test_intraday_no_cache(self):
        """1min, 5min, 15min should not be cached."""
        assert Granularity.MIN_1.is_intraday is True
        assert Granularity.MIN_5.is_intraday is True
        assert Granularity.MIN_15.is_intraday is True

    def test_longer_intervals_cached(self):
        """30min+ should be cached."""
        assert Granularity.MIN_30.is_intraday is False
        assert Granularity.MIN_60.is_intraday is False
        assert Granularity.DAILY.is_intraday is False

    def test_ttl_values(self):
        """Verify TTL values for each granularity."""
        assert Granularity.MIN_1.ttl_seconds == 0
        assert Granularity.MIN_5.ttl_seconds == 0
        assert Granularity.MIN_30.ttl_seconds == 300  # 5 min
        assert Granularity.MIN_60.ttl_seconds == 900  # 15 min
        assert Granularity.DAILY.ttl_seconds == 3600  # 1 hour


class TestDataTypes:
    """Test data type serialization."""

    def test_ohlcv_to_dict(self):
        """Verify OHLCV serialization."""
        data = OHLCVData(
            date=datetime(2025, 1, 15, 10, 30, tzinfo=UTC),
            open=150.0,
            high=151.5,
            low=149.5,
            close=151.0,
            volume=1000000,
        )
        d = data.to_dict()
        assert d["open"] == 150.0
        assert d["close"] == 151.0
        assert "2025-01-15" in d["date"]

    def test_ohlcv_from_dict(self):
        """Verify OHLCV deserialization."""
        d = {
            "date": "2025-01-15T10:30:00+00:00",
            "open": 150.0,
            "high": 151.5,
            "low": 149.5,
            "close": 151.0,
            "volume": 1000000,
        }
        data = OHLCVData.from_dict(d)
        assert data.open == 150.0
        assert data.volume == 1000000

    def test_treasury_round_trip(self):
        """Verify Treasury data serialization round-trip."""
        original = TreasuryData(
            date=datetime(2025, 1, 15, tzinfo=UTC),
            yield_value=4.25,
            maturity="2y",
        )
        d = original.to_dict()
        restored = TreasuryData.from_dict(d)
        assert restored.yield_value == original.yield_value
        assert restored.maturity == original.maturity

    def test_quote_data_to_dict(self):
        """Verify QuoteData serialization."""
        data = QuoteData(
            symbol="NVDA",
            price=142.50,
            volume=25000000,
            latest_trading_day="2025-01-15",
            previous_close=140.00,
            change=2.50,
            change_percent=1.79,
            open=141.00,
            high=143.00,
            low=140.50,
        )
        d = data.to_dict()
        assert d["symbol"] == "NVDA"
        assert d["price"] == 142.50
        assert d["change_percent"] == 1.79

    def test_quote_data_from_dict(self):
        """Verify QuoteData deserialization."""
        d = {
            "symbol": "NVDA",
            "price": 142.50,
            "volume": 25000000,
            "latest_trading_day": "2025-01-15",
            "previous_close": 140.00,
            "change": 2.50,
            "change_percent": 1.79,
            "open": 141.00,
            "high": 143.00,
            "low": 140.50,
        }
        data = QuoteData.from_dict(d)
        assert data.symbol == "NVDA"
        assert data.price == 142.50
        assert data.volume == 25000000

    def test_option_contract_to_dict(self):
        """Verify OptionContract serialization."""
        data = OptionContract(
            contract_id="NVDA250117C00150000",
            symbol="NVDA",
            expiration=datetime(2025, 1, 17, tzinfo=UTC),
            strike=150.00,
            option_type="call",
            last_price=5.50,
            bid=5.40,
            ask=5.60,
            volume=1500,
            open_interest=8500,
            implied_volatility=0.42,
            delta=0.55,
        )
        d = data.to_dict()
        assert d["contract_id"] == "NVDA250117C00150000"
        assert d["strike"] == 150.00
        assert d["option_type"] == "call"
        assert d["open_interest"] == 8500

    def test_option_contract_from_dict(self):
        """Verify OptionContract deserialization."""
        d = {
            "contract_id": "NVDA250117P00150000",
            "symbol": "NVDA",
            "expiration": "2025-01-17T00:00:00+00:00",
            "strike": 150.00,
            "option_type": "put",
            "last_price": 3.25,
            "bid": 3.20,
            "ask": 3.30,
            "volume": 2000,
            "open_interest": 12000,
            "implied_volatility": 0.38,
            "delta": -0.35,
        }
        data = OptionContract.from_dict(d)
        assert data.contract_id == "NVDA250117P00150000"
        assert data.option_type == "put"
        assert data.open_interest == 12000
        assert data.delta == -0.35

    def test_symbol_pcr_data_to_dict(self):
        """Verify SymbolPCRData serialization."""
        data = SymbolPCRData(
            symbol="NVDA",
            current_price=142.50,
            atm_zone_low=121.13,
            atm_zone_high=163.88,
            put_notional_mm=25.50,
            call_notional_mm=42.30,
            contracts_analyzed=156,
            pcr=0.60,
            interpretation="Bullish sentiment (contrarian bearish)",
            calculated_at=datetime(2025, 1, 15, 14, 30, tzinfo=UTC),
            atm_zone_pct=0.15,
            min_premium=0.50,
            min_oi=500,
        )
        d = data.to_dict()
        assert d["symbol"] == "NVDA"
        assert d["current_price"] == 142.50
        assert d["atm_zone_low"] == 121.13
        assert d["atm_zone_high"] == 163.88
        assert d["put_notional_mm"] == 25.50
        assert d["call_notional_mm"] == 42.30
        assert d["contracts_analyzed"] == 156
        assert d["pcr"] == 0.60
        assert d["interpretation"] == "Bullish sentiment (contrarian bearish)"
        assert "2025-01-15" in d["calculated_at"]
        assert d["atm_zone_pct"] == 0.15
        assert d["min_premium"] == 0.50
        assert d["min_oi"] == 500

    def test_symbol_pcr_data_from_dict(self):
        """Verify SymbolPCRData deserialization."""
        d = {
            "symbol": "AAPL",
            "current_price": 185.25,
            "atm_zone_low": 157.46,
            "atm_zone_high": 213.04,
            "put_notional_mm": 18.20,
            "call_notional_mm": 15.80,
            "contracts_analyzed": 98,
            "pcr": 1.15,
            "interpretation": "Moderate bearish sentiment",
            "calculated_at": "2025-01-15T10:00:00+00:00",
            "atm_zone_pct": 0.15,
            "min_premium": 0.50,
            "min_oi": 500,
        }
        data = SymbolPCRData.from_dict(d)
        assert data.symbol == "AAPL"
        assert data.current_price == 185.25
        assert data.pcr == 1.15
        assert data.contracts_analyzed == 98
        assert data.atm_zone_pct == 0.15
        assert data.min_oi == 500

    def test_symbol_pcr_data_round_trip(self):
        """Verify SymbolPCRData serialization round-trip."""
        original = SymbolPCRData(
            symbol="TSLA",
            current_price=250.00,
            atm_zone_low=212.50,
            atm_zone_high=287.50,
            put_notional_mm=33.45,
            call_notional_mm=28.90,
            contracts_analyzed=210,
            pcr=1.16,
            interpretation="Moderate bearish",
            calculated_at=datetime(2025, 1, 15, 12, 0, tzinfo=UTC),
        )
        d = original.to_dict()
        restored = SymbolPCRData.from_dict(d)
        assert restored.symbol == original.symbol
        assert restored.current_price == original.current_price
        assert restored.pcr == original.pcr
        assert restored.interpretation == original.interpretation
        assert restored.contracts_analyzed == original.contracts_analyzed

    def test_symbol_pcr_data_defaults(self):
        """Verify SymbolPCRData uses default filter values."""
        data = SymbolPCRData(
            symbol="GOOGL",
            current_price=180.00,
            atm_zone_low=153.00,
            atm_zone_high=207.00,
            put_notional_mm=10.00,
            call_notional_mm=12.00,
            contracts_analyzed=50,
            pcr=0.83,
            interpretation="Neutral",
            calculated_at=datetime.now(UTC),
        )
        # Verify defaults are applied
        assert data.atm_zone_pct == 0.15
        assert data.min_premium == 0.50
        assert data.min_oi == 500


class TestSharedDataContext:
    """Test shared data context container."""

    def test_get_ohlcv_by_symbol(self):
        """Verify OHLCV lookup by symbol."""
        ctx = SharedDataContext()
        data = [
            OHLCVData(
                date=datetime.now(UTC),
                open=150,
                high=151,
                low=149,
                close=150.5,
                volume=1000,
            )
        ]
        ctx.ohlcv["AAPL"] = data

        assert ctx.get_ohlcv("AAPL") == data
        # Note: get_ohlcv uses symbol.upper() so lookup is case-insensitive
        assert ctx.get_ohlcv("MSFT") is None

    def test_get_treasury_by_maturity(self):
        """Verify treasury lookup by maturity."""
        ctx = SharedDataContext()
        data = [TreasuryData(date=datetime.now(UTC), yield_value=4.25, maturity="2y")]
        ctx.treasury["2y"] = data

        assert ctx.get_treasury("2y") == data
        assert ctx.get_treasury("10y") is None

    def test_has_errors(self):
        """Verify error tracking."""
        ctx = SharedDataContext()
        assert ctx.has_errors() is False

        ctx.errors["ohlcv:AAPL"] = "API timeout"
        assert ctx.has_errors() is True

    def test_get_quote_by_symbol(self):
        """Verify quote lookup by symbol."""
        ctx = SharedDataContext()
        quote = QuoteData(
            symbol="NVDA",
            price=142.50,
            volume=25000000,
            latest_trading_day="2025-01-15",
            previous_close=140.00,
            change=2.50,
            change_percent=1.79,
            open=141.00,
            high=143.00,
            low=140.50,
        )
        ctx.quotes["NVDA"] = quote

        assert ctx.get_quote("NVDA") == quote
        assert ctx.get_quote("nvda") == quote  # Case-insensitive
        assert ctx.get_quote("MSFT") is None

    def test_get_options_by_symbol(self):
        """Verify options lookup by symbol."""
        ctx = SharedDataContext()
        options = [
            OptionContract(
                contract_id="NVDA250117C00150000",
                symbol="NVDA",
                expiration=datetime.now(UTC),
                strike=150.00,
                option_type="call",
                last_price=5.50,
                bid=5.40,
                ask=5.60,
                volume=1500,
                open_interest=8500,
                implied_volatility=0.42,
            )
        ]
        ctx.options["NVDA"] = options

        assert ctx.get_options("NVDA") == options
        assert ctx.get_options("nvda") == options  # Case-insensitive
        assert ctx.get_options("MSFT") is None


class TestCacheOperations:
    """Test cache operations wrapper."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        redis.delete = AsyncMock(return_value=1)
        redis.exists = AsyncMock(return_value=False)
        return redis

    @pytest.fixture
    def cache_ops(self, mock_redis):
        """Create CacheOperations with mock Redis."""
        return CacheOperations(mock_redis)

    @pytest.mark.asyncio
    async def test_get_cache_miss(self, cache_ops, mock_redis):
        """Verify cache miss returns None."""
        result = await cache_ops.get("nonexistent:key")
        assert result is None
        mock_redis.get.assert_called_once_with("nonexistent:key")

    @pytest.mark.asyncio
    async def test_get_cache_hit_dict(self, cache_ops, mock_redis):
        """Verify cache hit returns parsed dict."""
        mock_redis.get = AsyncMock(return_value='{"foo": "bar"}')
        result = await cache_ops.get("test:key")
        assert result == {"foo": "bar"}

    @pytest.mark.asyncio
    async def test_set_with_ttl(self, cache_ops, mock_redis):
        """Verify set calls Redis with TTL."""
        await cache_ops.set("test:key", {"data": 123}, 3600)
        mock_redis.set.assert_called_once()
        # Verify the key and TTL were passed
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "test:key"

    @pytest.mark.asyncio
    async def test_set_skips_zero_ttl(self, cache_ops, mock_redis):
        """Verify zero TTL skips caching."""
        result = await cache_ops.set("test:key", {"data": 123}, 0)
        assert result is False
        mock_redis.set.assert_not_called()


class TestDataManager:
    """Test DataManager core functionality."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis cache that simulates cache miss then stores."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)  # Cache miss
        redis.set = AsyncMock()
        redis.delete = AsyncMock(return_value=1)
        redis.exists = AsyncMock(return_value=False)
        return redis

    @pytest.fixture
    def sample_df(self):
        """Sample DataFrame for OHLCV data."""
        return pd.DataFrame(
            {
                "Open": [150.0, 151.0],
                "High": [151.5, 152.0],
                "Low": [149.5, 150.5],
                "Close": [151.0, 151.5],
                "Volume": [1000000, 1100000],
            },
            index=pd.to_datetime(["2025-01-15", "2025-01-14"]),
        )

    @pytest.fixture
    def mock_av_service(self, sample_df):
        """Create mock Alpha Vantage service."""
        service = AsyncMock()
        service.get_daily_bars = AsyncMock(return_value=sample_df)
        service.get_intraday_bars = AsyncMock(return_value=sample_df)
        service.get_weekly_bars = AsyncMock(return_value=sample_df)
        service.get_monthly_bars = AsyncMock(return_value=sample_df)

        # Mock treasury
        treasury_df = pd.DataFrame(
            {
                "value": [4.25, 4.20],
            },
            index=pd.to_datetime(["2025-01-15", "2025-01-14"]),
        )
        service.get_treasury_yield = AsyncMock(return_value=treasury_df)

        return service

    @pytest.fixture
    def data_manager(self, mock_redis, mock_av_service):
        """Create DataManager with mocks."""
        return DataManager(mock_redis, mock_av_service)

    @pytest.mark.asyncio
    async def test_get_ohlcv_daily_fetches_on_miss(self, data_manager, mock_av_service):
        """Daily OHLCV should fetch from API on cache miss.

        DataManager now tries yfinance first; we patch its bars adapter to
        raise so the fallback chain falls through to the AV mock — that's the
        path this test was originally written to cover.
        """
        with patch(
            "src.services.market_data.yfinance_bars.get_bars",
            side_effect=RuntimeError("yfinance disabled in unit test"),
        ):
            result = await data_manager.get_ohlcv("AAPL", "daily")

        # Should have fetched from AV after yfinance failed
        mock_av_service.get_daily_bars.assert_called_once()
        assert len(result) == 2
        assert result[0].close == 151.0

    @pytest.mark.asyncio
    async def test_get_ohlcv_intraday_always_fresh(
        self, data_manager, mock_redis, mock_av_service
    ):
        """Intraday OHLCV should NOT be cached - always fresh.

        Same yfinance-disabled patch as the daily test: we want this unit test
        to exercise the AV branch deterministically without hitting the live
        Yahoo endpoint.
        """
        with patch(
            "src.services.market_data.yfinance_bars.get_bars",
            side_effect=RuntimeError("yfinance disabled in unit test"),
        ):
            result = await data_manager.get_ohlcv("AAPL", "1min")

        assert len(result) == 2
        mock_av_service.get_intraday_bars.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_treasury_fetches_on_miss(self, data_manager, mock_av_service):
        """Treasury data should fall back to AV when FRED is unavailable.

        Patch FREDService.get_series to raise so the fallback chain falls
        through to AV — same path this test was originally written for.
        """
        with patch(
            "src.services.market_data.fred.FREDService.get_series",
            side_effect=RuntimeError("fred disabled in unit test"),
        ):
            result = await data_manager.get_treasury("2y")

        mock_av_service.get_treasury_yield.assert_called_once()
        assert len(result) == 2
        assert result[0].yield_value == 4.25
        assert result[0].maturity == "2y"

    @pytest.mark.asyncio
    async def test_prefetch_shared_parallel(self, data_manager, mock_av_service):
        """Prefetch should fetch multiple items in parallel.

        Patch yfinance bars + FRED off so OHLCV + treasury both fall through
        to AV mocks, as before.
        """
        with (
            patch(
                "src.services.market_data.yfinance_bars.get_bars",
                side_effect=RuntimeError("yfinance disabled in unit test"),
            ),
            patch(
                "src.services.market_data.fred.FREDService.get_series",
                side_effect=RuntimeError("fred disabled in unit test"),
            ),
        ):
            context = await data_manager.prefetch_shared(
                symbols=["NVDA", "MSFT"],
                treasury_maturities=["2y", "10y"],
            )

        # Should have data for symbols (from parallel fetches)
        assert "NVDA" in context.ohlcv
        assert "MSFT" in context.ohlcv
        assert "2y" in context.treasury
        assert "10y" in context.treasury
        # Verify multiple calls were made
        assert mock_av_service.get_daily_bars.call_count == 2
        assert mock_av_service.get_treasury_yield.call_count == 2

    @pytest.mark.asyncio
    async def test_prefetch_continues_on_partial_error(self, mock_redis, sample_df):
        """Prefetch should continue even if one fetch fails."""
        # Create service where first call fails, second succeeds
        mock_av_service = AsyncMock()
        call_count = [0]

        async def mock_daily_bars(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("API Error")
            return sample_df

        mock_av_service.get_daily_bars = mock_daily_bars
        mock_av_service.get_treasury_yield = AsyncMock(return_value=sample_df)

        dm = DataManager(mock_redis, mock_av_service)
        context = await dm.prefetch_shared(symbols=["FAIL", "MSFT"])

        # Should have error for first symbol
        assert context.has_errors()
        # But still have data for second one
        assert "MSFT" in context.ohlcv


class TestCacheKeyConsistency:
    """Test that cache keys are consistent across the codebase."""

    def test_all_keys_follow_convention(self):
        """All generated keys should follow {domain}:{type}:{identifier}."""
        keys = [
            CacheKeys.market("daily", "AAPL"),
            CacheKeys.treasury("2y"),
            CacheKeys.news_sentiment("technology"),
            CacheKeys.ipo_calendar(),
            CacheKeys.insights("ai_sector_risk", "latest"),
            CacheKeys.etf_holdings("AIQ"),
            CacheKeys.quote("NVDA"),
            CacheKeys.options("NVDA"),
            CacheKeys.pcr_symbol("NVDA"),
        ]

        for key in keys:
            parts = key.split(":")
            assert len(parts) >= 3, f"Key {key} doesn't follow convention"
            assert parts[0] in ["market", "macro", "sentiment", "insights", "etf"]


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
