"""Stage-A Phase 3: persist diagnostics only; no order plan is executed."""

from typing import TYPE_CHECKING, Any

from ...models.trading_decision import SymbolAnalysisResult, TradingAction
from ...services.decision_policy.context import current_run_id
from .decision_persistence import _trading_decisions_to_dicts

if TYPE_CHECKING:
    from ...database.repositories.portfolio_order_repository import (
        PortfolioOrderRepository,
    )
    from ..optimizer import OrderOptimizer


class Phase3ExecutionMixin:
    order_repo: "PortfolioOrderRepository"
    order_optimizer: "OrderOptimizer"
    react_agent: Any

    async def _resolve_decision_price(self, symbol: str) -> float | None:
        dm = getattr(getattr(self, "react_agent", None), "data_manager", None)
        if dm is None:
            return None
        try:
            quote = await dm.get_quote(symbol)
            return float(quote.price) if quote and quote.price else None
        except Exception:
            return None

    async def _persist_hold_signals(
        self,
        trading_decisions: list[Any],
        all_analysis_results: list[SymbolAnalysisResult],
        user_id: str,
    ) -> int:
        holds = [
            d
            for d in trading_decisions
            if getattr(d, "decision", None) == TradingAction.HOLD
        ]
        if not holds or not all_analysis_results:
            return 0
        batch = await self.order_repo.assess(
            request_key=(
                current_run_id()
                or ":".join(r.analysis_id for r in all_analysis_results)
            )
            + ":holds",
            run_id=current_run_id(),
            source="legacy_hold",
            symbols=[r.symbol for r in all_analysis_results],
            proposals=_trading_decisions_to_dicts(holds),
            research={r.symbol: r.analysis_text for r in all_analysis_results},
        )
        return len(batch.results)

    async def _run_phase3_execution(
        self,
        trading_decisions: list[Any],
        all_analysis_results: list[SymbolAnalysisResult],
        portfolio_context: dict[str, Any],
        user_id: str,
        result_summary: dict[str, Any],
    ) -> None:
        result_summary.update(
            orders_executed=0, orders_failed=0, orders_skipped=len(trading_decisions)
        )
        if not all_analysis_results:
            return
        batch = await self.order_repo.assess(
            request_key=current_run_id()
            or ":".join(r.analysis_id for r in all_analysis_results),
            run_id=current_run_id(),
            source="legacy_portfolio",
            symbols=[r.symbol for r in all_analysis_results],
            proposals=_trading_decisions_to_dicts(trading_decisions),
            research={r.symbol: r.analysis_text for r in all_analysis_results},
            holdings=[p["symbol"] for p in portfolio_context.get("positions", [])],
        )
        result_summary.update(
            assessment_count=len(batch.results),
            assessment_id=batch.assessment_id,
            actionable_count=0,
        )
