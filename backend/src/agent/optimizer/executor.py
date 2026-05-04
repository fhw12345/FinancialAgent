"""
Order Suggestion Engine.

W5a: Alpaca live trading removed. This executor no longer submits orders to a
broker. Instead, every actionable order from the optimizer is persisted to the
``portfolio_orders`` MongoDB collection with ``status="suggested"`` so the user
can review and execute them manually.
"""

import uuid
from typing import Any

import structlog

from src.core.utils.date_utils import utcnow

from ...database.repositories.message_repository import MessageRepository
from ...database.repositories.portfolio_order_repository import PortfolioOrderRepository
from ...models.message import MessageMetadata
from ...models.portfolio import PortfolioOrder
from ...models.trading_decision import (
    OrderExecutionPlan,
    SymbolAnalysisResult,
)

logger = structlog.get_logger()


class OrderExecutor:
    """
    Persists the optimized order plan as *suggested* orders.

    No broker API is contacted. Each non-skipped order is written to MongoDB
    with ``status="suggested"`` so manual execution can pick them up.
    """

    def __init__(
        self,
        trading_service: Any,  # kept for signature compat; ignored
        order_repo: PortfolioOrderRepository,
        message_repo: MessageRepository,
    ):
        # trading_service is intentionally ignored after W5a.
        self.trading_service = None
        self.order_repo = order_repo
        self.message_repo = message_repo

    async def execute_order_plan(
        self,
        plan: OrderExecutionPlan,
        user_id: str,
        analysis_results: list[SymbolAnalysisResult],
    ) -> dict[str, Any]:
        """
        Persist the optimized order plan as suggestions (no broker call).

        Returns a summary mirroring the prior shape:
          ``{"executed": <suggested-count>, "failed": 0, "skipped": <n>, ...}``
        """
        if not plan.orders:
            logger.info("No orders to suggest")
            return {"executed": 0, "failed": 0, "skipped": 0, "reason": "no_orders"}

        sorted_orders = sorted(plan.orders, key=lambda o: o.priority)

        suggested_orders: list[PortfolioOrder] = []
        metadata_updates: list[tuple[str, MessageMetadata]] = []
        skipped = 0

        analysis_by_symbol = {r.symbol: r for r in analysis_results}

        for order in sorted_orders:
            if order.skip_reason:
                logger.info(
                    "Skipping order suggestion",
                    symbol=order.symbol,
                    reason=order.skip_reason,
                )
                skipped += 1
                continue

            analysis = analysis_by_symbol.get(order.symbol)
            analysis_id = (
                analysis.analysis_id if analysis else f"suggested_{order.symbol}"
            )
            chat_id = analysis.chat_id if analysis else "unknown"
            message_id = analysis.message_id if analysis else None

            suggested = PortfolioOrder(
                order_id=f"order_{uuid.uuid4().hex[:12]}",
                chat_id=chat_id,
                user_id=user_id,
                message_id=message_id,
                alpaca_order_id=None,  # never sent to a broker
                analysis_id=analysis_id,
                symbol=order.symbol,
                order_type="market",
                side=order.side,
                quantity=float(order.shares),
                limit_price=None,
                stop_price=None,
                time_in_force="day",
                status="suggested",
                filled_qty=0.0,
                filled_avg_price=None,
                filled_at=None,
                error_message=None,
                created_at=utcnow(),
                # Decision-tracking anchor: capture the price the AI saw.
                decision_price=float(order.estimated_price),
                decision_type="order",
            )
            suggested_orders.append(suggested)

            logger.info(
                "Order suggestion recorded",
                symbol=order.symbol,
                side=order.side,
                shares=order.shares,
                priority=order.priority,
                estimated_cost=order.estimated_cost,
            )

            if message_id:
                metadata_updates.append(
                    (
                        message_id,
                        MessageMetadata(
                            symbol=order.symbol,
                            order_placed=False,
                            order_id=suggested.order_id,
                        ),
                    )
                )

        if suggested_orders:
            try:
                await self.order_repo.create_many(suggested_orders)
            except Exception as e:
                logger.error(
                    "Batch suggested-order persistence failed",
                    error=str(e),
                    order_count=len(suggested_orders),
                )

        if metadata_updates:
            try:
                await self.message_repo.update_metadata_batch(metadata_updates)
            except Exception as e:
                logger.error(
                    "Batch metadata update failed",
                    error=str(e),
                    update_count=len(metadata_updates),
                )

        logger.info(
            "Order suggestions completed",
            suggested=len(suggested_orders),
            skipped=skipped,
            total_orders=len(sorted_orders),
        )

        return {
            "executed": len(suggested_orders),  # legacy key = suggested count
            "failed": 0,
            "skipped": skipped,
            "total_orders": len(sorted_orders),
            "mode": "suggestion_only",
        }
