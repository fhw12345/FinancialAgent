"""
Data Manager - Single source of truth for all data access.

The DataManager provides a unified interface for:
- Market OHLCV data (with smart caching based on granularity)
- Macro indicators (Treasury yields, IPO calendar)
- News sentiment
- Computed insights

Key Features:
- Automatic caching with TTL based on data type
- No caching for real-time/intraday data
- Pre-fetch pattern for shared data
- Parallel fetching with asyncio.gather
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import structlog

from .cache import CacheOperations
from .keys import CacheKeys
from .types import (
    DataFetchError,
    Granularity,
    IPOData,
    NewsData,
    OHLCVData,
    OptionContract,
    QuoteData,
    SharedDataContext,
    SymbolPCRData,
    TreasuryData,
)

logger = structlog.get_logger(__name__)


class DataManager:
    """
    Single source of truth for all data access in the application.

    All data consumers (charts, AI tools, insights, analysis) should
    use this class instead of calling services directly.

    Cache Strategy:
    - Intraday (1min-15min): NO CACHE - always fresh
    - 30min-60min: Short TTL (5-15 min)
    - Daily+: Standard TTL (1-4 hours)
    - Macro data: 1-24 hour TTL based on update frequency
    """

    # TTL constants (seconds)
    TTL_TREASURY = 3600  # 1 hour
    TTL_NEWS = 3600  # 1 hour
    TTL_IPO = 86400  # 24 hours
    TTL_INSIGHTS = 86400  # 24 hours
    TTL_QUOTE = 300  # 5 minutes (real-time quotes)
    TTL_OPTIONS = 3600  # 1 hour (options chains - daily data)
    TTL_PCR = 3600  # 1 hour (per-symbol Put/Call Ratio)

    def __init__(
        self,
        redis_cache: Any,
        alpha_vantage_service: Any,
        finnhub_service: Any = None,
    ):
        """
        Initialize the Data Manager.

        Args:
            redis_cache: RedisCache instance for caching
            alpha_vantage_service: AlphaVantageMarketDataService for API calls
            finnhub_service: Optional FinnhubService; primary for quote/news/insider
        """
        self._cache = CacheOperations(redis_cache)
        self._av_service = alpha_vantage_service
        self._finnhub_service = finnhub_service
        logger.info(
            "data_manager_initialized",
            finnhub_enabled=finnhub_service is not None,
        )

    # =========================================================================
    # Market Data (OHLCV)
    # =========================================================================

    async def get_ohlcv(
        self,
        symbol: str,
        granularity: str | Granularity,
        outputsize: str = "compact",
    ) -> list[OHLCVData]:
        """
        Get OHLCV bars for a symbol.

        Caching:
        - 1min/5min/15min: NO CACHE (returns fresh data)
        - 30min/60min: 5-15 min TTL
        - daily/weekly/monthly: 1-4 hour TTL

        Args:
            symbol: Stock symbol (e.g., "AAPL")
            granularity: Time granularity ("daily", "1min", etc.)
            outputsize: "compact" (100 points) or "full" (all data)

        Returns:
            List of OHLCVData objects, newest first

        Raises:
            DataFetchError: If fetch fails
        """
        # Normalize granularity
        if isinstance(granularity, str):
            try:
                gran = Granularity(granularity.lower())
            except ValueError:
                gran = Granularity.DAILY
        else:
            gran = granularity

        symbol = symbol.upper()
        cache_key = CacheKeys.market(gran.value, symbol)

        # Skip cache for intraday
        if gran.is_intraday:
            logger.debug("ohlcv_no_cache", symbol=symbol, granularity=gran.value)
            return await self._fetch_ohlcv(symbol, gran, outputsize)

        # Try cache first
        async def fetch_func():
            data = await self._fetch_ohlcv(symbol, gran, outputsize)
            return [d.to_dict() for d in data]

        cached = await self._cache.get_with_fetch(
            cache_key, fetch_func, gran.ttl_seconds
        )

        if cached is None:
            raise DataFetchError(f"Failed to fetch OHLCV for {symbol}", "market")

        return [OHLCVData.from_dict(d) for d in cached]

    async def _fetch_ohlcv(
        self,
        symbol: str,
        granularity: Granularity,
        outputsize: str,
    ) -> list[OHLCVData]:
        """Internal: Fetch OHLCV bars. yfinance is the primary source (no key,
        no daily cap); Alpha Vantage is the fallback when yfinance fails."""
        # Provider 1: yfinance — same OHLCV columns, ~unlimited rate, no key
        try:
            from src.services.market_data import yfinance_bars

            df = await yfinance_bars.get_bars(
                symbol, granularity.value, outputsize
            )
            return self._dataframe_to_ohlcv(df)
        except Exception as e:
            logger.warning(
                "ohlcv_provider_failed",
                provider="yfinance",
                symbol=symbol,
                granularity=granularity.value,
                error=str(e),
            )

        # Provider 2: Alpha Vantage (last resort, burns 25/day quota)
        try:
            if granularity.is_intraday or granularity in (
                Granularity.MIN_30,
                Granularity.MIN_60,
            ):
                df = await self._av_service.get_intraday_bars(
                    symbol=symbol,
                    interval=granularity.value,
                    outputsize=outputsize,
                )
            else:
                method_map = {
                    Granularity.DAILY: self._av_service.get_daily_bars,
                    Granularity.WEEKLY: self._av_service.get_weekly_bars,
                    Granularity.MONTHLY: self._av_service.get_monthly_bars,
                }
                method = method_map.get(granularity, self._av_service.get_daily_bars)
                df = await method(symbol=symbol, outputsize=outputsize)

            return self._dataframe_to_ohlcv(df)

        except Exception as e:
            logger.error(
                "ohlcv_all_providers_failed",
                symbol=symbol,
                granularity=granularity.value,
                error=str(e),
            )
            raise DataFetchError(str(e), "all_providers") from e

    def _dataframe_to_ohlcv(self, df: pd.DataFrame) -> list[OHLCVData]:
        """Convert pandas DataFrame to list of OHLCVData."""
        if df is None or df.empty:
            return []

        result = []
        for idx, row in df.iterrows():
            # Handle both timezone-aware and naive datetimes
            if isinstance(idx, pd.Timestamp):
                dt = idx.to_pydatetime()
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
            else:
                dt = datetime.fromisoformat(str(idx))

            result.append(
                OHLCVData(
                    date=dt,
                    open=float(row.get("Open", row.get("open", 0))),
                    high=float(row.get("High", row.get("high", 0))),
                    low=float(row.get("Low", row.get("low", 0))),
                    close=float(row.get("Close", row.get("close", 0))),
                    volume=int(row.get("Volume", row.get("volume", 0))),
                )
            )

        # Sort newest first
        result.sort(key=lambda x: x.date, reverse=True)
        return result

    # =========================================================================
    # Macro Data (Treasury, IPO)
    # =========================================================================

    async def get_treasury(
        self,
        maturity: str,
        interval: str = "daily",
    ) -> list[TreasuryData]:
        """
        Get treasury yield data.

        Args:
            maturity: Treasury maturity ("2y", "10y", "5y", etc.)
            interval: Data interval ("daily", "weekly", "monthly")

        Returns:
            List of TreasuryData objects, newest first

        Raises:
            DataFetchError: If fetch fails
        """
        # Normalize maturity format
        maturity_normalized = maturity.lower().replace("year", "y")
        cache_key = CacheKeys.treasury(maturity_normalized)

        async def fetch_func():
            data = await self._fetch_treasury(maturity, interval)
            return [d.to_dict() for d in data]

        cached = await self._cache.get_with_fetch(
            cache_key, fetch_func, self.TTL_TREASURY
        )

        if cached is None:
            raise DataFetchError(f"Failed to fetch treasury {maturity}", "macro")

        return [TreasuryData.from_dict(d) for d in cached]

    async def _fetch_treasury(self, maturity: str, interval: str) -> list[TreasuryData]:
        """Internal: Fetch treasury yield. FRED is the primary source (no daily
        cap, authoritative since FRED *is* the Federal Reserve); Alpha Vantage
        is the fallback when FRED is unreachable or no FRED key is configured.

        `interval` is currently ignored — FRED returns daily values; weekly /
        monthly aggregation can be added later if needed.
        """
        # Provider 1: FRED (free, no daily cap, authoritative)
        try:
            from src.core.config import get_settings
            from src.services.market_data.fred import FREDService

            settings = get_settings()
            if settings.fred_api_key:
                # FRED series IDs for constant-maturity Treasury rates
                fred_map = {
                    "3m": "DGS3MO",
                    "2y": "DGS2",
                    "5y": "DGS5",
                    "10y": "DGS10",
                    "30y": "DGS30",
                }
                series_id = fred_map.get(maturity.lower())
                if series_id is not None:
                    fred = FREDService(api_key=settings.fred_api_key)
                    try:
                        df = await fred.get_series(series_id, days=365)
                    finally:
                        await fred.close()
                    if df is not None and not df.empty:
                        result: list[TreasuryData] = []
                        for idx, row in df.iterrows():
                            dt = (
                                idx.to_pydatetime()
                                if isinstance(idx, pd.Timestamp)
                                else datetime.fromisoformat(str(idx))
                            )
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=UTC)
                            result.append(
                                TreasuryData(
                                    date=dt,
                                    yield_value=float(row.get("value", row.iloc[0])),
                                    maturity=maturity.lower(),
                                )
                            )
                        result.sort(key=lambda x: x.date, reverse=True)
                        return result
        except Exception as e:
            logger.warning(
                "treasury_provider_failed",
                provider="fred",
                maturity=maturity,
                error=str(e),
            )

        # Provider 2: Alpha Vantage (fallback)
        try:
            maturity_map = {
                "2y": "2year",
                "5y": "5year",
                "10y": "10year",
                "30y": "30year",
                "3m": "3month",
            }
            api_maturity = maturity_map.get(maturity.lower(), maturity.lower())

            df = await self._av_service.get_treasury_yield(
                maturity=api_maturity, interval=interval
            )

            if df is None or df.empty:
                return []

            result = []
            for idx, row in df.iterrows():
                if isinstance(idx, pd.Timestamp):
                    dt = idx.to_pydatetime()
                else:
                    dt = datetime.fromisoformat(str(idx))

                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)

                result.append(
                    TreasuryData(
                        date=dt,
                        yield_value=float(row.get("value", row.iloc[0])),
                        maturity=maturity.lower(),
                    )
                )

            result.sort(key=lambda x: x.date, reverse=True)
            return result

        except Exception as e:
            logger.error("treasury_all_providers_failed", maturity=maturity, error=str(e))
            raise DataFetchError(str(e), "all_providers") from e

    async def get_ipo_calendar(self) -> list[IPOData]:
        """
        Get IPO calendar for upcoming IPOs.

        Returns:
            List of IPOData objects for upcoming IPOs

        Raises:
            DataFetchError: If fetch fails
        """
        cache_key = CacheKeys.ipo_calendar()

        async def fetch_func():
            data = await self._fetch_ipo_calendar()
            return [d.to_dict() for d in data]

        cached = await self._cache.get_with_fetch(cache_key, fetch_func, self.TTL_IPO)

        if cached is None:
            return []  # IPO calendar can be empty

        return [IPOData.from_dict(d) for d in cached]

    async def _fetch_ipo_calendar(self) -> list[IPOData]:
        """Internal: Fetch IPO calendar from Alpha Vantage."""
        try:
            # Check if method exists on service
            if not hasattr(self._av_service, "get_ipo_calendar"):
                logger.warning("ipo_calendar_not_available")
                return []

            df = await self._av_service.get_ipo_calendar()

            if df is None or df.empty:
                return []

            result = []
            for _, row in df.iterrows():
                # Parse IPO date
                ipo_date = row.get("ipoDate", row.get("date", ""))
                if not ipo_date:
                    continue

                try:
                    dt = pd.to_datetime(ipo_date).to_pydatetime()
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=UTC)
                except Exception:
                    continue

                # Parse price range
                price_low = None
                price_high = None
                price_range = row.get("priceRangeLow", row.get("price", ""))
                if price_range:
                    try:
                        price_low = float(row.get("priceRangeLow", 0))
                        price_high = float(row.get("priceRangeHigh", 0))
                    except (ValueError, TypeError):
                        pass

                result.append(
                    IPOData(
                        date=dt,
                        name=str(row.get("name", row.get("company", ""))),
                        exchange=str(row.get("exchange", "")),
                        price_range_low=price_low,
                        price_range_high=price_high,
                        shares_offered=row.get("shares", None),
                    )
                )

            return result

        except Exception as e:
            logger.error("ipo_fetch_failed", error=str(e))
            raise DataFetchError(str(e), "alpha_vantage") from e

    # =========================================================================
    # News Sentiment
    # =========================================================================

    async def get_news_sentiment(
        self,
        topic: str | None = None,
        tickers: list[str] | None = None,
    ) -> list[NewsData]:
        """
        Get news sentiment data.

        Args:
            topic: News topic (e.g., "technology", "earnings")
            tickers: List of ticker symbols to filter by

        Returns:
            List of NewsData objects

        Raises:
            DataFetchError: If fetch fails
        """
        cache_key = CacheKeys.news_sentiment(topic or "general")

        async def fetch_func():
            data = await self._fetch_news_sentiment(topic, tickers)
            return [d.to_dict() for d in data]

        cached = await self._cache.get_with_fetch(cache_key, fetch_func, self.TTL_NEWS)

        if cached is None:
            return []

        return [NewsData.from_dict(d) for d in cached]

    async def _fetch_news_sentiment(
        self,
        topic: str | None,
        tickers: list[str] | None,
    ) -> list[NewsData]:
        """Internal: Fetch news sentiment from Alpha Vantage."""
        try:
            if not hasattr(self._av_service, "get_news_sentiment"):
                logger.warning("news_sentiment_not_available")
                return []

            data = await self._av_service.get_news_sentiment(
                tickers=",".join(tickers) if tickers else None,
                topics=topic,
            )

            if not data or "feed" not in data:
                return []

            result = []
            for item in data.get("feed", []):
                try:
                    # Parse time
                    time_str = item.get("time_published", "")
                    dt = datetime.strptime(time_str[:15], "%Y%m%dT%H%M%S")
                    dt = dt.replace(tzinfo=UTC)

                    # Get overall sentiment
                    sentiment = float(item.get("overall_sentiment_score", 0))

                    # Get ticker relevance (average if multiple)
                    relevance = 1.0
                    ticker_sentiment = item.get("ticker_sentiment", [])
                    if ticker_sentiment:
                        relevances = [
                            float(t.get("relevance_score", 0)) for t in ticker_sentiment
                        ]
                        relevance = sum(relevances) / len(relevances)

                    result.append(
                        NewsData(
                            date=dt,
                            sentiment_score=sentiment,
                            ticker_relevance=relevance,
                            title=item.get("title", ""),
                            source=item.get("source", ""),
                        )
                    )
                except Exception as e:
                    logger.debug("news_item_parse_error", error=str(e))
                    continue

            # Sort newest first
            result.sort(key=lambda x: x.date, reverse=True)
            return result

        except Exception as e:
            logger.error("news_fetch_failed", topic=topic, error=str(e))
            raise DataFetchError(str(e), "alpha_vantage") from e

    # =========================================================================
    # Quotes and Options (Story 2.6: Put/Call Ratio)
    # =========================================================================

    async def get_quote(self, symbol: str) -> QuoteData:
        """
        Get real-time quote for a symbol.

        Uses existing QuotesMixin.get_quote() from Alpha Vantage.
        Short TTL since prices change frequently.

        Args:
            symbol: Stock symbol (e.g., "NVDA")

        Returns:
            QuoteData object with current price, volume, etc.

        Raises:
            DataFetchError: If fetch fails
        """
        symbol = symbol.upper()
        cache_key = CacheKeys.quote(symbol)

        async def fetch_func() -> dict[str, Any]:
            data = await self._fetch_quote(symbol)
            return data.to_dict()

        cached = await self._cache.get_with_fetch(cache_key, fetch_func, self.TTL_QUOTE)

        if cached is None:
            raise DataFetchError(f"Failed to fetch quote for {symbol}", "market")

        # Type assertion: cached is dict from get_with_fetch
        if not isinstance(cached, dict):
            raise DataFetchError(f"Invalid cache data for {symbol}", "cache")

        return QuoteData.from_dict(cached)

    async def _fetch_quote(self, symbol: str) -> QuoteData:
        """Internal: Fetch quote with Finnhub → yfinance → AV fallback chain.

        yfinance moved ahead of Alpha Vantage because the AV free-tier key is
        capped at 25 req/day and gets exhausted in a few page loads. yfinance
        has no key, no daily cap, and returns the same fields. AV is kept as
        a last-resort fallback for the rare case Yahoo's public endpoint is
        down.
        """
        # Provider 1: Finnhub (primary if configured — fastest + most accurate)
        if self._finnhub_service is not None:
            try:
                return await self._finnhub_service.fetch_quote(symbol)
            except Exception as e:
                logger.warning(
                    "quote_provider_failed",
                    provider="finnhub",
                    symbol=symbol,
                    error=str(e),
                )

        # Provider 2: yfinance (free, no daily cap)
        try:
            return await self._fetch_quote_yfinance(symbol)
        except Exception as e:
            logger.warning(
                "quote_provider_failed",
                provider="yfinance",
                symbol=symbol,
                error=str(e),
            )

        # Provider 3: Alpha Vantage (last resort — burns the 25/day quota)
        try:
            data = await self._av_service.get_quote(symbol)
            return QuoteData(
                symbol=data["symbol"],
                price=data["price"],
                volume=data["volume"],
                latest_trading_day=data["latest_trading_day"],
                previous_close=data["previous_close"],
                change=data["change"],
                change_percent=float(data["change_percent"]),
                open=data["open"],
                high=data["high"],
                low=data["low"],
                # AV GLOBAL_QUOTE is RTH-only; session metadata is regular.
                session="regular",
            )
        except Exception as e:
            logger.error("quote_all_providers_failed", symbol=symbol, error=str(e))
            raise DataFetchError(
                f"All providers failed for {symbol}: {e}", "all_providers"
            ) from e

    @staticmethod
    async def _fetch_quote_yfinance(symbol: str) -> QuoteData:
        """yfinance fallback. Runs sync yfinance in thread to keep async loop free.

        Pulls a 1-minute prepost-inclusive history bar to derive the actual
        trading session ("pre" / "regular" / "post" / "closed") from the last
        bar's timestamp via get_market_session(). Falls back to "regular" only
        if no bars are available.
        """
        import asyncio

        import yfinance as yf

        # Function-local import to avoid circular import at module load time
        # (services.market_data.__init__ imports submodules that may transitively
        # import data_manager).
        from src.services.market_data import get_market_session

        def _sync() -> QuoteData:
            t = yf.Ticker(symbol)
            fi = t.fast_info
            price = float(fi.last_price)
            prev = float(fi.previous_close)
            change = price - prev
            change_pct = (change / prev * 100) if prev else 0.0

            # Derive session from latest minute bar including extended hours.
            session: str = "regular"
            try:
                hist = t.history(period="1d", interval="1m", prepost=True)
                if hist is not None and len(hist):
                    last_ts = hist.index[-1]
                    if last_ts.tz is None:
                        last_ts = last_ts.tz_localize("UTC")
                    session = get_market_session(last_ts)
            except Exception:
                # Keep default "regular" — session is best-effort metadata.
                pass

            return QuoteData(
                symbol=symbol.upper(),
                price=price,
                volume=int(getattr(fi, "last_volume", 0) or 0),
                latest_trading_day=datetime.now(UTC).strftime("%Y-%m-%d"),
                previous_close=prev,
                change=change,
                change_percent=change_pct,
                open=float(getattr(fi, "open", 0.0) or 0.0),
                high=float(getattr(fi, "day_high", 0.0) or 0.0),
                low=float(getattr(fi, "day_low", 0.0) or 0.0),
                session=session,  # type: ignore[arg-type]
            )

        return await asyncio.to_thread(_sync)

    # =========================================================================
    # Company News (Finnhub primary → AV → yfinance)
    # =========================================================================

    async def get_company_news(
        self, symbol: str, from_date: str, to_date: str
    ) -> list[NewsData]:
        """
        Symbol-scoped company news with three-provider fallback.

        Args:
            symbol: Ticker symbol
            from_date: YYYY-MM-DD inclusive
            to_date: YYYY-MM-DD inclusive
        """
        symbol = symbol.upper()
        cache_key = CacheKeys.company_news(symbol, from_date, to_date)

        async def fetch_func():
            data = await self._fetch_company_news(symbol, from_date, to_date)
            return [d.to_dict() for d in data]

        cached = await self._cache.get_with_fetch(cache_key, fetch_func, self.TTL_NEWS)
        if cached is None:
            return []
        return [NewsData.from_dict(d) for d in cached]

    async def _fetch_company_news(
        self, symbol: str, from_date: str, to_date: str
    ) -> list[NewsData]:
        if self._finnhub_service is not None:
            try:
                return await self._finnhub_service.fetch_company_news(
                    symbol, from_date, to_date
                )
            except Exception as e:
                logger.warning(
                    "news_provider_failed",
                    provider="finnhub",
                    symbol=symbol,
                    error=str(e),
                )

        # yfinance: free, no daily cap. Headlines only — sentiment_score is 0.
        # If a caller needs sentiment scoring it'll fall through to AV below.
        try:
            return await self._fetch_company_news_yfinance(symbol)
        except Exception as e:
            logger.warning(
                "news_provider_failed",
                provider="yfinance",
                symbol=symbol,
                error=str(e),
            )

        # AV last resort (NEWS_SENTIMENT scoped to ticker — burns 25/day quota)
        try:
            return await self._fetch_news_sentiment(topic=None, tickers=[symbol])
        except Exception as e:
            logger.error("news_all_providers_failed", symbol=symbol, error=str(e))
            raise DataFetchError(
                f"All providers failed for news/{symbol}: {e}", "all_providers"
            ) from e

    @staticmethod
    async def _fetch_company_news_yfinance(symbol: str) -> list[NewsData]:
        import asyncio

        import yfinance as yf

        def _sync() -> list[NewsData]:
            items = yf.Ticker(symbol).news or []
            out: list[NewsData] = []
            for it in items:
                ts = it.get("providerPublishTime") or 0
                try:
                    dt = (
                        datetime.fromtimestamp(int(ts), tz=UTC)
                        if ts
                        else datetime.now(UTC)
                    )
                except (TypeError, ValueError):
                    dt = datetime.now(UTC)
                out.append(
                    NewsData(
                        date=dt,
                        sentiment_score=0.0,
                        ticker_relevance=1.0,
                        title=str(it.get("title", "")),
                        source=str(it.get("publisher", "yfinance")),
                    )
                )
            return out

        return await asyncio.to_thread(_sync)

    # =========================================================================
    # Insider Trades (Finnhub primary → AV → yfinance)
    # =========================================================================

    async def get_insider_trades(self, symbol: str) -> list[dict[str, Any]]:
        """
        Recent insider transactions with three-provider fallback.
        Returns a list of dicts (provider-shape preserved); callers format.
        """
        symbol = symbol.upper()
        cache_key = CacheKeys.insider_trades(symbol)

        async def fetch_func():
            return await self._fetch_insider_trades(symbol)

        cached = await self._cache.get_with_fetch(cache_key, fetch_func, self.TTL_NEWS)
        return cached or []

    async def _fetch_insider_trades(self, symbol: str) -> list[dict[str, Any]]:
        if self._finnhub_service is not None:
            try:
                return await self._finnhub_service.fetch_insider_transactions(symbol)
            except Exception as e:
                logger.warning(
                    "insider_provider_failed",
                    provider="finnhub",
                    symbol=symbol,
                    error=str(e),
                )

        # AV fallback: INSIDER_TRANSACTIONS (premium endpoint, may 403)
        try:
            if hasattr(self._av_service, "get_insider_transactions"):
                data = await self._av_service.get_insider_transactions(symbol)
                if isinstance(data, dict) and "data" in data:
                    return list(data["data"])
                if isinstance(data, list):
                    return data
        except Exception as e:
            logger.warning(
                "insider_provider_failed",
                provider="alpha_vantage",
                symbol=symbol,
                error=str(e),
            )

        try:
            return await self._fetch_insider_trades_yfinance(symbol)
        except Exception as e:
            logger.error("insider_all_providers_failed", symbol=symbol, error=str(e))
            raise DataFetchError(
                f"All providers failed for insider/{symbol}: {e}", "all_providers"
            ) from e

    @staticmethod
    async def _fetch_insider_trades_yfinance(symbol: str) -> list[dict[str, Any]]:
        import asyncio

        import yfinance as yf

        def _sync() -> list[dict[str, Any]]:
            df = yf.Ticker(symbol).insider_transactions
            if df is None or df.empty:
                return []
            return df.to_dict(orient="records")

        return await asyncio.to_thread(_sync)

    # =========================================================================
    # Point-in-time price lookup (used by decision-tracking PnL service)
    # =========================================================================

    async def get_price_on_date(
        self, symbol: str, target_date: datetime, max_forward_days: int = 5
    ) -> float | None:
        """
        Return the closing price for `symbol` on `target_date`, or the next
        trading day within `max_forward_days` if the target was a weekend/holiday.

        Tries Alpha Vantage daily bars first; falls back to yfinance if AV is
        rate-limited or returns empty (Finnhub free tier doesn't include
        historical daily bars). Returns None if no bar can be located.
        """
        from datetime import timedelta as _td

        symbol = symbol.upper()
        if target_date.tzinfo is None:
            target_date = target_date.replace(tzinfo=UTC)
        target_day = target_date.date()

        # Provider 1: Alpha Vantage via the OHLCV pipeline (cached)
        bars: list = []
        try:
            bars = await self.get_ohlcv(symbol, "daily", outputsize="full")
        except DataFetchError as e:
            logger.warning("price_on_date_av_failed", symbol=symbol, error=str(e))

        by_day = {b.date.date(): b.close for b in bars}
        for offset in range(max_forward_days + 1):
            day = target_day + _td(days=offset)
            if day in by_day:
                return float(by_day[day])

        # Provider 2: yfinance fallback for historical bars
        try:
            return await self._price_on_date_yfinance(
                symbol, target_date, max_forward_days
            )
        except Exception as e:
            logger.warning("price_on_date_yfinance_failed", symbol=symbol, error=str(e))
            return None

    @staticmethod
    async def _price_on_date_yfinance(
        symbol: str, target_date: datetime, max_forward_days: int
    ) -> float | None:
        import asyncio
        from datetime import timedelta as _td

        import yfinance as yf

        def _sync() -> float | None:
            # Pad both directions so weekend/holiday + market-still-open scenarios
            # both resolve. Forward scan picks the next trading day; if none yet
            # (target is today and close not posted), back off to the previous
            # trading day so the snapshot lands rather than retry forever.
            start = (target_date - _td(days=4)).date()
            end = (target_date + _td(days=max_forward_days + 2)).date()
            df = yf.Ticker(symbol).history(
                start=start.isoformat(), end=end.isoformat(), auto_adjust=False
            )
            if df is None or df.empty:
                return None
            available = {
                idx.strftime("%Y-%m-%d"): row["Close"] for idx, row in df.iterrows()
            }
            target_day = target_date.date()

            # Forward scan first (preferred)
            for offset in range(max_forward_days + 1):
                key = (target_day + _td(days=offset)).isoformat()
                if key in available:
                    return float(available[key])
            # Backward fallback (handles weekend horizons when forward window
            # ends today/future and yfinance hasn't posted the next close yet)
            for offset in range(1, 4):
                key = (target_day - _td(days=offset)).isoformat()
                if key in available:
                    return float(available[key])
            return None

        return await asyncio.to_thread(_sync)

    async def get_options(self, symbol: str) -> list[OptionContract]:
        """
        Get options chain for a symbol.

        Fetches from Alpha Vantage HISTORICAL_OPTIONS endpoint.
        Returns previous trading day's options data.

        Args:
            symbol: Stock symbol (e.g., "NVDA")

        Returns:
            List of OptionContract objects

        Raises:
            DataFetchError: If fetch fails
        """
        symbol = symbol.upper()
        cache_key = CacheKeys.options(symbol)

        async def fetch_func() -> list[dict[str, Any]]:
            data = await self._fetch_options(symbol)
            return [d.to_dict() for d in data]

        cached = await self._cache.get_with_fetch(
            cache_key, fetch_func, self.TTL_OPTIONS
        )

        if cached is None:
            return []  # Options data may not be available

        # Type assertion: cached is list from get_with_fetch
        if not isinstance(cached, list):
            return []

        return [OptionContract.from_dict(d) for d in cached]

    async def _fetch_options(self, symbol: str) -> list[OptionContract]:
        """Internal: Fetch options chain from Alpha Vantage."""
        try:
            if not hasattr(self._av_service, "get_historical_options"):
                logger.warning("options_endpoint_not_available")
                return []

            data = await self._av_service.get_historical_options(symbol)

            if not data or "data" not in data:
                return []

            result = []
            for item in data.get("data", []):
                try:
                    result.append(
                        OptionContract(
                            contract_id=item.get("contractID", ""),
                            symbol=symbol,
                            expiration=datetime.strptime(
                                item.get("expiration", ""), "%Y-%m-%d"
                            ),
                            strike=float(item.get("strike", 0)),
                            option_type=item.get("type", "").lower(),
                            last_price=float(item.get("last", 0)),
                            bid=float(item.get("bid", 0)),
                            ask=float(item.get("ask", 0)),
                            volume=int(item.get("volume", 0) or 0),
                            open_interest=int(item.get("open_interest", 0) or 0),
                            implied_volatility=float(
                                item.get("implied_volatility", 0) or 0
                            ),
                            delta=(
                                float(item.get("delta", 0))
                                if item.get("delta")
                                else None
                            ),
                        )
                    )
                except Exception as e:
                    logger.debug("options_item_parse_error", error=str(e))
                    continue

            logger.info(
                "options_fetched",
                symbol=symbol,
                contracts=len(result),
            )
            return result

        except Exception as e:
            logger.error("options_fetch_failed", symbol=symbol, error=str(e))
            raise DataFetchError(str(e), "alpha_vantage") from e

    # =========================================================================
    # Put/Call Ratio (Per-Symbol, Cached)
    # =========================================================================

    async def get_symbol_pcr(
        self,
        symbol: str,
        atm_zone_pct: float = 0.15,
        min_premium: float = 0.50,
        min_oi: int = 500,
    ) -> SymbolPCRData | None:
        """
        Get Put/Call Ratio data for a symbol with caching.

        Uses ATM Dollar-Weighted methodology:
        - Filters options to ATM zone (±15% of current price)
        - Requires minimum premium ($0.50) and open interest (500)
        - Calculates notional as OI × Price × 100
        - PCR = Σ(Put Notionals) / Σ(Call Notionals)

        This method is shared between:
        1. AI agent tools (get_put_call_ratio tool)
        2. AI Sector Risk metric (aggregates multiple symbols)

        Args:
            symbol: Stock symbol (e.g., "NVDA")
            atm_zone_pct: ATM zone range (default ±15%)
            min_premium: Minimum option premium (default $0.50)
            min_oi: Minimum open interest (default 500)

        Returns:
            SymbolPCRData with full details, or None if insufficient data
        """
        symbol = symbol.upper()
        cache_key = CacheKeys.pcr_symbol(symbol)

        async def fetch_func() -> dict[str, Any] | None:
            data = await self._calculate_symbol_pcr(
                symbol, atm_zone_pct, min_premium, min_oi
            )
            return data.to_dict() if data else None

        cached = await self._cache.get_with_fetch(cache_key, fetch_func, self.TTL_PCR)

        if cached is None:
            return None

        if not isinstance(cached, dict):
            return None

        return SymbolPCRData.from_dict(cached)

    async def _calculate_symbol_pcr(
        self,
        symbol: str,
        atm_zone_pct: float,
        min_premium: float,
        min_oi: int,
    ) -> SymbolPCRData | None:
        """
        Internal: Calculate PCR for a single symbol.

        Fetches quote and options data, filters to ATM zone,
        and calculates dollar-weighted Put/Call Ratio.
        """
        try:
            # Fetch quote and options concurrently
            quote_task = self.get_quote(symbol)
            options_task = self.get_options(symbol)

            quote, options = await asyncio.gather(
                quote_task, options_task, return_exceptions=True
            )

            # Handle errors
            if isinstance(quote, Exception):
                logger.warning("pcr_quote_failed", symbol=symbol, error=str(quote))
                return None

            if isinstance(options, Exception) or not options:
                logger.warning(
                    "pcr_options_failed",
                    symbol=symbol,
                    error=str(options) if isinstance(options, Exception) else "empty",
                )
                return None

            # Get current price
            current_price = quote.price
            if current_price <= 0:
                logger.warning("pcr_invalid_price", symbol=symbol, price=current_price)
                return None

            # Calculate ATM zone
            atm_zone_low = current_price * (1 - atm_zone_pct)
            atm_zone_high = current_price * (1 + atm_zone_pct)

            # Filter options to ATM zone
            put_notional = 0.0
            call_notional = 0.0
            contracts_analyzed = 0

            for contract in options:
                # Check ATM zone
                if not (atm_zone_low <= contract.strike <= atm_zone_high):
                    continue

                # Check minimum premium
                if contract.last_price < min_premium:
                    continue

                # Check minimum open interest
                if contract.open_interest < min_oi:
                    continue

                # Calculate notional: OI × Price × 100 (options = 100 shares)
                notional = contract.open_interest * contract.last_price * 100

                if contract.option_type == "put":
                    put_notional += notional
                elif contract.option_type == "call":
                    call_notional += notional

                contracts_analyzed += 1

            # Check for sufficient data
            if contracts_analyzed == 0 or call_notional == 0:
                logger.warning(
                    "pcr_insufficient_data",
                    symbol=symbol,
                    contracts=contracts_analyzed,
                    call_notional=call_notional,
                )
                return None

            # Calculate PCR
            pcr = put_notional / call_notional

            # Generate interpretation
            interpretation = self._interpret_pcr(pcr)

            logger.info(
                "pcr_calculated",
                symbol=symbol,
                price=current_price,
                pcr=round(pcr, 2),
                contracts=contracts_analyzed,
            )

            return SymbolPCRData(
                symbol=symbol,
                current_price=current_price,
                atm_zone_low=round(atm_zone_low, 2),
                atm_zone_high=round(atm_zone_high, 2),
                put_notional_mm=round(put_notional / 1_000_000, 2),
                call_notional_mm=round(call_notional / 1_000_000, 2),
                contracts_analyzed=contracts_analyzed,
                pcr=round(pcr, 2),
                interpretation=interpretation,
                calculated_at=datetime.now(UTC),
                atm_zone_pct=atm_zone_pct,
                min_premium=min_premium,
                min_oi=min_oi,
            )

        except Exception as e:
            logger.error("pcr_calculation_failed", symbol=symbol, error=str(e))
            return None

    def _interpret_pcr(self, pcr: float) -> str:
        """Generate human-readable PCR interpretation."""
        if pcr < 0.5:
            return "Very low PCR - Extreme bullish sentiment (contrarian bearish)"
        elif pcr < 0.7:
            return "Low PCR - Bullish sentiment (contrarian cautious)"
        elif pcr < 1.0:
            return "Moderate PCR - Slightly bullish sentiment"
        elif pcr < 1.3:
            return "Moderate PCR - Slightly bearish sentiment"
        elif pcr < 1.5:
            return "High PCR - Bearish sentiment (contrarian optimistic)"
        else:
            return "Very high PCR - Extreme fear (contrarian bullish)"

    # =========================================================================
    # Insights (Computed Data)
    # =========================================================================

    async def get_insights(
        self, category_id: str, suffix: str = "latest"
    ) -> dict | None:
        """
        Get computed insight data from cache.

        Args:
            category_id: Insight category (e.g., "ai_sector_risk")
            suffix: Key suffix ("latest", "trend", etc.)

        Returns:
            Cached insight data or None
        """
        cache_key = CacheKeys.insights(category_id, suffix)
        return await self._cache.get(cache_key)

    async def set_insights(
        self,
        category_id: str,
        data: dict,
        suffix: str = "latest",
        ttl: int | None = None,
    ) -> bool:
        """
        Store computed insight data in cache.

        Args:
            category_id: Insight category
            data: Insight data to cache
            suffix: Key suffix
            ttl: TTL in seconds (default: 24 hours)

        Returns:
            True if successful
        """
        cache_key = CacheKeys.insights(category_id, suffix)
        return await self._cache.set(cache_key, data, ttl or self.TTL_INSIGHTS)

    # =========================================================================
    # Pre-fetch Pattern (Shared Data)
    # =========================================================================

    async def prefetch_shared(
        self,
        symbols: list[str] | None = None,
        treasury_maturities: list[str] | None = None,
        include_news: bool = False,
        include_ipo: bool = False,
    ) -> SharedDataContext:
        """
        Pre-fetch shared data in parallel.

        Use this to fetch data that will be used by multiple
        metric calculations, ensuring each data source is
        fetched only once.

        Example:
            context = await dm.prefetch_shared(
                symbols=["NVDA", "MSFT", "AMD"],
                treasury_maturities=["2y", "10y"],
            )
            # Now use context.get_treasury("2y") in multiple metrics
            # without duplicate API calls

        Args:
            symbols: Stock symbols to fetch OHLCV for
            treasury_maturities: Treasury maturities to fetch
            include_news: Whether to fetch news sentiment
            include_ipo: Whether to fetch IPO calendar

        Returns:
            SharedDataContext with all fetched data
        """
        context = SharedDataContext()
        tasks = []
        task_keys = []

        # Queue OHLCV tasks
        for symbol in symbols or []:
            tasks.append(self.get_ohlcv(symbol, "daily"))
            task_keys.append(("ohlcv", symbol.upper()))

        # Queue treasury tasks
        for maturity in treasury_maturities or []:
            tasks.append(self.get_treasury(maturity))
            task_keys.append(("treasury", maturity.lower()))

        # Queue news task
        if include_news:
            tasks.append(self.get_news_sentiment(topic="technology"))
            task_keys.append(("news", "technology"))

        # Queue IPO task
        if include_ipo:
            tasks.append(self.get_ipo_calendar())
            task_keys.append(("ipo", "calendar"))

        # Execute all in parallel
        if tasks:
            logger.info(
                "prefetch_started",
                symbols=symbols,
                treasury=treasury_maturities,
                total_tasks=len(tasks),
            )

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for (data_type, key), result in zip(task_keys, results, strict=False):
                if isinstance(result, Exception):
                    context.errors[f"{data_type}:{key}"] = str(result)
                    logger.warning(
                        "prefetch_task_failed",
                        data_type=data_type,
                        key=key,
                        error=str(result),
                    )
                elif data_type == "ohlcv":
                    context.ohlcv[key] = result
                elif data_type == "treasury":
                    context.treasury[key] = result
                elif data_type == "news":
                    context.news[key] = result
                elif data_type == "ipo":
                    context.ipo = result

            logger.info(
                "prefetch_completed",
                ohlcv_count=len(context.ohlcv),
                treasury_count=len(context.treasury),
                errors=len(context.errors),
            )

        return context

    # =========================================================================
    # Cache Management
    # =========================================================================

    async def invalidate_market(
        self, symbol: str | None = None, granularity: str | None = None
    ) -> int:
        """
        Invalidate market data cache.

        Args:
            symbol: Symbol to invalidate, or all if None
            granularity: Granularity to invalidate, or all if None

        Returns:
            Number of keys invalidated
        """
        if symbol and granularity:
            key = CacheKeys.market(granularity, symbol)
            deleted = await self._cache.delete(key)
            return 1 if deleted else 0
        elif symbol:
            pattern = f"{CacheKeys.MARKET}:*:{symbol.upper()}"
        elif granularity:
            pattern = CacheKeys.pattern(CacheKeys.MARKET, granularity)
        else:
            pattern = CacheKeys.pattern(CacheKeys.MARKET)

        return await self._cache.invalidate_pattern(pattern)

    async def invalidate_insights(self, category_id: str | None = None) -> int:
        """
        Invalidate insights cache.

        Args:
            category_id: Category to invalidate, or all if None

        Returns:
            Number of keys invalidated
        """
        if category_id:
            pattern = f"{CacheKeys.INSIGHTS}:{category_id.lower()}:*"
        else:
            pattern = CacheKeys.pattern(CacheKeys.INSIGHTS)

        return await self._cache.invalidate_pattern(pattern)
