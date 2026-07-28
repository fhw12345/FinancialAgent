"""Market-calendar timezone helpers for symbol-scoped date validation."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

DEFAULT_MARKET_TIMEZONE = "America/New_York"
MARKET_TIMEZONE_SUFFIXES = {
    ".HK": "Asia/Hong_Kong",
    ".SS": "Asia/Shanghai",
    ".SZ": "Asia/Shanghai",
    ".T": "Asia/Tokyo",
    ".L": "Europe/London",
}


def market_timezone(symbol: str | None) -> str:
    """Resolve a supported exchange timezone from the ticker suffix."""
    normalized = (symbol or "").upper()
    for suffix, timezone in MARKET_TIMEZONE_SUFFIXES.items():
        if normalized.endswith(suffix):
            return timezone
    return DEFAULT_MARKET_TIMEZONE


def market_today(symbol: str | None, now: datetime | None = None) -> date:
    """Return today's calendar date in the symbol's market timezone."""
    timezone = ZoneInfo(market_timezone(symbol))
    current = now.astimezone(timezone) if now else datetime.now(timezone)
    return current.date()
