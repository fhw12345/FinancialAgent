"""
Cache key generators for the Data Manager Layer.

All cache keys follow the convention: {domain}:{type}:{identifier}

This module provides consistent key generation to ensure:
- No duplicate keys for different data
- Easy pattern matching for invalidation
- Clear organization by data domain
"""


class CacheKeys:
    """
    Cache key generators for consistent naming across the DML.

    Key Convention:
        {domain}:{granularity/type}:{identifier}

    Examples:
        market:daily:AAPL
        macro:treasury:2y
        sentiment:news:technology
        etf:holdings:AIQ
        insights:ai_sector_risk:latest
    """

    # Domain prefixes
    MARKET = "market"
    MACRO = "macro"
    SENTIMENT = "sentiment"
    ETF = "etf"
    INSIGHTS = "insights"

    @staticmethod
    def market(granularity: str, symbol: str) -> str:
        """
        Generate cache key for market OHLCV data.

        Args:
            granularity: Time granularity (daily, 1min, etc.)
            symbol: Stock symbol (uppercase)

        Returns:
            Cache key like 'market:daily:AAPL'
        """
        return f"{CacheKeys.MARKET}:{granularity.lower()}:{symbol.upper()}"

    @staticmethod
    def treasury(maturity: str) -> str:
        """
        Generate cache key for treasury yield data.

        Args:
            maturity: Treasury maturity (2y, 10y, etc.)

        Returns:
            Cache key like 'macro:treasury:2y'
        """
        return f"{CacheKeys.MACRO}:treasury:{maturity.lower()}"

    @staticmethod
    def news_sentiment(topic: str) -> str:
        """
        Generate cache key for news sentiment data.

        Args:
            topic: News topic or ticker symbol

        Returns:
            Cache key like 'sentiment:news:technology'
        """
        return f"{CacheKeys.SENTIMENT}:news:{topic.lower()}"

    @staticmethod
    def ipo_calendar() -> str:
        """
        Generate cache key for IPO calendar.

        Returns:
            Cache key 'macro:ipo:calendar'
        """
        return f"{CacheKeys.MACRO}:ipo:calendar"

    @staticmethod
    def etf_holdings(symbol: str) -> str:
        """
        Generate cache key for ETF holdings.

        Args:
            symbol: ETF symbol

        Returns:
            Cache key like 'etf:holdings:AIQ'
        """
        return f"{CacheKeys.ETF}:holdings:{symbol.upper()}"

    @staticmethod
    def quote(symbol: str) -> str:
        """
        Generate cache key for real-time quote data.

        Args:
            symbol: Stock symbol (uppercase)

        Returns:
            Cache key like 'market:quote:NVDA'
        """
        return f"{CacheKeys.MARKET}:quote:{symbol.upper()}"

    @staticmethod
    def quote_ext(symbol: str) -> str:
        """
        Generate cache key for the extended-hours companion blob (W3.18).

        The yfinance ``Ticker.info`` payload behind ext-hours pricing is
        an expensive HTTP roundtrip — unlike ``fast_info`` it scrapes
        the full quote JSON. We cache it under its own key so the
        primary quote refresh path stays cheap when only the companion
        is stale.

        Returns:
            Cache key like 'market:quote_ext:NVDA'
        """
        return f"{CacheKeys.MARKET}:quote_ext:{symbol.upper()}"

    @staticmethod
    def options(symbol: str) -> str:
        """
        Generate cache key for options chain data.

        Args:
            symbol: Stock symbol (uppercase)

        Returns:
            Cache key like 'market:options:NVDA'
        """
        return f"{CacheKeys.MARKET}:options:{symbol.upper()}"

    @staticmethod
    def pcr_symbol(symbol: str) -> str:
        """
        Generate cache key for per-symbol Put/Call Ratio data.

        Args:
            symbol: Stock symbol (uppercase)

        Returns:
            Cache key like 'market:pcr:NVDA'
        """
        return f"{CacheKeys.MARKET}:pcr:{symbol.upper()}"

    @staticmethod
    def insights(category_id: str, suffix: str = "latest") -> str:
        """
        Generate cache key for computed insight data.

        Args:
            category_id: Insight category (ai_sector_risk, etc.)
            suffix: Key suffix (latest, trend, etc.)

        Returns:
            Cache key like 'insights:ai_sector_risk:latest'
        """
        return f"{CacheKeys.INSIGHTS}:{category_id.lower()}:{suffix.lower()}"

    @staticmethod
    def company_news(symbol: str, from_date: str, to_date: str) -> str:
        """
        Cache key for symbol-scoped company news (Finnhub primary, AV/yfinance fallback).

        Returns:
            Cache key like 'sentiment:news:AAPL:2026-04-01:2026-05-01'
        """
        return f"{CacheKeys.SENTIMENT}:news:{symbol.upper()}:{from_date}:{to_date}"

    @staticmethod
    def insider_trades(symbol: str) -> str:
        """
        Cache key for insider trades (Finnhub primary, AV/yfinance fallback).

        Returns:
            Cache key like 'market:insider:AAPL'
        """
        return f"{CacheKeys.MARKET}:insider:{symbol.upper()}"

    @staticmethod
    def parse(key: str) -> dict[str, str]:
        """
        Parse a cache key into its components.

        Args:
            key: Cache key to parse

        Returns:
            Dict with domain, type, and identifier
        """
        parts = key.split(":")
        if len(parts) < 3:
            return {"raw": key}

        return {
            "domain": parts[0],
            "type": parts[1],
            "identifier": ":".join(parts[2:]),  # Handle multi-part identifiers
        }

    @staticmethod
    def pattern(domain: str, type_prefix: str = "*") -> str:
        """
        Generate a pattern for key matching/invalidation.

        Args:
            domain: Domain to match
            type_prefix: Type prefix to match (default: all)

        Returns:
            Pattern like 'market:daily:*' for Redis SCAN
        """
        return f"{domain}:{type_prefix}:*"
