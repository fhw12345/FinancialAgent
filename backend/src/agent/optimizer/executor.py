"""Legacy optimized plans become non-actionable assessments, never order suggestions."""

from typing import Any

from ...database.repositories.message_repository import MessageRepository
from ...database.repositories.portfolio_order_repository import PortfolioOrderRepository
from ...models.trading_decision import OrderExecutionPlan, SymbolAnalysisResult
from ...services.decision_policy.context import current_run_id


class OrderExecutor:
    def __init__(
        self, order_repo: PortfolioOrderRepository, message_repo: MessageRepository
    ):
        self.order_repo = order_repo
        self.message_repo = message_repo

    async def execute_order_plan(
        self,
        plan: OrderExecutionPlan,
        user_id: str,
        analysis_results: list[SymbolAnalysisResult],
    ) -> dict[str, Any]:
        symbols = list(dict.fromkeys(r.symbol for r in analysis_results))
        if not plan.orders or not symbols:
            return {
                "executed": 0,
                "failed": 0,
                "skipped": len(plan.orders),
                "assessment_count": 0,
                "mode": "research_only",
                "reason": "no_orders_or_research_context",
            }
        rows = [
            {
                "symbol": o.symbol,
                "decision": o.side.upper(),
                "position_size_percent": o.original_size_percent,
                "entry_price": o.estimated_price,
                "reasoning_summary": plan.notes or "Legacy plan draft",
            }
            for o in plan.orders
            if not o.skip_reason
        ]
        if not rows:
            return {
                "executed": 0,
                "failed": 0,
                "skipped": len(plan.orders),
                "assessment_count": 0,
                "mode": "research_only",
            }
        key = current_run_id() or ":".join(
            sorted(r.analysis_id for r in analysis_results)
        )
        batch = await self.order_repo.assess(
            request_key=key,
            run_id=current_run_id(),
            source="optimizer",
            symbols=symbols,
            proposals=rows,
            research={r.symbol: r.analysis_text for r in analysis_results},
        )
        return {
            "executed": 0,
            "failed": 0,
            "skipped": len(plan.orders),
            "assessment_count": len(batch.results),
            "assessment_id": batch.assessment_id,
            "mode": "research_only",
        }
