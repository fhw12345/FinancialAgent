"""
Risk-adaptive coarse filter for the Today's Picks universe.

Reduces a sector-filtered candidate list (could be 100s) to ≤50 finalists
based on user's risk tolerance:

- conservative: top 50 by market cap (blue chips)
- aggressive  : top 50 by 30-day momentum (recent winners)
- moderate    : union of top 25 by cap + top 25 by momentum (balanced)

The 50-symbol cap bounds Phase 1 LLM cost.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from ...models.portfolio_analysis import SectorUniverseRow

logger = structlog.get_logger(__name__)

MAX_FINALISTS = 50
HALF = MAX_FINALISTS // 2


async def _momentum_30d(symbol: str, data_manager: Any) -> float:
    """Return 30d return as a float, or -inf if data unavailable (sorts to bottom)."""
    try:
        bars = await data_manager.get_ohlcv(symbol, "daily", outputsize="compact")
        if not bars or len(bars) < 20:
            return float("-inf")
        # bars are newest-first
        recent = bars[0].close
        old = bars[min(len(bars) - 1, 21)].close  # ~30 calendar days back
        if old <= 0:
            return float("-inf")
        return (recent - old) / old
    except Exception as e:
        logger.debug("momentum_failed", symbol=symbol, error=str(e))
        return float("-inf")


async def _rank_by_momentum(
    rows: list[SectorUniverseRow], data_manager: Any, limit: int
) -> list[SectorUniverseRow]:
    """Compute 30d return for each row in parallel, return top N."""
    sem = asyncio.Semaphore(10)  # cap concurrent OHLCV fetches

    async def _one(row: SectorUniverseRow) -> tuple[SectorUniverseRow, float]:
        async with sem:
            return row, await _momentum_30d(row.symbol, data_manager)

    pairs = await asyncio.gather(*(_one(r) for r in rows))
    pairs.sort(key=lambda p: p[1], reverse=True)
    return [p[0] for p in pairs[:limit]]


async def filter_by_risk(
    rows: list[SectorUniverseRow],
    risk_tolerance: str,
    data_manager: Any,
) -> list[SectorUniverseRow]:
    """
    Reduce `rows` to ≤MAX_FINALISTS based on `risk_tolerance`.

    Args:
        rows: sector-filtered universe rows
        risk_tolerance: 'conservative' | 'moderate' | 'aggressive'
        data_manager: DataManager instance for momentum lookup
    """
    if not rows:
        return []
    if len(rows) <= MAX_FINALISTS:
        return rows

    risk = (risk_tolerance or "moderate").lower()
    if risk == "conservative":
        # Sort by market cap descending
        return sorted(rows, key=lambda r: r.market_cap_b, reverse=True)[:MAX_FINALISTS]
    if risk == "aggressive":
        return await _rank_by_momentum(rows, data_manager, MAX_FINALISTS)

    # moderate: top HALF by cap ∪ top HALF by momentum, dedupe
    by_cap = sorted(rows, key=lambda r: r.market_cap_b, reverse=True)[:HALF]
    by_mom = await _rank_by_momentum(rows, data_manager, HALF)
    seen: set[str] = set()
    out: list[SectorUniverseRow] = []
    for r in [*by_cap, *by_mom]:
        if r.symbol not in seen:
            seen.add(r.symbol)
            out.append(r)
    return out[:MAX_FINALISTS]
