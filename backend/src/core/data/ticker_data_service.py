"""Cached current-price access for portfolio holdings."""

import structlog

from ...database.redis import RedisCache
from ...services.alphavantage_market_data import AlphaVantageMarketDataService

logger = structlog.get_logger()


class TickerDataService:
    """Fetch current prices through the local market-data fallback service."""

    def __init__(
        self,
        redis_cache: RedisCache,
        alpha_vantage_service: AlphaVantageMarketDataService,
    ) -> None:
        self.redis_cache = redis_cache
        self.market_service = alpha_vantage_service

    async def get_current_price(self, symbol: str) -> float | None:
        cache_key = f"current_price:{symbol.upper()}"
        cached_price = await self.redis_cache.get(cache_key)
        if cached_price is not None:
            return float(cached_price)

        try:
            quote = await self.market_service.get_quote(symbol.upper())
            price = float(quote.get("price") or 0)
            if price <= 0:
                return None
            await self.redis_cache.set(cache_key, price, ttl_seconds=30)
            return price
        except Exception as exc:
            logger.warning(
                "Current price fetch failed",
                symbol=symbol,
                error=str(exc),
            )
            return None
