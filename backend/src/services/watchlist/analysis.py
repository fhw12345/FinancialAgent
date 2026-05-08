"""
Core analysis logic for watchlist analyzer.

Handles LLM agent invocation, fallback Fibonacci analysis, and analysis cycles.
"""

import asyncio
import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog

from src.core.utils.date_utils import utcnow

from ...core.financial_analysis import FibonacciAnalyzer
from ...database.repositories.message_repository import MessageRepository
from ...database.repositories.watchlist_repository import WatchlistRepository
from ...models.message import MessageCreate, MessageMetadata
from ..context_window_manager import ContextWindowManager
from .chat_manager import ChatManager
from .context_handler import ContextHandler
from .order_handler import OrderHandler

logger = structlog.get_logger()


class AnalysisEngine:
    """Core analysis engine for watchlist symbols."""

    def __init__(
        self,
        watchlist_repo: WatchlistRepository,
        message_repo: MessageRepository,
        chat_manager: ChatManager,
        context_manager: ContextWindowManager,
        market_service,
        settings,
        data_manager=None,
        agent=None,
        trading_service=None,
        order_repository=None,
    ):
        """
        Initialize analysis engine.

        Args:
            watchlist_repo: Repository for watchlist operations
            message_repo: Repository for message operations
            chat_manager: Chat management helper
            context_manager: Context window manager for history management
            market_service: Market data service (e.g., AlphaVantage)
            settings: Application settings
            data_manager: Singleton DataManager for cached OHLCV access
            agent: Optional LLM agent for analysis
            trading_service: Optional trading service for order placement
            order_repository: Optional repository for persisting orders
        """
        self.watchlist_repo = watchlist_repo
        self.message_repo = message_repo
        self.chat_manager = chat_manager
        self.context_manager = context_manager
        self.market_service = market_service
        self.settings = settings
        self.data_manager = data_manager
        self.agent = agent
        self.trading_service = trading_service
        self.order_repository = order_repository

        # Initialize helper components
        self.context_handler = ContextHandler(
            message_repo=message_repo,
            context_manager=context_manager,
            settings=settings,
            agent=agent,
        )
        self.order_handler = OrderHandler(
            message_repo=message_repo,
            trading_service=trading_service,
            order_repository=order_repository,
        )

    async def analyze_symbol(
        self, symbol: str, user_id: str = "default_user", analysis_id: str | None = None
    ) -> bool:
        """
        Run LLM agent analysis on a single symbol with MCP tools.

        Args:
            symbol: Stock symbol to analyze
            user_id: User ID for the analysis
            analysis_id: Optional analysis ID for grouping

        Returns:
            True if analysis succeeded, False otherwise
        """
        try:
            # Generate analysis_id if not provided (format: symbol_YYYYMMDD_HHMMSS)
            if analysis_id is None:
                timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
                analysis_id = f"{symbol}_{timestamp}"

            logger.info(
                "Running agent-based analysis",
                symbol=symbol,
                user_id=user_id,
                analysis_id=analysis_id,
                has_agent=self.agent is not None,
            )

            # If no agent, fall back to basic Fibonacci
            if not self.agent:
                logger.warning(
                    "No agent available, falling back to basic Fibonacci analysis",
                    symbol=symbol,
                )
                return await self._fallback_fibonacci_analysis(symbol, analysis_id)

            # Use LLM agent for comprehensive analysis
            # Invalidate cached quote so the agent's quote tools see a fresh
            # price (otherwise a 5-min stale RTH quote can leak into the
            # research during pre/post-market).
            if self.data_manager is not None:
                try:
                    await self.data_manager.invalidate_quote(symbol)
                except Exception as e:
                    logger.debug(
                        "watchlist_invalidate_quote_failed",
                        symbol=symbol,
                        error=str(e),
                    )
            prompt = self._build_analysis_prompt(symbol)

            # Get symbol-specific chat ID (one chat per symbol) - BEFORE invoking agent
            chat_id = await self.chat_manager.get_symbol_chat_id(symbol)

            # Fetch historical messages for context management
            historical_messages = await self.message_repo.get_by_chat(chat_id)

            # Prepare conversation history for agent
            conversation_history = (
                await self.context_handler.prepare_conversation_history(
                    historical_messages, chat_id, symbol
                )
            )

            logger.info(
                "Invoking agent for analysis",
                symbol=symbol,
                conversation_history_length=len(conversation_history),
            )

            # Invoke agent with conversation history
            response = await self.agent.ainvoke(
                prompt, conversation_history=conversation_history
            )

            logger.info(
                "Agent analysis complete",
                symbol=symbol,
                response_length=len(str(response)),
            )

            # Parse agent response and create message
            decision, position_size, response_text = self._parse_agent_response(
                response
            )

            # Create analysis message
            message = await self._create_analysis_message(
                chat_id, symbol, decision, position_size, analysis_id, response_text
            )

            logger.info(
                "Agent analysis completed",
                symbol=symbol,
                decision=decision,
                position_size=position_size,
                analysis_id=analysis_id,
            )

            # Place order if decision is BUY or SELL
            if decision in ["BUY", "SELL"] and position_size and self.trading_service:
                await self.order_handler.place_order(
                    symbol,
                    decision,
                    position_size,
                    analysis_id,
                    chat_id,
                    user_id,
                    message,
                )

            return True

        except Exception as e:
            logger.error(
                "Agent analysis failed",
                symbol=symbol,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    def _build_analysis_prompt(self, symbol: str) -> str:
        """
        Build analysis prompt for LLM agent.

        Args:
            symbol: Stock symbol to analyze

        Returns:
            Analysis prompt string
        """
        return f"""Analyze the stock symbol {symbol} and provide:

1. Technical Analysis: Use Fibonacci retracement, trend analysis, and any other technical indicators
2. Fundamental Data: Use AlphaVantage MCP tools to get company fundamentals, earnings, news sentiment
3. Trading Decision: Based on the analysis, recommend one of:
   - BUY (if strong bullish signals)
   - SELL (if strong bearish signals)
   - HOLD (if neutral or unclear)
4. Position Size: If BUY or SELL, suggest a position size (percentage of portfolio, e.g., 5%, 10%)

Provide a concise analysis with clear reasoning for your trading decision.
Format your response as:
DECISION: [BUY/SELL/HOLD]
POSITION_SIZE: [percentage if BUY/SELL, or N/A if HOLD]
REASONING: [your analysis]
"""

    def _parse_agent_response(self, response) -> tuple[str, int | None, str]:
        """
        Parse agent response to extract decision, position size, and response text.

        Args:
            response: Agent response (dict or string)

        Returns:
            Tuple of (decision, position_size, response_text)
        """
        # Parse agent response - extract final_answer from dict response
        if isinstance(response, dict) and "final_answer" in response:
            response_text = response["final_answer"]
        else:
            response_text = str(response)

        # Extract decision
        decision = "HOLD"
        position_size = None

        if "DECISION:" in response_text:
            decision_line = [
                line for line in response_text.split("\n") if "DECISION:" in line
            ][0]
            if "BUY" in decision_line.upper():
                decision = "BUY"
            elif "SELL" in decision_line.upper():
                decision = "SELL"

        if "POSITION_SIZE:" in response_text:
            size_line = [
                line for line in response_text.split("\n") if "POSITION_SIZE:" in line
            ][0]
            # Extract percentage (e.g., "5%" or "5") - match number followed by %
            match = re.search(r"(\d+)%", size_line)
            if match:
                position_size = int(match.group(1))

        return decision, position_size, response_text

    async def _create_analysis_message(
        self,
        chat_id: str,
        symbol: str,
        decision: str,
        position_size: int | None,
        analysis_id: str,
        response_text: str,
    ):
        """
        Create and persist analysis message.

        Args:
            chat_id: Chat ID for the symbol
            symbol: Stock symbol
            decision: Trading decision (BUY/SELL/HOLD)
            position_size: Optional position size percentage
            analysis_id: Analysis ID
            response_text: Full response text from agent

        Returns:
            Created message object
        """
        message_content = f"## 🤖 AI Agent Analysis - {symbol}\n\n"
        message_content += f"**Decision:** {decision}\n"
        if position_size:
            message_content += f"**Position Size:** {position_size}%\n"
        message_content += f"**Analysis ID:** {analysis_id}\n\n"
        message_content += f"{response_text}\n"

        metadata = MessageMetadata(
            symbol=symbol,
            interval="1d",
            analysis_id=analysis_id,
            # Add decision metadata for order placement
            trend_direction=decision.lower() if decision in ["BUY", "SELL"] else None,
        )

        message_create = MessageCreate(
            chat_id=chat_id,
            role="assistant",
            content=message_content,
            source="llm",
            metadata=metadata,
        )
        return await self.message_repo.create(message_create)

    async def _fallback_fibonacci_analysis(self, symbol: str, analysis_id: str) -> bool:
        """
        Fallback to basic Fibonacci analysis if agent not available.

        Args:
            symbol: Stock symbol to analyze
            analysis_id: Analysis ID

        Returns:
            True if analysis succeeded, False otherwise
        """
        try:
            if not self.data_manager:
                logger.error("DataManager not available for Fibonacci analysis")
                return False

            analyzer = FibonacciAnalyzer(self.data_manager)
            end_date = datetime.now(ZoneInfo("Asia/Shanghai")).date()
            start_date = end_date - timedelta(days=180)

            result = await analyzer.analyze(
                symbol=symbol,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                timeframe="1d",
            )

            trend = (
                result.market_structure.trend_direction
                if result.market_structure
                else None
            )
            levels = (
                [level.price for level in result.fibonacci_levels[:5]]
                if result.fibonacci_levels
                else []
            )

            metadata = MessageMetadata(
                symbol=symbol,
                interval="1d",
                trend_direction=trend,
                key_levels=levels,
                analysis_id=analysis_id,
            )

            chat_id = await self.chat_manager.get_symbol_chat_id(symbol)

            message_content = f"## 📊 Fibonacci Analysis - {symbol}\n\n"
            message_content += f"**Trend:** {trend or 'Unknown'}\n"
            message_content += f"**Period:** {start_date} to {end_date}\n"
            message_content += f"**Confidence:** {result.confidence_score:.2%}\n"

            message_create = MessageCreate(
                chat_id=chat_id,
                role="assistant",
                content=message_content,
                source="llm",
                metadata=metadata,
            )
            await self.message_repo.create(message_create)

            logger.info(
                "Fallback Fibonacci analysis completed", symbol=symbol, trend=trend
            )
            return True

        except Exception as e:
            logger.error("Fallback analysis failed", symbol=symbol, error=str(e))
            return False

    async def run_analysis_cycle(self, force: bool = False):
        """
        Run one analysis cycle for all watchlist items.

        Args:
            force: If True, analyze all symbols regardless of last_analyzed_at.
                   If False, only analyze symbols not analyzed in last 5 minutes.

        Filters out watchlist items whose symbol is already in `holdings`,
        because those get covered by the dedicated portfolio (holdings) analysis
        and re-running them here just wastes a quote+LLM call.
        """
        try:
            logger.info("Starting watchlist analysis cycle", force=force)

            if force:
                # Get ALL watchlist items (manual trigger)
                items = await self.watchlist_repo.get_by_user("default_user")
            else:
                # Get stale items (not analyzed in last 5 minutes)
                items = await self.watchlist_repo.get_stale_items(minutes=5)

            if not items:
                logger.debug("No symbols need analysis")
                return

            # Skip symbols that are already held — those run through the
            # holdings analysis path. Use the same Mongo db that backs the
            # watchlist repo (zero new injection points).
            held_symbols: set[str] = set()
            try:
                db = self.watchlist_repo.collection.database
                async for h in db["holdings"].find({}, {"symbol": 1, "_id": 0}):
                    sym = h.get("symbol")
                    if sym:
                        held_symbols.add(str(sym).upper())
            except Exception as e:
                # Read failure should not block the cycle — log and proceed.
                logger.warning(
                    "holdings_dedup_lookup_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                )

            if held_symbols:
                before = len(items)
                items = [i for i in items if i.symbol.upper() not in held_symbols]
                skipped = before - len(items)
                if skipped:
                    logger.info(
                        "Watchlist symbols skipped (already in holdings)",
                        skipped=skipped,
                        remaining=len(items),
                    )

            if not items:
                logger.info("All watchlist symbols are held; nothing to analyze")
                return

            logger.info("Found symbols to analyze", count=len(items))

            # Analyze each symbol
            for item in items:
                try:
                    success = await self.analyze_symbol(item.symbol)

                    if not success:
                        logger.warning(
                            "Analysis returned failure",
                            symbol=item.symbol,
                        )
                except Exception as e:
                    logger.error(
                        "Analysis failed with exception",
                        symbol=item.symbol,
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    success = False
                finally:
                    # ALWAYS update last_analyzed_at to prevent infinite retry loops
                    # Even on failure, we don't want to retry immediately
                    await self.watchlist_repo.update_last_analyzed(
                        watchlist_id=item.watchlist_id,
                        timestamp=utcnow(),
                    )

                # Small delay between analyses to avoid rate limiting
                await asyncio.sleep(2)

            logger.info("Analysis cycle completed", analyzed=len(items))

        except Exception as e:
            logger.error(
                "Analysis cycle failed",
                error=str(e),
                error_type=type(e).__name__,
            )
