"""
Hourly cron: refresh current_price + market_value + unrealized_pl for every
holding so the dashboard shows live values without waiting for a manual edit.

Walks portfolio_holdings, calls DataManager.get_quote per symbol (Finnhub →
AV → yfinance fallback chain), writes back via repo.update_price.

Idempotent and safe to re-run; failures per-symbol are logged but don't abort
the rest of the batch.

Run from inside the backend container:
    python scripts/refresh_holding_prices.py
"""

from __future__ import annotations

import asyncio
import logging
import sys

import structlog


async def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ]
    )
    logging.basicConfig(level=logging.INFO)
    log = structlog.get_logger("refresh_prices")

    sys.path.insert(0, "/app")
    from src.core.config import get_settings
    from src.database.mongodb import MongoDB
    from src.database.redis import RedisCache
    from src.database.repositories.holding_repository import HoldingRepository
    from src.services.alphavantage_market_data import AlphaVantageMarketDataService
    from src.services.data_manager.manager import DataManager
    from src.services.finnhub import FinnhubService

    settings = get_settings()
    mongo = MongoDB()
    redis = RedisCache()
    await mongo.connect(settings.mongodb_url)
    await redis.connect(settings.redis_url)

    refreshed = 0
    failed = 0
    try:
        repo = HoldingRepository(mongo.get_collection("holdings"))
        av = AlphaVantageMarketDataService(settings)
        finnhub = (
            FinnhubService(api_key=settings.finnhub_api_key)
            if settings.finnhub_api_key
            else None
        )
        dm = DataManager(
            redis_cache=redis,
            alpha_vantage_service=av,
            finnhub_service=finnhub,
        )

        holdings = await repo.list_by_user()
        log.info("refresh_start", count=len(holdings))

        for h in holdings:
            try:
                quote = await dm.get_quote(h.symbol)
                price = float(getattr(quote, "price", 0) or 0)
                if price <= 0:
                    log.warning("refresh_skip_no_price", symbol=h.symbol)
                    failed += 1
                    continue
                await repo.update_price(h.holding_id, price)
                log.info(
                    "refresh_ok",
                    symbol=h.symbol,
                    price=round(price, 2),
                )
                refreshed += 1
            except Exception as e:
                log.warning("refresh_failed", symbol=h.symbol, error=str(e))
                failed += 1

        log.info("refresh_done", refreshed=refreshed, failed=failed)
        return 0
    except Exception as e:
        log.error("refresh_job_failed", error=str(e))
        return 1
    finally:
        await mongo.disconnect()
        await redis.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
