"""
Cache warming service for Redis cache optimization.

Pre-populates the cache with frequently accessed data to improve
cache hit ratios and reduce latency for common queries.

Supports:
- Startup warming for market movers (top gainers/losers)
- User watchlist warming (per-user symbol data)
- Background refresh for stale entries
"""

import typing
from datetime import UTC, datetime
from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorCollection

from ..core.config import Settings
from ..database.redis import RedisCache
from ..services.alphavantage_market_data import AlphaVantageMarketDataService

logger = structlog.get_logger()


class CacheWarmingService:
    """Service for warming Redis cache with frequently accessed data."""

    # Default symbols to warm on startup (major indices and popular stocks)
    DEFAULT_SYMBOLS = [
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "NVDA",
        "META",
        "TSLA",
        "SPY",
        "QQQ",
        "BRK-B",
    ]

    def __init__(
        self,
        redis_cache: RedisCache,
        market_service: AlphaVantageMarketDataService,
        watchlist_collection: (
            AsyncIOMotorCollection[dict[str, typing.Any]] | None
        ) = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize cache warming service.

        Args:
            redis_cache: Redis cache instance for storing warmed data
            market_service: Alpha Vantage service for fetching market data
            watchlist_collection: MongoDB collection for user watchlists (optional)
            settings: Application settings for TTL configuration
        """
        self.redis_cache = redis_cache
        self.market_service = market_service
        self.watchlist_collection = watchlist_collection
        self.settings = settings
        self._warming_in_progress = False

    async def warm_startup_cache(
        self, symbols: list[str] | None = None
    ) -> dict[str, typing.Any]:
        """Warm cache on application startup.

        Pre-populates cache with data for common symbols to reduce
        cold start latency. Runs in background to not block startup.

        Args:
            symbols: List of symbols to warm (defaults to DEFAULT_SYMBOLS)

        Returns:
            dict with warming results (success count, errors)
        """
        if self._warming_in_progress:
            logger.warning("Cache warming already in progress, skipping")
            return {"status": "skipped", "reason": "already_in_progress"}

        self._warming_in_progress = True
        symbols = symbols or self.DEFAULT_SYMBOLS
        results: dict[str, Any] = {
            "total": len(symbols),
            "success": 0,
            "errors": [],
            "skipped": 0,
        }

        logger.info(
            "Starting startup cache warming",
            symbol_count=len(symbols),
            symbols=symbols,
        )

        try:
            for symbol in symbols:
                try:
                    await self._warm_symbol(symbol)
                    results["success"] += 1
                except Exception as e:
                    logger.warning(
                        "Failed to warm cache for symbol",
                        symbol=symbol,
                        error=str(e),
                    )
                    results["errors"].append({"symbol": symbol, "error": str(e)})

            logger.info(
                "Startup cache warming completed",
                success=results["success"],
                errors=len(results["errors"]),
            )

        finally:
            self._warming_in_progress = False

        return results

    async def warm_user_watchlist(self, user_id: str) -> dict[str, typing.Any]:
        """Warm cache for a specific user's watchlist.

        Pre-populates cache with data for all symbols in a user's watchlist.

        Args:
            user_id: User ID to warm watchlist for

        Returns:
            dict with warming results
        """
        if not self.watchlist_collection:
            return {"status": "error", "reason": "watchlist_collection_not_configured"}

        results: dict[str, Any] = {
            "user_id": user_id,
            "success": 0,
            "errors": [],
            "symbols": [],
        }

        try:
            # Get user's watchlist symbols
            watchlist_docs = await self.watchlist_collection.find(
                {"user_id": user_id}
            ).to_list(length=100)

            symbols = [
                symbol
                for doc in watchlist_docs
                if isinstance((symbol := doc.get("symbol")), str)
            ]
            results["symbols"] = symbols

            if not symbols:
                logger.info("No watchlist symbols found for user", user_id=user_id)
                return results

            logger.info(
                "Warming cache for user watchlist",
                user_id=user_id,
                symbol_count=len(symbols),
            )

            for symbol in symbols:
                try:
                    await self._warm_symbol(symbol)
                    results["success"] += 1
                except Exception as e:
                    results["errors"].append({"symbol": symbol, "error": str(e)})

            logger.info(
                "User watchlist cache warming completed",
                user_id=user_id,
                success=results["success"],
                errors=len(results["errors"]),
            )

        except Exception as e:
            logger.error(
                "Failed to warm user watchlist cache",
                user_id=user_id,
                error=str(e),
            )
            results["errors"].append({"error": str(e)})

        return results

    async def warm_market_movers(self) -> dict[str, typing.Any]:
        """Warm cache with current market movers data.

        Fetches and caches top gainers, losers, and most active stocks.

        Returns:
            dict with warming results
        """
        results: dict[str, Any] = {
            "success": 0,
            "errors": [],
            "symbols_warmed": [],
        }

        try:
            logger.info("Fetching market movers for cache warming")

            # Get market movers data
            movers_data = await self.market_service.get_top_gainers_losers()

            if not movers_data:
                return {
                    "status": "error",
                    "reason": "failed_to_fetch_market_movers",
                }

            # Cache the market movers response directly
            current_date = datetime.now(UTC).strftime("%Y-%m-%d")
            cache_key = f"market_movers:{current_date}"

            ttl = (
                self.settings.cache_ttl_news if self.settings else 3600
            )  # 1 hour default
            await self.redis_cache.set(cache_key, movers_data, ttl_seconds=ttl)

            logger.info(
                "Market movers cached",
                cache_key=cache_key,
                ttl_seconds=ttl,
            )

            # Extract symbols from movers for individual warming
            symbols_to_warm = []
            for category in ["top_gainers", "top_losers", "most_actively_traded"]:
                items = movers_data.get(category, [])
                for item in items[:5]:  # Top 5 from each category
                    if ticker := item.get("ticker"):
                        symbols_to_warm.append(ticker)

            # Warm individual symbol data
            for symbol in symbols_to_warm[:15]:  # Limit to 15 symbols
                try:
                    await self._warm_symbol(symbol)
                    results["symbols_warmed"].append(symbol)
                    results["success"] += 1
                except Exception as e:
                    results["errors"].append({"symbol": symbol, "error": str(e)})

            logger.info(
                "Market movers cache warming completed",
                symbols_warmed=len(results["symbols_warmed"]),
                errors=len(results["errors"]),
            )

        except Exception as e:
            logger.error("Failed to warm market movers cache", error=str(e))
            results["errors"].append({"error": str(e)})

        return results

    async def _warm_symbol(self, symbol: str) -> None:
        """Warm cache for a single symbol.

        Fetches and caches quote and company overview data.

        Args:
            symbol: Stock symbol to warm
        """
        current_date = datetime.now(UTC).strftime("%Y-%m-%d")

        # Warm quote data
        try:
            quote = await self.market_service.get_quote(symbol)
            if quote:
                cache_key = f"quote:{symbol}:{current_date}"
                ttl = self.settings.cache_ttl_realtime if self.settings else 60
                await self.redis_cache.set(cache_key, quote, ttl_seconds=ttl)
                logger.debug("Warmed quote cache", symbol=symbol, cache_key=cache_key)
        except Exception as e:
            logger.debug("Failed to warm quote for symbol", symbol=symbol, error=str(e))

        # Warm company overview (longer TTL - fundamentals)
        try:
            overview = await self.market_service.get_company_overview(symbol)
            if overview:
                cache_key = f"company_overview:{symbol}:{current_date}"
                ttl = self.settings.cache_ttl_fundamentals if self.settings else 86400
                await self.redis_cache.set(cache_key, overview, ttl_seconds=ttl)
                logger.debug(
                    "Warmed company overview cache",
                    symbol=symbol,
                    cache_key=cache_key,
                )
        except Exception as e:
            logger.debug(
                "Failed to warm overview for symbol",
                symbol=symbol,
                error=str(e),
            )

    async def get_warming_status(self) -> dict[str, typing.Any]:
        """Get current cache warming status.

        Returns:
            dict with warming status and statistics
        """
        return {
            "warming_in_progress": self._warming_in_progress,
            "default_symbols": self.DEFAULT_SYMBOLS,
            "timestamp": datetime.now(UTC).isoformat(),
        }
