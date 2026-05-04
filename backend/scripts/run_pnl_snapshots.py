"""
Hourly cron: compute ex-post P&L snapshots for AI decisions.

Walks portfolio_orders rows that have a decision_price + an unfilled
horizon slot (7d/30d/90d), fetches the mark-to-market close via
DataManager.get_price_on_date, writes pnl_snapshots back.

Idempotent: existing snapshots are skipped by the repo query.
Run from inside the backend container:

    python scripts/run_pnl_snapshots.py
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
    log = structlog.get_logger("pnl_snapshots")

    sys.path.insert(0, "/app")
    from src.core.config import get_settings
    from src.database.mongodb import MongoDB
    from src.database.redis import RedisCache
    from src.database.repositories.portfolio_order_repository import (
        PortfolioOrderRepository,
    )
    from src.services.alphavantage_market_data import AlphaVantageMarketDataService
    from src.services.data_manager.manager import DataManager
    from src.services.finnhub import FinnhubService
    from src.services.pnl_service import run_pnl_snapshot_job

    settings = get_settings()
    mongo = MongoDB()
    redis = RedisCache()
    await mongo.connect(settings.mongodb_url)
    await redis.connect(settings.redis_url)

    try:
        repo = PortfolioOrderRepository(mongo.get_collection("portfolio_orders"))
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

        log.info("pnl_snapshot_job_start")
        counters = await run_pnl_snapshot_job(data_manager=dm, repo=repo)
        log.info("pnl_snapshot_job_done", **counters)
        return 0
    except Exception as e:
        log.error("pnl_snapshot_job_failed", error=str(e))
        return 1
    finally:
        await mongo.disconnect()
        await redis.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
