"""
Phase 3: Execution - Order placement and execution.

This module orchestrates order execution via OrderOptimizer.
"""

import uuid
from typing import Any

import structlog

from ...core.utils.date_utils import utcnow
from ...models.portfolio import PortfolioOrder
from ...models.trading_decision import SymbolAnalysisResult, TradingAction

logger = structlog.get_logger()


class Phase3ExecutionMixin:
    """Mixin providing Phase 3 execution capabilities."""

    async def _resolve_decision_price(self, symbol: str) -> float | None:
        """Best-effort current quote for HOLD anchor. Uses DataManager fallback chain."""
        dm = getattr(getattr(self, "react_agent", None), "data_manager", None)
        if dm is None:
            return None
        try:
            quote = await dm.get_quote(symbol)
            return float(quote.price) if quote and quote.price else None
        except Exception as e:
            logger.debug("hold_price_lookup_failed", symbol=symbol, error=str(e))
            return None

    async def _persist_hold_signals(
        self,
        trading_decisions: list[Any],
        all_analysis_results: list[SymbolAnalysisResult],
        user_id: str,
    ) -> int:
        """Persist HOLD decisions as signal rows so the decision tracker can score them."""
        holds = [
            d
            for d in trading_decisions
            if getattr(d, "decision", None) == TradingAction.HOLD
        ]
        if not holds or not getattr(self, "order_repo", None):
            return 0

        analysis_by_symbol = {r.symbol: r for r in all_analysis_results}
        created = 0
        for d in holds:
            analysis = analysis_by_symbol.get(d.symbol)
            analysis_id = analysis.analysis_id if analysis else f"hold_{d.symbol}"
            chat_id = analysis.chat_id if analysis else "unknown"
            message_id = analysis.message_id if analysis else None
            decision_price = await self._resolve_decision_price(d.symbol)
            if not decision_price:
                logger.debug("hold_signal_skipped_no_price", symbol=d.symbol)
                continue

            row = PortfolioOrder(
                order_id=f"hold_{uuid.uuid4().hex[:12]}",
                chat_id=chat_id,
                user_id=user_id,
                message_id=message_id,
                alpaca_order_id=None,
                analysis_id=analysis_id,
                symbol=d.symbol,
                order_type="market",
                side="hold",
                quantity=0.0,
                limit_price=None,
                stop_price=None,
                time_in_force="day",
                status="signal",
                filled_qty=0.0,
                filled_avg_price=None,
                filled_at=None,
                error_message=None,
                created_at=utcnow(),
                decision_price=decision_price,
                decision_type="signal",
            )
            try:
                await self.order_repo.create(row)
                created += 1
            except Exception as e:
                logger.warning(
                    "hold_signal_persist_failed", symbol=d.symbol, error=str(e)
                )
        if created:
            logger.info("hold_signals_persisted", count=created)
        return created

    async def _run_phase3_execution(
        self,
        trading_decisions: list[Any],
        all_analysis_results: list[SymbolAnalysisResult],
        portfolio_context: dict[str, Any],
        user_id: str,
        result_summary: dict[str, Any],
    ) -> None:
        """
        Run Phase 3: Execute orders (SELLs first for liquidity, then BUYs).

        Args:
            trading_decisions: Trading decisions from Phase 2
            all_analysis_results: Symbol analyses from Phase 1
            portfolio_context: Portfolio state
            user_id: User ID for tracking
            result_summary: Result summary dict to update
        """
        if not trading_decisions:
            logger.info("Phase 2: No trading decisions made")
            return

        # Persist HOLD decisions as decision_type="signal" rows so the
        # decision tracker can mark them to market alongside BUY/SELL orders.
        result_summary["holds_persisted"] = await self._persist_hold_signals(
            trading_decisions, all_analysis_results, user_id
        )

        logger.info(
            "Phase 3: Converting decisions to execution plan",
            decisions_count=len(trading_decisions),
        )

        # Convert TradingDecisions to OrderExecutionPlan via optimizer
        execution_plan = await self.order_optimizer.optimize_trading_decisions(
            analysis_results=all_analysis_results,
            portfolio_context=portfolio_context,
            user_id=user_id,
            trading_decisions=trading_decisions,  # Pass pre-made decisions
        )

        if execution_plan and execution_plan.orders:
            logger.info(
                "Phase 3: Executing orders",
                orders_count=len(execution_plan.orders),
                scaling_applied=execution_plan.scaling_applied,
            )

            execution_result = await self.order_optimizer.execute_order_plan(
                plan=execution_plan,
                user_id=user_id,
                analysis_results=all_analysis_results,
            )

            result_summary["orders_executed"] = execution_result.get("executed", 0)
            result_summary["orders_failed"] = execution_result.get("failed", 0)
            result_summary["orders_skipped"] = execution_result.get("skipped", 0)

            logger.info(
                "Phase 3 complete: Order execution finished",
                executed=result_summary["orders_executed"],
                failed=result_summary["orders_failed"],
                skipped=result_summary["orders_skipped"],
            )
        else:
            logger.info("Phase 3: No actionable orders after optimization")
