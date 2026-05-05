"""
Decisions endpoint — surfaces AI decisions (orders + HOLD signals) enriched
with ex-post P&L snapshots written by the pnl_snapshots cron.

Frontend dashboard hits this to render "Was the AI right?" tables / charts.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ...database.repositories.portfolio_order_repository import PortfolioOrderRepository
from ..dependencies.portfolio_deps import get_portfolio_order_repository
from ..dependencies.rate_limit import limiter

logger = structlog.get_logger()

router = APIRouter()


@router.get("/decisions")
@limiter.limit("60/minute")
async def list_decisions(
    request: Request,
    symbol: str | None = Query(None, description="Filter to a single symbol"),
    decision_type: str | None = Query(
        None, description="'order' (BUY/SELL), 'signal' (HOLD/verdict), or omit for all"
    ),
    source: str | None = Query(
        None,
        description="'holdings' or 'picks' to filter by analysis flow source; omit for all",
    ),
    limit: int = Query(100, ge=1, le=500),
    order_repo: PortfolioOrderRepository = Depends(get_portfolio_order_repository),
) -> dict:
    """List AI decisions newest-first with their P&L snapshots."""
    try:
        decisions = await order_repo.list_decisions(
            symbol=symbol,
            decision_type=decision_type,
            source=source,
            limit=limit,
        )
        return {
            "decisions": [
                {
                    "order_id": d.order_id,
                    "symbol": d.symbol,
                    "side": d.side,
                    "decision_type": d.decision_type,
                    "decision_price": d.decision_price,
                    "quantity": d.quantity,
                    "status": d.status,
                    "filled_qty": d.filled_qty,
                    "filled_avg_price": d.filled_avg_price,
                    "filled_at": d.filled_at.isoformat() if d.filled_at else None,
                    "user_transaction_id": d.user_transaction_id,
                    "created_at": d.created_at.isoformat(),
                    "analysis_id": d.analysis_id,
                    "chat_id": d.chat_id,
                    "recommendation_source": d.recommendation_source,
                    "pnl_snapshots": d.pnl_snapshots or {},
                    "metadata": d.metadata or {},
                }
                for d in decisions
            ],
            "count": len(decisions),
        }
    except Exception as e:
        logger.error("decisions_list_failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to list decisions: {e}"
        ) from e
