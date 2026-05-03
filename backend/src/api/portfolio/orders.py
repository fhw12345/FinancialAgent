"""
Portfolio orders endpoint.

W5a: Alpaca live trading removed. Orders are now sourced from the local
``portfolio_orders`` MongoDB collection (status="suggested" by default).
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from ...database.repositories.portfolio_order_repository import PortfolioOrderRepository
from ..dependencies.portfolio_deps import get_portfolio_order_repository
from ..dependencies.rate_limit import limiter

logger = structlog.get_logger()

router = APIRouter()


@router.get("/orders")
@limiter.limit("30/minute")
async def get_portfolio_orders(
    request: Request,
    limit: int = 50,
    status: str | None = None,
    order_repo: PortfolioOrderRepository = Depends(get_portfolio_order_repository),
) -> dict:
    """List portfolio orders from MongoDB (suggested orders, manual execution required)."""
    try:
        orders = await order_repo.list_by_user(
            status=status if status not in (None, "all") else None,
            limit=limit,
        )

        return {
            "orders": [
                {
                    "order_id": o.order_id,
                    "symbol": o.symbol,
                    "side": o.side,
                    "quantity": float(o.quantity),
                    "order_type": o.order_type,
                    "status": o.status,
                    "filled_qty": float(o.filled_qty or 0),
                    "filled_avg_price": o.filled_avg_price,
                    "submitted_at": o.created_at.isoformat() if o.created_at else None,
                    "filled_at": o.filled_at.isoformat() if o.filled_at else None,
                    "analysis_id": o.analysis_id,
                }
                for o in orders
            ],
            "total": len(orders),
            "note": "Suggested orders only. Manual execution required.",
        }
    except Exception as e:
        logger.error("Failed to list portfolio orders", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve order history.",
        ) from e
