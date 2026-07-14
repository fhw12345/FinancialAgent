"""
Order Optimizer - Modular structure.

Provides OrderOptimizer class that combines:
- Base initialization (base.py)
- Plan building (plan_builder.py)
- Order execution (executor.py)

This maintains backward compatibility with the original monolithic module.
"""

from typing import Any

from ...models.trading_decision import (
    OrderExecutionPlan,
    SymbolAnalysisResult,
    TradingDecision,
)
from .base import OrderOptimizerBase
from .executor import OrderExecutor
from .plan_builder import PlanBuilder

__all__ = ["OrderOptimizer"]


class OrderOptimizer(OrderOptimizerBase):
    """
    Phase 3: Order optimization and execution.

    Responsibilities:
    1. Convert TradingDecisions from Phase 2 into OrderExecutionPlan
    2. Calculate share quantities and apply liquidity constraints
    3. Persist suggestions (SELLs first for liquidity, then scaled BUYs)

    This class combines functionality from:
    - OrderOptimizerBase: Initialization and dependency management
    - PlanBuilder: Building execution plans from trading decisions
    - OrderExecutor: Persisting order suggestions
    """

    async def optimize_trading_decisions(
        self,
        analysis_results: list[SymbolAnalysisResult],
        portfolio_context: dict[str, Any],
        user_id: str,
        trading_decisions: list[TradingDecision] | None = None,
    ) -> OrderExecutionPlan | None:
        """
        Phase 3: Convert trading decisions into an optimized execution plan.

        Takes pre-made TradingDecisions from Phase 2 and builds an OrderExecutionPlan:
        1. SELLs first (to free up buying power / gain liquidity)
        2. Calculate available funds = current_buying_power + estimated_sell_proceeds
        3. Scale down BUYs proportionally if insufficient funds
        4. Return OrderExecutionPlan for execution

        Args:
            analysis_results: List of SymbolAnalysisResult from Phase 1 (for linking)
            portfolio_context: Portfolio state (equity, buying_power, positions)
            user_id: User ID for the portfolio
            trading_decisions: Pre-made decisions from Phase 2 (required in new flow)

        Returns:
            OrderExecutionPlan with optimized order sequence, or None if failed
        """
        return await PlanBuilder.build_execution_plan(
            analysis_results=analysis_results,
            portfolio_context=portfolio_context,
            user_id=user_id,
            trading_decisions=trading_decisions,
        )

    async def execute_order_plan(
        self,
        plan: OrderExecutionPlan,
        user_id: str,
        analysis_results: list[SymbolAnalysisResult],
    ) -> dict[str, Any]:
        """
        Persist the optimized order plan as local suggestions.

        Suggestions are stored in priority order (SELLs first, then BUYs).
        Database persistence is batched for efficiency.

        Args:
            plan: OrderExecutionPlan from aggregation hook
            user_id: User ID for the trades
            analysis_results: Original analysis results (for linking orders to messages)

        Returns:
            Execution summary with success/failure counts
        """
        executor = OrderExecutor(
            order_repo=self.order_repo,
            message_repo=self.message_repo,
        )

        return await executor.execute_order_plan(
            plan=plan,
            user_id=user_id,
            analysis_results=analysis_results,
        )
