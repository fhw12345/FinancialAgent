"""Portfolio research and decision pipeline used by the local dashboard."""

from typing import TYPE_CHECKING, Any

from ...core.config import Settings
from ...database.mongodb import MongoDB
from ...database.repositories.chat_repository import ChatRepository
from ...database.repositories.message_repository import MessageRepository
from ...database.repositories.portfolio_order_repository import PortfolioOrderRepository
from ...database.repositories.watchlist_repository import (
    WATCHLIST_COLLECTION,
    WatchlistRepository,
)
from ...services.context_window_manager import ContextWindowManager
from ..langgraph_react_agent import FinancialAnalysisReActAgent
from ..order_optimizer import OrderOptimizer
from .phase1_research import Phase1ResearchMixin
from .phase2_decisions import Phase2DecisionsMixin
from .phase3_execution import Phase3ExecutionMixin

if TYPE_CHECKING:
    from ...database.redis import RedisCache


class PortfolioAnalysisAgent(
    Phase1ResearchMixin,
    Phase2DecisionsMixin,
    Phase3ExecutionMixin,
):
    """Coordinates the local Phase 1 research and Phase 2 decision flows."""

    def __init__(
        self,
        mongodb: MongoDB,
        react_agent: FinancialAnalysisReActAgent,
        settings: Settings,
        redis_cache: "RedisCache",
        market_service: Any | None = None,
    ) -> None:
        self.mongodb = mongodb
        self.react_agent = react_agent
        self.settings = settings
        self.redis_cache = redis_cache
        self.market_service = market_service

        self.watchlist_repo = WatchlistRepository(
            mongodb.get_collection(WATCHLIST_COLLECTION)
        )
        self.chat_repo = ChatRepository(mongodb.get_collection("chats"), redis_cache)
        self.message_repo = MessageRepository(
            mongodb.get_collection("messages"), redis_cache
        )
        self.order_repo = PortfolioOrderRepository(
            mongodb.get_collection("portfolio_orders")
        )
        self.context_manager = ContextWindowManager(settings)
        self.order_optimizer = OrderOptimizer(
            react_agent=react_agent,
            order_repo=self.order_repo,
            message_repo=self.message_repo,
        )
