"""
Unit tests for Data Manager types.

Tests all dataclasses and their serialization methods.
"""

from datetime import UTC, datetime

from src.services.data_manager.types import (
    DataFetchError,
    Granularity,
    IPOData,
    MetricStatus,
    NewsData,
    OHLCVData,
    OptionContract,
    QuoteData,
    SharedDataContext,
    SymbolPCRData,
    TreasuryData,
    TrendPoint,
)

# ===== MetricStatus Tests =====


class TestMetricStatus:
    """Test MetricStatus enum."""

    def test_values(self):
        """Test enum values."""
        assert MetricStatus.LOW == "low"
        assert MetricStatus.NORMAL == "normal"
        assert MetricStatus.ELEVATED == "elevated"
        assert MetricStatus.HIGH == "high"


# ===== Granularity Tests =====


class TestGranularity:
    """Test Granularity enum."""

    def test_values(self):
        """Test enum values."""
        assert Granularity.MIN_1 == "1min"
        assert Granularity.DAILY == "daily"
        assert Granularity.MONTHLY == "monthly"

    def test_is_intraday(self):
        """Test is_intraday property."""
        assert Granularity.MIN_1.is_intraday is True
        assert Granularity.MIN_5.is_intraday is True
        assert Granularity.MIN_15.is_intraday is True
        assert Granularity.MIN_30.is_intraday is False
        assert Granularity.DAILY.is_intraday is False

    def test_ttl_seconds(self):
        """Test ttl_seconds property."""
        assert Granularity.MIN_1.ttl_seconds == 0
        assert Granularity.MIN_30.ttl_seconds == 300
        assert Granularity.DAILY.ttl_seconds == 3600
        assert Granularity.MONTHLY.ttl_seconds == 14400


# ===== OHLCVData Tests =====


class TestOHLCVData:
    """Test OHLCVData dataclass."""

    def test_create(self):
        """Test creating OHLCV data."""
        now = datetime.now(UTC)
        data = OHLCVData(
            date=now,
            open=100.0,
            high=105.0,
            low=98.0,
            close=103.0,
            volume=1000000,
        )

        assert data.open == 100.0
        assert data.close == 103.0
        assert data.volume == 1000000

    def test_to_dict(self):
        """Test to_dict serialization."""
        now = datetime(2025, 1, 10, 12, 0, 0, tzinfo=UTC)
        data = OHLCVData(
            date=now,
            open=100.0,
            high=105.0,
            low=98.0,
            close=103.0,
            volume=1000000,
        )

        d = data.to_dict()

        assert d["open"] == 100.0
        assert "date" in d
        assert d["volume"] == 1000000

    def test_from_dict(self):
        """Test from_dict deserialization."""
        d = {
            "date": "2025-01-10T12:00:00+00:00",
            "open": 100.0,
            "high": 105.0,
            "low": 98.0,
            "close": 103.0,
            "volume": 1000000,
        }

        data = OHLCVData.from_dict(d)

        assert data.open == 100.0
        assert data.volume == 1000000


# ===== TreasuryData Tests =====


class TestTreasuryData:
    """Test TreasuryData dataclass."""

    def test_create(self):
        """Test creating treasury data."""
        now = datetime.now(UTC)
        data = TreasuryData(date=now, yield_value=4.25, maturity="10y")

        assert data.yield_value == 4.25
        assert data.maturity == "10y"

    def test_to_dict(self):
        """Test to_dict serialization."""
        now = datetime(2025, 1, 10, tzinfo=UTC)
        data = TreasuryData(date=now, yield_value=4.25, maturity="10y")

        d = data.to_dict()

        assert d["yield_value"] == 4.25
        assert d["maturity"] == "10y"

    def test_from_dict(self):
        """Test from_dict deserialization."""
        d = {
            "date": "2025-01-10T00:00:00+00:00",
            "yield_value": 4.25,
            "maturity": "10y",
        }

        data = TreasuryData.from_dict(d)

        assert data.yield_value == 4.25
        assert data.maturity == "10y"


# ===== NewsData Tests =====


class TestNewsData:
    """Test NewsData dataclass."""

    def test_create_with_defaults(self):
        """Test creating news data with defaults."""
        now = datetime.now(UTC)
        data = NewsData(date=now, sentiment_score=0.5, ticker_relevance=0.8)

        assert data.sentiment_score == 0.5
        assert data.title == ""
        assert data.source == ""

    def test_create_full(self):
        """Test creating news data with all fields."""
        now = datetime.now(UTC)
        data = NewsData(
            date=now,
            sentiment_score=0.75,
            ticker_relevance=0.9,
            title="Stock Surges",
            source="Reuters",
        )

        assert data.title == "Stock Surges"
        assert data.source == "Reuters"

    def test_to_dict(self):
        """Test to_dict serialization."""
        now = datetime(2025, 1, 10, tzinfo=UTC)
        data = NewsData(date=now, sentiment_score=0.5, ticker_relevance=0.8)

        d = data.to_dict()

        assert d["sentiment_score"] == 0.5
        assert d["ticker_relevance"] == 0.8

    def test_from_dict(self):
        """Test from_dict deserialization."""
        d = {
            "date": "2025-01-10T00:00:00+00:00",
            "sentiment_score": 0.5,
            "ticker_relevance": 0.8,
            "title": "Test Title",
            "source": "Test Source",
        }

        data = NewsData.from_dict(d)

        assert data.title == "Test Title"
        assert data.source == "Test Source"


# ===== IPOData Tests =====


class TestIPOData:
    """Test IPOData dataclass."""

    def test_create_minimal(self):
        """Test creating IPO data with required fields only."""
        now = datetime.now(UTC)
        data = IPOData(date=now, name="Test Company", exchange="NASDAQ")

        assert data.name == "Test Company"
        assert data.price_range_low is None

    def test_create_full(self):
        """Test creating IPO data with all fields."""
        now = datetime.now(UTC)
        data = IPOData(
            date=now,
            name="Test Company",
            exchange="NASDAQ",
            price_range_low=10.0,
            price_range_high=12.0,
            shares_offered=1000000,
        )

        assert data.price_range_high == 12.0
        assert data.shares_offered == 1000000

    def test_to_dict(self):
        """Test to_dict serialization."""
        now = datetime(2025, 1, 10, tzinfo=UTC)
        data = IPOData(date=now, name="Test Co", exchange="NYSE")

        d = data.to_dict()

        assert d["name"] == "Test Co"
        assert d["price_range_low"] is None

    def test_from_dict(self):
        """Test from_dict deserialization."""
        d = {
            "date": "2025-01-10T00:00:00+00:00",
            "name": "Test Co",
            "exchange": "NYSE",
            "price_range_low": 15.0,
            "price_range_high": 18.0,
            "shares_offered": 500000,
        }

        data = IPOData.from_dict(d)

        assert data.shares_offered == 500000


# ===== QuoteData Tests =====


class TestQuoteData:
    """Test QuoteData dataclass."""

    def test_create(self):
        """Test creating quote data."""
        data = QuoteData(
            symbol="AAPL",
            price=150.0,
            volume=10000000,
            latest_trading_day="2025-01-10",
            previous_close=148.0,
            change=2.0,
            change_percent=1.35,
            open=149.0,
            high=151.0,
            low=148.5,
        )

        assert data.symbol == "AAPL"
        assert data.price == 150.0

    def test_to_dict(self):
        """Test to_dict serialization."""
        data = QuoteData(
            symbol="AAPL",
            price=150.0,
            volume=10000000,
            latest_trading_day="2025-01-10",
            previous_close=148.0,
            change=2.0,
            change_percent=1.35,
            open=149.0,
            high=151.0,
            low=148.5,
        )

        d = data.to_dict()

        assert d["symbol"] == "AAPL"
        assert d["change_percent"] == 1.35

    def test_from_dict(self):
        """Test from_dict deserialization."""
        d = {
            "symbol": "MSFT",
            "price": 300.0,
            "volume": 5000000,
            "latest_trading_day": "2025-01-10",
            "previous_close": 298.0,
            "change": 2.0,
            "change_percent": 0.67,
            "open": 299.0,
            "high": 301.0,
            "low": 297.0,
        }

        data = QuoteData.from_dict(d)

        assert data.symbol == "MSFT"


# ===== OptionContract Tests =====


class TestOptionContract:
    """Test OptionContract dataclass."""

    def test_create(self):
        """Test creating option contract."""
        now = datetime.now(UTC)
        data = OptionContract(
            contract_id="AAPL250117C00150000",
            symbol="AAPL",
            expiration=now,
            strike=150.0,
            option_type="call",
            last_price=5.0,
            bid=4.9,
            ask=5.1,
            volume=1000,
            open_interest=5000,
            implied_volatility=0.25,
        )

        assert data.option_type == "call"
        assert data.delta is None

    def test_to_dict(self):
        """Test to_dict serialization."""
        now = datetime(2025, 1, 17, tzinfo=UTC)
        data = OptionContract(
            contract_id="AAPL250117C00150000",
            symbol="AAPL",
            expiration=now,
            strike=150.0,
            option_type="call",
            last_price=5.0,
            bid=4.9,
            ask=5.1,
            volume=1000,
            open_interest=5000,
            implied_volatility=0.25,
            delta=0.55,
        )

        d = data.to_dict()

        assert d["option_type"] == "call"
        assert d["delta"] == 0.55

    def test_from_dict(self):
        """Test from_dict deserialization."""
        d = {
            "contract_id": "AAPL250117P00140000",
            "symbol": "AAPL",
            "expiration": "2025-01-17T00:00:00+00:00",
            "strike": 140.0,
            "option_type": "put",
            "last_price": 3.0,
            "bid": 2.9,
            "ask": 3.1,
            "volume": 500,
            "open_interest": 2000,
            "implied_volatility": 0.30,
            "delta": -0.35,
        }

        data = OptionContract.from_dict(d)

        assert data.option_type == "put"
        assert data.delta == -0.35


# ===== TrendPoint Tests =====


class TestTrendPoint:
    """Test TrendPoint dataclass."""

    def test_create(self):
        """Test creating trend point."""
        now = datetime.now(UTC)
        data = TrendPoint(date=now, score=65.0, status=MetricStatus.ELEVATED)

        assert data.score == 65.0
        assert data.status == MetricStatus.ELEVATED

    def test_to_dict(self):
        """Test to_dict serialization."""
        now = datetime(2025, 1, 10, tzinfo=UTC)
        data = TrendPoint(date=now, score=45.0, status=MetricStatus.NORMAL)

        d = data.to_dict()

        assert d["score"] == 45.0
        assert d["status"] == "normal"

    def test_from_dict(self):
        """Test from_dict deserialization."""
        d = {
            "date": "2025-01-10T00:00:00+00:00",
            "score": 80.0,
            "status": "high",
        }

        data = TrendPoint.from_dict(d)

        assert data.score == 80.0
        assert data.status == MetricStatus.HIGH


# ===== SymbolPCRData Tests =====


class TestSymbolPCRData:
    """Test SymbolPCRData dataclass."""

    def test_create(self):
        """Test creating PCR data."""
        now = datetime.now(UTC)
        data = SymbolPCRData(
            symbol="SPY",
            current_price=500.0,
            atm_zone_low=425.0,
            atm_zone_high=575.0,
            put_notional_mm=100.0,
            call_notional_mm=120.0,
            contracts_analyzed=500,
            pcr=0.83,
            interpretation="Bullish",
            calculated_at=now,
        )

        assert data.symbol == "SPY"
        assert data.pcr == 0.83

    def test_to_dict(self):
        """Test to_dict serialization."""
        now = datetime(2025, 1, 10, tzinfo=UTC)
        data = SymbolPCRData(
            symbol="SPY",
            current_price=500.0,
            atm_zone_low=425.0,
            atm_zone_high=575.0,
            put_notional_mm=100.0,
            call_notional_mm=120.0,
            contracts_analyzed=500,
            pcr=0.83,
            interpretation="Bullish",
            calculated_at=now,
        )

        d = data.to_dict()

        assert d["symbol"] == "SPY"
        assert d["atm_zone_pct"] == 0.15  # default

    def test_from_dict(self):
        """Test from_dict deserialization."""
        d = {
            "symbol": "QQQ",
            "current_price": 400.0,
            "atm_zone_low": 340.0,
            "atm_zone_high": 460.0,
            "put_notional_mm": 50.0,
            "call_notional_mm": 40.0,
            "contracts_analyzed": 200,
            "pcr": 1.25,
            "interpretation": "Bearish",
            "calculated_at": "2025-01-10T00:00:00+00:00",
        }

        data = SymbolPCRData.from_dict(d)

        assert data.pcr == 1.25
        assert data.interpretation == "Bearish"


# ===== SharedDataContext Tests =====


class TestSharedDataContext:
    """Test SharedDataContext dataclass."""

    def test_create_empty(self):
        """Test creating empty context."""
        ctx = SharedDataContext()

        assert ctx.ohlcv == {}
        assert ctx.treasury == {}
        assert ctx.errors == {}

    def test_get_ohlcv(self):
        """Test get_ohlcv method."""
        ctx = SharedDataContext()
        now = datetime.now(UTC)
        data = OHLCVData(date=now, open=100, high=105, low=98, close=103, volume=1000)
        ctx.ohlcv["AAPL"] = [data]

        result = ctx.get_ohlcv("AAPL")
        assert result is not None
        assert len(result) == 1

        result = ctx.get_ohlcv("aapl")  # Test case insensitivity (works via upper())
        assert result is not None  # aapl.upper() = AAPL finds the data
        assert len(result) == 1  # Same data returned

        # Non-existent symbol returns None
        result = ctx.get_ohlcv("MSFT")
        assert result is None

    def test_get_treasury(self):
        """Test get_treasury method."""
        ctx = SharedDataContext()
        now = datetime.now(UTC)
        data = TreasuryData(date=now, yield_value=4.25, maturity="10y")
        ctx.treasury["10y"] = [data]

        result = ctx.get_treasury("10y")
        assert result is not None

    def test_get_quote(self):
        """Test get_quote method."""
        ctx = SharedDataContext()
        data = QuoteData(
            symbol="AAPL",
            price=150.0,
            volume=1000,
            latest_trading_day="2025-01-10",
            previous_close=148.0,
            change=2.0,
            change_percent=1.35,
            open=149.0,
            high=151.0,
            low=148.5,
        )
        ctx.quotes["AAPL"] = data

        result = ctx.get_quote("AAPL")
        assert result is not None

    def test_get_options(self):
        """Test get_options method."""
        ctx = SharedDataContext()
        now = datetime.now(UTC)
        contract = OptionContract(
            contract_id="test",
            symbol="AAPL",
            expiration=now,
            strike=150.0,
            option_type="call",
            last_price=5.0,
            bid=4.9,
            ask=5.1,
            volume=100,
            open_interest=500,
            implied_volatility=0.25,
        )
        ctx.options["AAPL"] = [contract]

        result = ctx.get_options("AAPL")
        assert result is not None

    def test_has_errors(self):
        """Test has_errors method."""
        ctx = SharedDataContext()
        assert ctx.has_errors() is False

        ctx.errors["AAPL"] = "API error"
        assert ctx.has_errors() is True


# ===== DataFetchError Tests =====


class TestDataFetchError:
    """Test DataFetchError exception."""

    def test_create_without_source(self):
        """Test creating error without source."""
        error = DataFetchError("Connection failed")

        assert error.message == "Connection failed"
        assert error.source is None
        assert str(error) == "Connection failed"

    def test_create_with_source(self):
        """Test creating error with source."""
        error = DataFetchError("API limit exceeded", source="Alpha Vantage")

        assert error.message == "API limit exceeded"
        assert error.source == "Alpha Vantage"
        assert "Alpha Vantage" in str(error)
