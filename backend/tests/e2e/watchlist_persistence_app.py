"""FastAPI app with deterministic portfolio execution for UAW-004 E2E."""

from __future__ import annotations

from datetime import UTC
from typing import Any

from src.agent.portfolio import flows as portfolio_flows
from src.api import watchlist as watchlist_api
from src.main import app as main_app
from src.models.watchlist import WatchlistItem
from src.services.cache_warming_service import CacheWarmingService

app = main_app


async def deterministic_single_symbol(
    app_instance: Any,
    symbol: str,
) -> dict[str, Any]:
    """Replace only expensive model execution; keep persistence real."""
    return {
        "result_count": 1,
        "run_id": f"uaw004_{symbol.lower()}",
        "symbol": symbol,
        "message": "Deterministic UAW-004 analysis completed.",
    }


async def skip_live_quote_enrichment(
    request: Any,
    items: list[WatchlistItem],
) -> list[WatchlistItem]:
    """Keep the E2E focused on watchlist persistence, not quote vendors."""
    for item in items:
        if item.added_at.tzinfo is None:
            item.added_at = item.added_at.replace(tzinfo=UTC)
        if item.last_analyzed_at is not None and item.last_analyzed_at.tzinfo is None:
            item.last_analyzed_at = item.last_analyzed_at.replace(tzinfo=UTC)
    return items


async def skip_startup_cache_warming(
    self: CacheWarmingService,
    symbols: list[str] | None = None,
) -> dict[str, object]:
    """Prevent external market calls from affecting the persistence E2E."""
    return {"status": "skipped", "reason": "uaw004_e2e"}


portfolio_flows.run_single_symbol = deterministic_single_symbol
watchlist_api._enrich_with_live_quote = skip_live_quote_enrichment
CacheWarmingService.warm_startup_cache = skip_startup_cache_warming
