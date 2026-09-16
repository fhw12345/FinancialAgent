"""Watchlist drafts use the shared assessment boundary, not PortfolioOrder writes."""

from ...database.repositories.message_repository import MessageRepository
from ...database.repositories.portfolio_order_repository import PortfolioOrderRepository
from ...models.message import Message
from ..decision_policy.context import current_run_id


class OrderHandler:
    def __init__(
        self,
        message_repo: MessageRepository,
        order_repository: PortfolioOrderRepository | None,
    ) -> None:
        self.message_repo = message_repo
        self.order_repository = order_repository

    async def place_order(
        self,
        symbol: str,
        decision: str,
        position_size: int,
        analysis_id: str,
        chat_id: str,
        user_id: str,
        message: Message | None,
    ) -> None:
        if self.order_repository is None:
            raise RuntimeError("Assessment storage is unavailable")
        await self.order_repository.assess(
            request_key=current_run_id() or analysis_id,
            run_id=current_run_id(),
            source="watchlist",
            symbols=[symbol],
            proposals=[
                {
                    "symbol": symbol,
                    "decision": decision.upper(),
                    "position_size_percent": position_size,
                    "reasoning_summary": "Unverified watchlist draft; no execution plan.",
                }
            ],
            research={symbol: message.content if message else ""},
        )
        # No order_id/order_placed metadata: saving research is not order creation.
