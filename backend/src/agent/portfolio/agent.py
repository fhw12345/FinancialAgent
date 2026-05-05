"""
Portfolio Analysis Agent - Autonomous portfolio analysis.

Main orchestration class that coordinates the 3-phase analysis flow:
- Phase 1: Research (concurrent symbol analysis)
- Phase 2: Decisions (holistic portfolio decisions)
- Phase 3: Execution (order placement)
"""

from typing import TYPE_CHECKING, Any

import structlog

from src.core.utils.date_utils import utcnow

from ...core.config import Settings
from ...database.mongodb import MongoDB
from ...database.repositories.chat_repository import ChatRepository
from ...database.repositories.message_repository import MessageRepository
from ...database.repositories.portfolio_order_repository import PortfolioOrderRepository
from ...database.repositories.user_repository import UserRepository
from ...database.repositories.watchlist_repository import WatchlistRepository
from ...services.context_window_manager import ContextWindowManager
from ..langgraph_react_agent import FinancialAnalysisReActAgent
from ..order_optimizer import OrderOptimizer
from .phase1_research import Phase1ResearchMixin
from .phase2_decisions import Phase2DecisionsMixin
from .phase3_execution import Phase3ExecutionMixin

if TYPE_CHECKING:
    from ...database.redis import RedisCache

logger = structlog.get_logger()


class PortfolioAnalysisAgent(
    Phase1ResearchMixin,
    Phase2DecisionsMixin,
    Phase3ExecutionMixin,
):
    """
    Autonomous agent for portfolio analysis.

    Features:
    - Analyzes all active user portfolios
    - Uses ReAct agent with 120 tools (2 local + 118 MCP)
    - Stores analysis results in MongoDB
    - Handles errors gracefully
    """

    def __init__(
        self,
        mongodb: MongoDB,
        react_agent: FinancialAnalysisReActAgent,
        settings: Settings,
        redis_cache: "RedisCache",
        market_service=None,  # AlphaVantageMarketDataService
        trading_service=None,  # AlpacaTradingService
    ):
        """
        Initialize portfolio analysis agent.

        Args:
            mongodb: MongoDB connection
            react_agent: ReAct agent with MCP tools
            settings: Application settings
            redis_cache: Redis cache used by the write-time translator in repos
            market_service: Alpha Vantage market data service
            trading_service: Alpaca trading service for order placement
        """
        self.mongodb = mongodb
        self.react_agent = react_agent
        self.settings = settings
        self.redis_cache = redis_cache
        self.market_service = market_service
        self.trading_service = trading_service

        # Repositories
        self.user_repo = UserRepository(mongodb.get_collection("users"))
        self.watchlist_repo = WatchlistRepository(mongodb.get_collection("watchlist"))
        self.chat_repo = ChatRepository(mongodb.get_collection("chats"), redis_cache)
        self.message_repo = MessageRepository(
            mongodb.get_collection("messages"), redis_cache
        )
        self.order_repo = PortfolioOrderRepository(
            mongodb.get_collection("portfolio_orders")
        )

        # Context window manager for sliding window + summary
        self.context_manager = ContextWindowManager(settings)

        # Order optimizer for Phase 2/3 (aggregation and execution)
        self.order_optimizer = OrderOptimizer(
            react_agent=react_agent,
            trading_service=trading_service,
            order_repo=self.order_repo,
            message_repo=self.message_repo,
        )

    async def analyze_all_portfolios(self, dry_run: bool = False) -> dict[str, Any]:
        """
        Run analysis for all active user portfolios.

        Args:
            dry_run: If True, don't write results to DB

        Returns:
            Execution summary with metrics
        """
        run_id = f"run_{utcnow().strftime('%Y%m%d_%H%M%S')}"
        started_at = utcnow()

        logger.info(
            "Portfolio analysis started",
            run_id=run_id,
            dry_run=dry_run,
        )

        # Get all active users with portfolios
        users_to_analyze = await self.user_repo.get_active_users_with_portfolios()

        results = {
            "run_id": run_id,
            "started_at": started_at.isoformat(),
            "dry_run": dry_run,
            "users_to_analyze": len(users_to_analyze),
            "users_analyzed": 0,
            "portfolios_analyzed": 0,
            "errors": [],
            "metrics": {},
        }

        if not users_to_analyze:
            logger.info("No users with portfolios to analyze", run_id=run_id)
            results["completed_at"] = utcnow().isoformat()
            return results

        # Analyze each user's portfolio
        for user in users_to_analyze:
            try:
                user_result = await self.analyze_user_portfolio(
                    user_id=user["user_id"],
                    dry_run=dry_run,
                )

                results["users_analyzed"] += 1
                results["portfolios_analyzed"] += user_result.get("portfolios_count", 0)

            except Exception as e:
                logger.error(
                    "Failed to analyze user portfolio",
                    run_id=run_id,
                    user_id=user.get("user_id"),
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True,
                )

                results["errors"].append(
                    {
                        "user_id": user.get("user_id"),
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )

        # Calculate metrics
        completed_at = utcnow()
        duration_seconds = (completed_at - started_at).total_seconds()

        results["completed_at"] = completed_at.isoformat()
        results["metrics"] = {
            "total_duration_seconds": duration_seconds,
            "avg_duration_per_user_seconds": (
                duration_seconds / results["users_analyzed"]
                if results["users_analyzed"] > 0
                else 0
            ),
        }

        # Store execution record in MongoDB
        if not dry_run:
            await self._store_execution_record(results)

        logger.info(
            "Portfolio analysis completed",
            run_id=run_id,
            users_analyzed=results["users_analyzed"],
            portfolios_analyzed=results["portfolios_analyzed"],
            errors_count=len(results["errors"]),
            duration_seconds=duration_seconds,
        )

        return results

    async def analyze_user_portfolio(
        self, user_id: str, dry_run: bool = False
    ) -> dict[str, Any]:
        """
        Run portfolio analysis with Research → Decide → Execute flow.

        Phase 1: Independent symbol research (concurrent, pure analysis)
        Phase 2: Portfolio Agent makes holistic decisions for all symbols
        Phase 3: Execute orders (SELLs first for liquidity, then BUYs)

        Analyzes:
        1. Holdings (current positions)
        2. Watchlist symbols
        (Market movers removed - were informational only, not actionable)

        Args:
            user_id: User identifier
            dry_run: If True, don't write results to DB or execute orders

        Returns:
            Analysis result summary
        """
        logger.info("Analyzing user portfolio", user_id=user_id, dry_run=dry_run)

        result_summary = {
            "user_id": user_id,
            "portfolios_count": 0,
            "holdings_analyzed": 0,
            "watchlist_analyzed": 0,
            "total_symbols_analyzed": 0,
            "decisions_made": 0,
            "orders_executed": 0,
            "orders_failed": 0,
            "orders_skipped": 0,
            "errors": [],
        }

        try:
            # 1. Get user's positions from Alpaca (single source of truth)
            positions = []
            if self.trading_service:
                try:
                    positions = await self.trading_service.get_positions(user_id)
                    logger.info(
                        "Retrieved Alpaca positions",
                        user_id=user_id,
                        positions_count=len(positions),
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to retrieve Alpaca positions - continuing without positions",
                        user_id=user_id,
                        error=str(e),
                    )
            else:
                logger.info(
                    "Trading service not available - skipping positions analysis"
                )

            # 2. Get user's watchlist
            watchlist_items = await self.watchlist_repo.get_by_user(user_id)
            logger.info(
                "Retrieved user watchlist",
                user_id=user_id,
                watchlist_count=len(watchlist_items),
            )

            # 3. Build portfolio context (used in Phase 2 for decisions)
            portfolio_context = None
            if self.trading_service:
                try:
                    account_summary = await self.trading_service.get_account_summary(
                        user_id
                    )
                    portfolio_context = {
                        "total_equity": float(account_summary.equity),
                        "buying_power": float(account_summary.buying_power),
                        "cash": float(account_summary.cash),
                        "positions": [
                            {
                                "symbol": pos.symbol,
                                "quantity": int(pos.quantity),
                                "market_value": float(pos.market_value),
                                "unrealized_pl_percent": float(pos.unrealized_pl_pct),
                            }
                            for pos in positions
                        ],
                    }
                    logger.info(
                        "Portfolio context built",
                        equity=portfolio_context["total_equity"],
                        buying_power=portfolio_context["buying_power"],
                        positions_count=len(portfolio_context["positions"]),
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to build portfolio context",
                        error=str(e),
                        error_type=type(e).__name__,
                    )

            # ================================================================
            # DEV MODE: Filter symbols if dev_analysis_symbols is set
            # ================================================================
            dev_symbols_str = self.settings.dev_analysis_symbols
            if dev_symbols_str and self.settings.is_development:
                # Parse comma-separated symbols from env var
                dev_symbols_set = {
                    s.strip().upper() for s in dev_symbols_str.split(",") if s.strip()
                }
                logger.info(
                    "DEV MODE: Limiting analysis to specific symbols",
                    dev_symbols=list(dev_symbols_set),
                )
                # Filter positions
                if positions:
                    original_count = len(positions)
                    positions = [
                        p for p in positions if p.symbol.upper() in dev_symbols_set
                    ]
                    logger.info(
                        "DEV MODE: Filtered positions",
                        original=original_count,
                        filtered=len(positions),
                    )
                # Filter watchlist items
                if watchlist_items:
                    original_count = len(watchlist_items)
                    watchlist_items = [
                        w
                        for w in watchlist_items
                        if w.symbol.upper() in dev_symbols_set
                    ]
                    logger.info(
                        "DEV MODE: Filtered watchlist",
                        original=original_count,
                        filtered=len(watchlist_items),
                    )

            # ================================================================
            # PHASE 1: Independent Symbol Research (NO portfolio context)
            # ================================================================
            all_analysis_results = await self._run_phase1_research(
                positions=positions,
                watchlist_items=watchlist_items,
                user_id=user_id,
                dry_run=dry_run,
                result_summary=result_summary,
            )

            # Check minimum success rate before Phase 2
            # Calculate total symbols that should have been analyzed
            position_symbols = {p.symbol for p in positions} if positions else set()
            watchlist_symbols = (
                {w.symbol for w in watchlist_items if w.symbol not in position_symbols}
                if watchlist_items
                else set()
            )
            total_symbols = len(position_symbols) + len(watchlist_symbols)

            if total_symbols > 0 and not dry_run:
                success_rate = len(all_analysis_results) / total_symbols
                min_rate = self.settings.portfolio_analysis_min_success_rate

                if success_rate < min_rate:
                    error_msg = (
                        f"Phase 1 success rate ({success_rate:.1%}) "
                        f"below threshold ({min_rate:.0%})"
                    )
                    logger.warning(
                        "Skipping Phase 2 due to low success rate",
                        success_rate=success_rate,
                        threshold=min_rate,
                        successful=len(all_analysis_results),
                        total=total_symbols,
                    )
                    result_summary["errors"].append(
                        {"type": "low_success_rate", "message": error_msg}
                    )

                    # Store failure message in Portfolio Decisions chat
                    await self._store_phase2_failure_message(
                        reason=error_msg,
                        success_rate=success_rate,
                        successful_count=len(all_analysis_results),
                        total_count=total_symbols,
                    )
                    return result_summary

            # ================================================================
            # PHASE 2: Portfolio Agent Decision (single holistic call)
            # ================================================================
            decision_result, trading_decisions = await self._run_phase2_decisions(
                all_analysis_results=all_analysis_results,
                portfolio_context=portfolio_context,
                user_id=user_id,
                dry_run=dry_run,
            )

            result_summary["decisions_made"] = len(trading_decisions)

            # ================================================================
            # PHASE 3: Order Execution (SELLs first for liquidity, then BUYs)
            # ================================================================
            await self._run_phase3_execution(
                trading_decisions=trading_decisions,
                all_analysis_results=all_analysis_results,
                portfolio_context=portfolio_context,
                user_id=user_id,
                result_summary=result_summary,
            )

            logger.info(
                "User portfolio analysis completed",
                user_id=user_id,
                total_analyzed=result_summary["total_symbols_analyzed"],
                holdings=result_summary["holdings_analyzed"],
                watchlist=result_summary["watchlist_analyzed"],
                decisions_made=result_summary["decisions_made"],
                orders_executed=result_summary["orders_executed"],
                errors=len(result_summary["errors"]),
            )

        except Exception as e:
            logger.error(
                "Portfolio analysis failed",
                user_id=user_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            result_summary["errors"].append({"type": "general", "error": str(e)})

        return result_summary

    async def _store_execution_record(self, execution_data: dict[str, Any]) -> None:
        """
        Store execution record in MongoDB.

        Args:
            execution_data: Execution result data
        """
        try:
            collection = self.mongodb.get_collection("portfolio_analysis_runs")
            await collection.insert_one(execution_data)

            logger.info(
                "Execution record stored",
                run_id=execution_data["run_id"],
            )

        except Exception as e:
            logger.error(
                "Failed to store execution record",
                run_id=execution_data.get("run_id"),
                error=str(e),
                error_type=type(e).__name__,
            )
            # Don't raise - execution succeeded even if record storage failed
