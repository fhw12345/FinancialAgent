"""
Watchlist Analyzer Service.

Automated analysis scheduler that runs Fibonacci analysis
on watchlist symbols every 5 minutes.
"""

import asyncio
import typing
from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorCollection

from ...core.config import Settings
from ...core.local_user import LOCAL_USER_ID
from ...database.redis import RedisCache
from ...database.repositories.chat_repository import ChatRepository
from ...database.repositories.message_repository import MessageRepository
from ...database.repositories.watchlist_repository import WatchlistRepository
from ..context_window_manager import ContextWindowManager
from .analysis import AnalysisEngine
from .chat_manager import ChatManager

logger = structlog.get_logger()


class WatchlistAnalyzer:
    """Automated watchlist analysis service."""

    def __init__(
        self,
        watchlist_collection: AsyncIOMotorCollection[dict[str, typing.Any]],
        messages_collection: AsyncIOMotorCollection[dict[str, typing.Any]],
        chats_collection: AsyncIOMotorCollection[dict[str, typing.Any]],
        redis_cache: RedisCache,
        market_service: Any,  # AlphaVantageMarketDataService for market data
        settings: Settings,  # Application settings for context management
        agent: Any | None = None,  # LLM agent for analysis
        order_repository: Any | None = None,
        data_manager: Any | None = None,
    ) -> None:
        """Initialize watchlist analyzer."""
        self.watchlist_repo = WatchlistRepository(watchlist_collection)
        self.message_repo = MessageRepository(messages_collection, redis_cache)
        self.chat_repo = ChatRepository(chats_collection, redis_cache)
        self.redis_cache = redis_cache
        self.market_service = market_service
        self.settings = settings
        self.agent = agent
        self.order_repository = order_repository
        self.data_manager = data_manager
        self.is_running = False
        self._task = None

        # Initialize context window manager for history management
        self.context_manager = ContextWindowManager(settings)

        # Initialize helper components
        self.chat_manager = ChatManager(self.chat_repo)

        # Initialize analysis engine with singleton DataManager
        self.analysis_engine = AnalysisEngine(
            watchlist_repo=self.watchlist_repo,
            message_repo=self.message_repo,
            chat_manager=self.chat_manager,
            context_manager=self.context_manager,
            market_service=self.market_service,
            settings=self.settings,
            data_manager=self.data_manager,
            agent=self.agent,
            order_repository=self.order_repository,
        )

    async def analyze_symbol(
        self, symbol: str, user_id: str = LOCAL_USER_ID, analysis_id: str | None = None
    ) -> bool:
        """
        Run LLM agent analysis on a single symbol with local tools.

        Args:
            symbol: Stock symbol to analyze
            user_id: User ID for the analysis
            analysis_id: Optional analysis ID for grouping

        Returns:
            True if analysis succeeded, False otherwise
        """
        return await self.analysis_engine.analyze_symbol(symbol, user_id, analysis_id)

    async def run_analysis_cycle(self, force: bool = False) -> None:
        """
        Run one analysis cycle for all watchlist items.

        Args:
            force: If True, analyze all symbols regardless of last_analyzed_at.
                   If False, only analyze symbols not analyzed in last 5 minutes.
        """
        await self.analysis_engine.run_analysis_cycle(force)

    async def start(self) -> None:
        """Start the automated analysis scheduler (runs every 5 minutes)."""
        if self.is_running:
            logger.warning("Watchlist analyzer already running")
            return

        self.is_running = True
        logger.info("Starting watchlist analyzer (5-minute cycle)")

        while self.is_running:
            try:
                await self.run_analysis_cycle()

                # Wait 5 minutes until next cycle
                await asyncio.sleep(5 * 60)

            except asyncio.CancelledError:
                logger.info("Watchlist analyzer cancelled")
                break
            except Exception as e:
                logger.error(
                    "Watchlist analyzer error",
                    error=str(e),
                    error_type=type(e).__name__,
                )
                # Wait a bit before retrying on error
                await asyncio.sleep(30)

    async def stop(self) -> None:
        """Stop the automated analysis scheduler."""
        logger.info("Stopping watchlist analyzer")
        self.is_running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
