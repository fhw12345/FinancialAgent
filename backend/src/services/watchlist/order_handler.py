"""
Order suggestion handler for watchlist analysis.

W5a: Alpaca live trading removed. Trading decisions are persisted to MongoDB
``portfolio_orders`` with ``status="suggested"`` instead of being submitted to
a broker.
"""

import uuid

import structlog

from src.core.utils.date_utils import utcnow

from ...database.repositories.message_repository import MessageRepository
from ...models.portfolio import PortfolioOrder

logger = structlog.get_logger()


class OrderHandler:
    """Handles order suggestion persistence for trading decisions."""

    def __init__(
        self,
        message_repo: MessageRepository,
        trading_service,  # ignored after W5a
        order_repository,
    ):
        self.message_repo = message_repo
        self.trading_service = None  # broker integration removed
        self.order_repository = order_repository

    async def place_order(
        self,
        symbol: str,
        decision: str,
        position_size: int,
        analysis_id: str,
        chat_id: str,
        user_id: str,
        message,
    ):
        """Persist a *suggested* order (no broker call)."""
        if not self.order_repository:
            logger.warning(
                "Order repository not available - suggestion not persisted",
                symbol=symbol,
            )
            return

        try:
            quantity = 1  # TODO: derive from position_size

            suggested = PortfolioOrder(
                order_id=f"order_{uuid.uuid4().hex[:12]}",
                chat_id=chat_id,
                user_id=user_id,
                message_id=message.message_id if message else None,
                alpaca_order_id=None,
                analysis_id=analysis_id,
                symbol=symbol,
                order_type="market",
                side=decision.lower(),
                quantity=float(quantity),
                limit_price=None,
                stop_price=None,
                time_in_force="day",
                status="suggested",
                filled_qty=0.0,
                filled_avg_price=None,
                filled_at=None,
                error_message=None,
                created_at=utcnow(),
            )

            await self.order_repository.create(suggested)
            logger.info(
                "Order suggestion persisted",
                symbol=symbol,
                side=suggested.side,
                analysis_id=analysis_id,
                order_id=suggested.order_id,
            )

            if message:
                message.metadata.order_placed = False
                message.metadata.order_id = suggested.order_id
                await self.message_repo.update_metadata(
                    message.message_id, message.metadata
                )
        except Exception as e:
            logger.error(
                "Failed to persist order suggestion",
                symbol=symbol,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Don't fail the whole analysis if suggestion persistence fails
