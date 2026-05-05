"""
Portfolio orders endpoint.

W5a: Alpaca live trading removed. Orders are now sourced from the local
``portfolio_orders`` MongoDB collection (status="suggested" by default).
"""

from datetime import datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.core.utils.date_utils import utcnow

from ...database.mongodb import MongoDB
from ...database.repositories.holding_repository import HoldingRepository
from ...database.repositories.portfolio_order_repository import PortfolioOrderRepository
from ...database.repositories.user_transaction_repository import (
    UserTransactionRepository,
)
from ...services.order_execution_service import (
    OrderAlreadyFilledError,
    OrderNotExecutableError,
    OrderNotFoundError,
    mark_order_executed,
)
from ..dependencies.auth import get_mongodb
from ..dependencies.portfolio_deps import (
    get_holding_repository,
    get_portfolio_order_repository,
)
from ..dependencies.rate_limit import limiter
from .user_transactions import get_user_tx_repo

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


class MarkExecutedRequest(BaseModel):
    """Payload for POST /api/portfolio/orders/{order_id}/mark-executed."""

    filled_qty: float = Field(gt=0, description="Shares actually filled")
    filled_avg_price: float = Field(gt=0, description="Per-share fill price (USD)")
    executed_at: datetime | None = Field(
        default=None, description="When the trade filled. Defaults to now (UTC)."
    )
    notes: str | None = Field(default=None, max_length=500)


class MarkExecutedResponse(BaseModel):
    order_id: str
    transaction_id: str
    symbol: str
    side: Literal["buy", "sell"]
    filled_qty: float
    filled_avg_price: float
    filled_at: str
    cash_delta: float
    new_cash_balance: float
    cash_warning: str | None = None


@router.post(
    "/orders/{order_id}/mark-executed",
    response_model=MarkExecutedResponse,
)
@limiter.limit("30/minute")
async def mark_order_executed_endpoint(
    request: Request,
    order_id: str,
    payload: MarkExecutedRequest,
    mongodb: MongoDB = Depends(get_mongodb),
    order_repo: PortfolioOrderRepository = Depends(get_portfolio_order_repository),
    tx_repo: UserTransactionRepository = Depends(get_user_tx_repo),
    holding_repo: HoldingRepository = Depends(get_holding_repository),
) -> MarkExecutedResponse:
    """
    Mark an LLM-suggested order as executed by the user.

    Atomically:
    - creates a UserTransaction (back-pointing to the order)
    - applies the trade to portfolio_holdings (BUY +qty / SELL -qty)
    - adjusts user_settings.cash_balance (BUY -total / SELL +total).
      Cash may go negative — UI displays a warning, see PRD.
    - flips the order to status="filled" with fill columns set
    """
    try:
        result = await mark_order_executed(
            mongodb=mongodb,
            order_repo=order_repo,
            tx_repo=tx_repo,
            holding_repo=holding_repo,
            order_id=order_id,
            filled_qty=payload.filled_qty,
            filled_avg_price=payload.filled_avg_price,
            executed_at=payload.executed_at or utcnow(),
            notes=payload.notes,
        )
    except OrderNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except OrderAlreadyFilledError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except OrderNotExecutableError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        # Holdings ledger errors (oversell / no-holding) bubble up here
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("mark_executed_failed", order_id=order_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to mark order executed: {e}",
        ) from e

    return MarkExecutedResponse(**result)
