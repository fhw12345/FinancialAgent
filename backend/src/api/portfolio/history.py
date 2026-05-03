"""
Portfolio history endpoint.

W5a: Alpaca live trading removed. Portfolio value time series is no longer
available (no broker account). This endpoint returns an empty time series with
order markers from the local ``portfolio_orders`` MongoDB collection so the
chart still renders.
"""

from datetime import timedelta

import structlog
from fastapi import APIRouter, Depends, Request

from src.core.utils.date_utils import utcnow

from ...database.mongodb import MongoDB
from ..dependencies.auth import get_mongodb
from ..dependencies.rate_limit import limiter
from ..schemas.portfolio_models import (
    AnalysisMarker,
    OrderMarker,
    PortfolioHistoryResponse,
)

logger = structlog.get_logger()

router = APIRouter()


@router.get("/history", response_model=PortfolioHistoryResponse)
@limiter.limit("30/minute")
async def get_portfolio_history(
    request: Request,
    period: str = "1D",
    symbol: str | None = None,
    mongodb: MongoDB = Depends(get_mongodb),
) -> PortfolioHistoryResponse:
    """Return order markers from MongoDB; broker-sourced equity history is removed."""
    end_time = utcnow()
    start_time = end_time - timedelta(days=30)

    orders_collection = mongodb.get_collection("portfolio_orders")

    order_query: dict = {
        "created_at": {"$gte": start_time, "$lte": end_time},
    }
    if symbol:
        order_query["symbol"] = symbol

    cursor = orders_collection.find(order_query).sort("created_at", -1).limit(100)

    order_markers: list[OrderMarker] = []
    async for order_dict in cursor:
        order_markers.append(
            OrderMarker(
                timestamp=order_dict["created_at"],
                symbol=order_dict["symbol"],
                side=order_dict["side"],
                quantity=order_dict["quantity"],
                status=order_dict["status"],
                filled_avg_price=order_dict.get("filled_avg_price"),
                order_id=order_dict["order_id"],
            )
        )

    markers: list[AnalysisMarker] = []

    logger.info(
        "Portfolio history (suggestion-only mode)",
        period=period,
        order_markers=len(order_markers),
    )

    return PortfolioHistoryResponse(
        data_points=[],
        markers=markers,
        order_markers=order_markers,
        current_value=0.0,
        period=period,
    )
