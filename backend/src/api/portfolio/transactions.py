"""
Portfolio transactions endpoint.

Provides:
- GET /transactions: Fetch transaction history from MongoDB (includes failed orders)
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request

from ...database.mongodb import MongoDB
from ..dependencies.auth import get_mongodb
from ..dependencies.rate_limit import limiter

logger = structlog.get_logger()

router = APIRouter()


@router.get("/transactions")
@limiter.limit("60/minute")  # Database read - standard limit
async def get_portfolio_transactions(
    request: Request,
    limit: int = 10,
    offset: int = 0,
    status: str | None = None,  # "success", "failed", or None for all
    mongodb: MongoDB = Depends(get_mongodb),
) -> dict:
    """
    Get portfolio transactions from MongoDB (includes failed orders).

    Unlike /orders (Alpaca API), this endpoint returns transactions from our
    database which includes both successful and failed orders with error messages.

    Args:
        limit: Maximum number of transactions to return (default: 10)
        offset: Number of transactions to skip for pagination (default: 0)
        status: Filter by status - "success" (filled/new), "failed", or None for all

    Returns:
        List of transactions with execution details and error messages for failures
    """
    try:
        orders_collection = mongodb.get_collection("portfolio_orders")

        # Build query based on status filter
        query: dict = {}

        if status == "success":
            # Success = filled, new, partially_filled, accepted (anything that went to Alpaca)
            # Note: Status may include "OrderStatus." prefix from Alpaca SDK enum
            query["status"] = {
                "$in": [
                    "filled",
                    "new",
                    "partially_filled",
                    "accepted",
                    "pending_new",
                    "OrderStatus.FILLED",
                    "OrderStatus.NEW",
                    "OrderStatus.PARTIALLY_FILLED",
                    "OrderStatus.ACCEPTED",
                    "OrderStatus.PENDING_NEW",
                ]
            }
        elif status == "failed":
            # Failed = orders that failed before reaching Alpaca
            query["status"] = "failed"
        # else: no filter, return all

        # Get total count for pagination
        total_count = await orders_collection.count_documents(query)

        # Query with pagination
        cursor = (
            orders_collection.find(query)
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )

        transactions = []
        async for order_dict in cursor:
            order_dict.pop("_id", None)
            transactions.append(
                {
                    "order_id": order_dict.get("order_id"),
                    "alpaca_order_id": order_dict.get("alpaca_order_id"),
                    "symbol": order_dict.get("symbol"),
                    "side": order_dict.get("side"),
                    "quantity": order_dict.get("quantity"),
                    "order_type": order_dict.get("order_type"),
                    "status": order_dict.get("status"),
                    "filled_qty": order_dict.get("filled_qty", 0),
                    "filled_avg_price": order_dict.get("filled_avg_price"),
                    "error_message": order_dict.get(
                        "error_message"
                    ),  # For failed orders
                    "analysis_id": order_dict.get("analysis_id"),
                    "created_at": (
                        order_dict["created_at"].isoformat()
                        if order_dict.get("created_at")
                        else None
                    ),
                    "filled_at": (
                        order_dict["filled_at"].isoformat()
                        if order_dict.get("filled_at")
                        else None
                    ),
                }
            )

        logger.info(
            "Portfolio transactions retrieved",
            transaction_count=len(transactions),
            total_count=total_count,
            status_filter=status,
            offset=offset,
            limit=limit,
        )

        return {
            "transactions": transactions,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(transactions) < total_count,
        }

    except Exception as e:
        logger.error(
            "Failed to retrieve portfolio transactions",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve transaction history. Please try again later.",
        ) from e
