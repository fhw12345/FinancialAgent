"""
P&L snapshot service for the decision-tracking dashboard.

Pure stateless functions:
- compute_pnl_pct: directional return given a side, decision price, mark price
- snapshot_decision: fetch mark price for one (decision, horizon), write to repo

Direction handling:
- BUY  → pnl_pct = (mark - decision) / decision * 100   (long thesis was right if positive)
- SELL → pnl_pct = (decision - mark) / decision * 100   (short/exit thesis was right if positive)
- HOLD/SIGNAL → same as BUY (positive means "by holding/signaling, you'd have gained")

Horizon checkpoints in days. Run hourly from the portfolio-cron container.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import structlog

from ..core.utils.date_utils import utcnow
from ..database.repositories.portfolio_order_repository import PortfolioOrderRepository
from ..models.portfolio import PortfolioOrder
from ..services.data_manager.manager import DataManager

logger = structlog.get_logger(__name__)

DEFAULT_HORIZONS_DAYS: tuple[int, ...] = (7, 30, 90)


def compute_pnl_pct(side: str, decision_price: float, mark_price: float) -> float:
    """Directional P&L percentage. Positive means the AI was right."""
    if decision_price <= 0:
        return 0.0
    raw = (mark_price - decision_price) / decision_price * 100.0
    return raw if side.lower() != "sell" else -raw


async def snapshot_decision(
    order: PortfolioOrder,
    horizon_days: int,
    data_manager: DataManager,
    repo: PortfolioOrderRepository,
) -> dict[str, Any] | None:
    """
    Resolve mark price at order.created_at + horizon_days, compute P&L,
    write snapshot to mongo. Returns the snapshot dict, or None if skipped.
    """
    if not order.decision_price or order.decision_price <= 0:
        return None

    # Mongo returns naive datetimes by default; coerce to UTC-aware so the
    # comparison with utcnow() (aware) doesn't raise TypeError.
    from datetime import UTC as _UTC

    created = order.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=_UTC)
    target_dt = created + timedelta(days=horizon_days)
    if target_dt > utcnow():
        return None  # Horizon hasn't elapsed yet — try again later

    mark_price = await data_manager.get_price_on_date(order.symbol, target_dt)
    if mark_price is None:
        logger.debug(
            "pnl_snapshot_skipped_no_price",
            symbol=order.symbol,
            horizon=horizon_days,
            order_id=order.order_id,
        )
        return None

    pnl_pct = compute_pnl_pct(order.side, order.decision_price, mark_price)
    snap = {
        "price": round(mark_price, 4),
        "pnl_pct": round(pnl_pct, 4),
        "computed_at": utcnow().isoformat(),
    }
    await repo.update_pnl_snapshot(order.order_id, horizon_days, snap)
    logger.info(
        "pnl_snapshot_written",
        symbol=order.symbol,
        horizon=horizon_days,
        pnl_pct=snap["pnl_pct"],
        order_id=order.order_id,
    )
    return snap


async def run_pnl_snapshot_job(
    data_manager: DataManager,
    repo: PortfolioOrderRepository,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS_DAYS,
    limit_per_horizon: int = 200,
) -> dict[str, int]:
    """
    Per-horizon scan: find orders whose horizon has elapsed but the snapshot
    is missing, compute and write. Idempotent — existing snapshots are not
    re-fetched (the repo query filters them out).
    """
    counters: dict[str, int] = {}
    now = utcnow()
    for h in horizons:
        cutoff = now - timedelta(days=h)
        pending = await repo.list_pending_pnl_snapshots(
            horizon_days=h, cutoff_dt=cutoff, limit=limit_per_horizon
        )
        written = 0
        for order in pending:
            try:
                if await snapshot_decision(order, h, data_manager, repo):
                    written += 1
            except Exception as e:
                logger.warning(
                    "pnl_snapshot_one_failed",
                    order_id=order.order_id,
                    horizon=h,
                    error=str(e),
                )
        counters[f"{h}d"] = written
        logger.info(
            "pnl_snapshot_horizon_done",
            horizon=h,
            pending=len(pending),
            written=written,
        )
    return counters


__all__ = [
    "DEFAULT_HORIZONS_DAYS",
    "compute_pnl_pct",
    "run_pnl_snapshot_job",
    "snapshot_decision",
]
