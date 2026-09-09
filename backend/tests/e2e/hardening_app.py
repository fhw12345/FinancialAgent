"""Hardening browser app: real routes/storage/calculators, recorded market providers."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

from fastapi.responses import JSONResponse

from src.services.data_manager import CacheKeys, DataManager
from src.services.insights.categories.ai_sector_risk import AI_BASKET_CACHE_KEY
from src.services.insights.registry import InsightsCategoryRegistry
from src.services.insights.snapshot_service import InsightsSnapshotService
from src.services.market_data import yfinance_bars
from tests.e2e.agent_events_app import app
from tests.e2e.insights_provider_fixture import (
    SYMBOLS,
    RecordedFred,
    RecordedMarket,
    seed_pcr,
)

market = RecordedMarket()
prefetch_requests = []
prefetch_gate = None
_original_lifespan = app.router.lifespan_context
_original_prefetch = DataManager.prefetch_shared


async def record_prefetch(self, **kwargs):
    prefetch_requests.append(kwargs)
    if prefetch_gate is not None:
        await prefetch_gate.wait()
    return await _original_prefetch(self, **kwargs)


@asynccontextmanager
async def lifespan(application):
    async with _original_lifespan(application):
        cache = application.state.redis
        settings = application.state.settings
        registry = InsightsCategoryRegistry(settings, cache, market, RecordedFred())
        manager = DataManager(cache, market)
        application.state.insights_registry = registry
        application.state.data_manager = manager
        application.state.snapshot_service = InsightsSnapshotService(
            application.state.mongodb,
            cache,
            manager,
            settings,
            registry,
        )
        await seed_pcr(cache)
        with (
            patch.object(yfinance_bars, "get_bars", market.bars),
            patch.object(DataManager, "prefetch_shared", record_prefetch),
        ):
            yield


app.router.lifespan_context = lifespan


@app.middleware("http")
async def no_background_market_movers(request, call_next):
    # Unrelated widget traffic must not turn CI into a live-provider test.
    if request.url.path == "/api/market/market-movers":
        return JSONResponse(
            {"top_gainers": [], "top_losers": [], "most_actively_traded": []}
        )
    return await call_next(request)


@app.post("/api/test/insights/reset")
async def reset_insights():
    global prefetch_gate
    prefetch_gate = asyncio.Event()
    cache = app.state.redis
    for key in [
        AI_BASKET_CACHE_KEY,
        *(CacheKeys.market("daily", symbol, outputsize="full") for symbol in SYMBOLS),
        CacheKeys.treasury("2y"),
        CacheKeys.treasury("10y"),
        CacheKeys.news_sentiment("technology"),
        CacheKeys.ipo_calendar(),
    ]:
        await cache.delete(key)
    await seed_pcr(cache)
    market.calls.clear()
    market.outputs.clear()
    prefetch_requests.clear()
    return {"reset": True}


@app.post("/api/test/insights/release")
async def release_prefetch():
    if prefetch_gate is not None:
        prefetch_gate.set()
    return {"released": True}


@app.get("/api/test/insights/evidence")
async def insights_evidence():
    doc = await app.state.mongodb.get_collection("insight_snapshots").find_one(
        {"category_id": "ai_sector_risk"},
        sort=[("date", -1)],
    )
    return {
        "calls": dict(market.calls),
        "outputs": market.outputs,
        "prefetch_requests": prefetch_requests,
        "snapshot": (
            {
                key: doc[key]
                for key in (
                    "category_id",
                    "composite_score",
                    "metrics",
                    "prefetch_errors",
                )
            }
            if doc
            else None
        ),
    }
