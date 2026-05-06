"""
Data types for the Data Manager Layer.

These models define the structure of data returned by the DML,
ensuring consistent interfaces across all data consumers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal


class MetricStatus(StrEnum):
    """Status levels for insight metrics."""

    LOW = "low"
    NORMAL = "normal"
    ELEVATED = "elevated"
    HIGH = "high"


class Granularity(StrEnum):
    """Time granularity for OHLCV data."""

    MIN_1 = "1min"
    MIN_5 = "5min"
    MIN_15 = "15min"
    MIN_30 = "30min"
    MIN_60 = "60min"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

    @property
    def is_intraday(self) -> bool:
        """Returns True for granularities that should NOT be cached."""
        return self in (Granularity.MIN_1, Granularity.MIN_5, Granularity.MIN_15)

    @property
    def ttl_seconds(self) -> int:
        """Returns the TTL in seconds for this granularity."""
        ttl_map = {
            Granularity.MIN_1: 0,  # No cache
            Granularity.MIN_5: 0,  # No cache
            Granularity.MIN_15: 0,  # No cache
            Granularity.MIN_30: 300,  # 5 minutes
            Granularity.MIN_60: 900,  # 15 minutes
            Granularity.DAILY: 3600,  # 1 hour
            Granularity.WEEKLY: 7200,  # 2 hours
            Granularity.MONTHLY: 14400,  # 4 hours
        }
        return ttl_map.get(self, 3600)


@dataclass
class OHLCVData:
    """OHLCV bar data for a single time period."""

    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OHLCVData":
        """Create from dictionary."""
        return cls(
            date=datetime.fromisoformat(data["date"]),
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            close=float(data["close"]),
            volume=int(data["volume"]),
        )


@dataclass
class TreasuryData:
    """Treasury yield data for a single date."""

    date: datetime
    yield_value: float
    maturity: str  # "2y", "10y", etc.

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date.isoformat(),
            "yield_value": self.yield_value,
            "maturity": self.maturity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TreasuryData":
        """Create from dictionary."""
        return cls(
            date=datetime.fromisoformat(data["date"]),
            yield_value=float(data["yield_value"]),
            maturity=data["maturity"],
        )


@dataclass
class NewsData:
    """News sentiment data for a single article/aggregation."""

    date: datetime
    sentiment_score: float  # -1.0 to 1.0
    ticker_relevance: float  # 0.0 to 1.0
    title: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date.isoformat(),
            "sentiment_score": self.sentiment_score,
            "ticker_relevance": self.ticker_relevance,
            "title": self.title,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NewsData":
        """Create from dictionary."""
        return cls(
            date=datetime.fromisoformat(data["date"]),
            sentiment_score=float(data["sentiment_score"]),
            ticker_relevance=float(data["ticker_relevance"]),
            title=data.get("title", ""),
            source=data.get("source", ""),
        )


@dataclass
class IPOData:
    """IPO calendar entry."""

    date: datetime
    name: str
    exchange: str
    price_range_low: float | None = None
    price_range_high: float | None = None
    shares_offered: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date.isoformat(),
            "name": self.name,
            "exchange": self.exchange,
            "price_range_low": self.price_range_low,
            "price_range_high": self.price_range_high,
            "shares_offered": self.shares_offered,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IPOData":
        """Create from dictionary."""
        return cls(
            date=datetime.fromisoformat(data["date"]),
            name=data["name"],
            exchange=data["exchange"],
            price_range_low=data.get("price_range_low"),
            price_range_high=data.get("price_range_high"),
            shares_offered=data.get("shares_offered"),
        )


@dataclass
class QuoteData:
    """Real-time quote data from GLOBAL_QUOTE."""

    symbol: str
    price: float
    volume: int
    latest_trading_day: str
    previous_close: float
    change: float
    change_percent: float
    open: float
    high: float
    low: float
    session: Literal["pre", "regular", "post", "closed"] = "regular"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "symbol": self.symbol,
            "price": self.price,
            "volume": self.volume,
            "latest_trading_day": self.latest_trading_day,
            "previous_close": self.previous_close,
            "change": self.change,
            "change_percent": self.change_percent,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "session": self.session,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QuoteData":
        """Create from dictionary."""
        return cls(
            symbol=data["symbol"],
            price=float(data["price"]),
            volume=int(data["volume"]),
            latest_trading_day=data["latest_trading_day"],
            previous_close=float(data["previous_close"]),
            change=float(data["change"]),
            change_percent=float(data["change_percent"]),
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            session=data.get("session", "regular"),
        )


@dataclass
class OptionContract:
    """Single option contract from HISTORICAL_OPTIONS."""

    contract_id: str
    symbol: str
    expiration: datetime
    strike: float
    option_type: str  # "call" or "put"
    last_price: float
    bid: float
    ask: float
    volume: int
    open_interest: int
    implied_volatility: float
    delta: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "contract_id": self.contract_id,
            "symbol": self.symbol,
            "expiration": self.expiration.isoformat(),
            "strike": self.strike,
            "option_type": self.option_type,
            "last_price": self.last_price,
            "bid": self.bid,
            "ask": self.ask,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "implied_volatility": self.implied_volatility,
            "delta": self.delta,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OptionContract":
        """Create from dictionary."""
        return cls(
            contract_id=data["contract_id"],
            symbol=data["symbol"],
            expiration=datetime.fromisoformat(data["expiration"]),
            strike=float(data["strike"]),
            option_type=data["option_type"],
            last_price=float(data["last_price"]),
            bid=float(data["bid"]),
            ask=float(data["ask"]),
            volume=int(data["volume"]),
            open_interest=int(data["open_interest"]),
            implied_volatility=float(data["implied_volatility"]),
            delta=data.get("delta"),
        )


@dataclass
class TrendPoint:
    """Single data point in a trend series."""

    date: datetime
    score: float
    status: MetricStatus

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "date": self.date.isoformat(),
            "score": self.score,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrendPoint":
        """Create from dictionary."""
        return cls(
            date=datetime.fromisoformat(data["date"]),
            score=float(data["score"]),
            status=MetricStatus(data["status"]),
        )


@dataclass
class SymbolPCRData:
    """
    Put/Call Ratio data for a single symbol.

    Cached per-symbol to enable reuse between AI tools and AI Sector Risk metric.
    Uses ATM Dollar-Weighted methodology: Notional = OI × Price × 100.
    """

    symbol: str
    current_price: float
    atm_zone_low: float
    atm_zone_high: float
    put_notional_mm: float  # Put notional in millions
    call_notional_mm: float  # Call notional in millions
    contracts_analyzed: int
    pcr: float  # Put/Call Ratio
    interpretation: str  # Human-readable interpretation
    calculated_at: datetime
    # Filter parameters used for calculation
    atm_zone_pct: float = 0.15  # ATM zone ±15%
    min_premium: float = 0.50  # Minimum option premium
    min_oi: int = 500  # Minimum open interest

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "symbol": self.symbol,
            "current_price": self.current_price,
            "atm_zone_low": self.atm_zone_low,
            "atm_zone_high": self.atm_zone_high,
            "put_notional_mm": self.put_notional_mm,
            "call_notional_mm": self.call_notional_mm,
            "contracts_analyzed": self.contracts_analyzed,
            "pcr": self.pcr,
            "interpretation": self.interpretation,
            "calculated_at": self.calculated_at.isoformat(),
            "atm_zone_pct": self.atm_zone_pct,
            "min_premium": self.min_premium,
            "min_oi": self.min_oi,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SymbolPCRData":
        """Create from dictionary."""
        return cls(
            symbol=data["symbol"],
            current_price=float(data["current_price"]),
            atm_zone_low=float(data["atm_zone_low"]),
            atm_zone_high=float(data["atm_zone_high"]),
            put_notional_mm=float(data["put_notional_mm"]),
            call_notional_mm=float(data["call_notional_mm"]),
            contracts_analyzed=int(data["contracts_analyzed"]),
            pcr=float(data["pcr"]),
            interpretation=data["interpretation"],
            calculated_at=datetime.fromisoformat(data["calculated_at"]),
            atm_zone_pct=float(data.get("atm_zone_pct", 0.15)),
            min_premium=float(data.get("min_premium", 0.50)),
            min_oi=int(data.get("min_oi", 500)),
        )


@dataclass
class SharedDataContext:
    """
    Container for pre-fetched shared data.

    Used by the prefetch pattern to eliminate duplicate API calls
    when multiple metrics need the same data source.
    """

    ohlcv: dict[str, list[OHLCVData]] = field(default_factory=dict)
    treasury: dict[str, list[TreasuryData]] = field(default_factory=dict)
    news: dict[str, list[NewsData]] = field(default_factory=dict)
    ipo: list[IPOData] = field(default_factory=list)
    quotes: dict[str, QuoteData] = field(default_factory=dict)
    options: dict[str, list[OptionContract]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    def get_ohlcv(self, symbol: str) -> list[OHLCVData] | None:
        """Get OHLCV data for a symbol, or None if not fetched."""
        return self.ohlcv.get(symbol.upper())

    def get_treasury(self, maturity: str) -> list[TreasuryData] | None:
        """Get treasury data for a maturity, or None if not fetched."""
        return self.treasury.get(maturity.lower())

    def get_quote(self, symbol: str) -> QuoteData | None:
        """Get quote data for a symbol, or None if not fetched."""
        return self.quotes.get(symbol.upper())

    def get_options(self, symbol: str) -> list[OptionContract] | None:
        """Get options chain for a symbol, or None if not fetched."""
        return self.options.get(symbol.upper())

    def has_errors(self) -> bool:
        """Check if any fetch errors occurred."""
        return len(self.errors) > 0


class DataFetchError(Exception):
    """Exception raised when data fetch fails."""

    def __init__(self, message: str, source: str | None = None):
        self.message = message
        self.source = source
        super().__init__(f"{source}: {message}" if source else message)
