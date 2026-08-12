"""Composition tests for deterministic plan building and suggestion persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agent.optimizer.executor import OrderExecutor
from src.agent.optimizer.plan_builder import PlanBuilder
from src.agent.portfolio.phase3_execution import Phase3ExecutionMixin
from src.models.trading_decision import (
    OptimizedOrder,
    OrderExecutionPlan,
    OrderIntent,
    SymbolAnalysisResult,
    TradingAction,
    TradingDecision,
)


def _decision(
    symbol: str,
    action: TradingAction,
    size: int | None,
    *,
    intent: OrderIntent | None = None,
) -> TradingDecision:
    actionable = action != TradingAction.HOLD
    short_side = intent in (OrderIntent.OPEN_SHORT, OrderIntent.CLOSE_SHORT)
    return TradingDecision(
        symbol=symbol,
        decision=action,
        position_size_percent=size,
        confidence=7,
        entry_price=100 if actionable else None,
        stop_loss=(110 if short_side else 90) if actionable else None,
        take_profit=(80 if short_side else 120) if actionable else None,
        intent=intent,
        reasoning_summary="Deterministic fixture",
    )


def _analysis(symbol: str) -> SymbolAnalysisResult:
    return SymbolAnalysisResult(
        symbol=symbol,
        analysis_type="holding",
        analysis_text="Evidence",
        analysis_id=f"analysis_{symbol}",
        chat_id=f"chat_{symbol}",
        message_id=f"message_{symbol}",
    )


@pytest.mark.asyncio
async def test_plan_builder_handles_empty_and_hold_only_inputs() -> None:
    assert await PlanBuilder.build_execution_plan([], {}, "local", None) is None

    plan = await PlanBuilder.build_execution_plan(
        [_analysis("AAPL")],
        {"buying_power": 5000, "positions": []},
        "local",
        [_decision("AAPL", TradingAction.HOLD, None)],
    )
    assert plan is not None
    assert plan.orders == []
    assert plan.scaling_applied is False
    assert "HOLD" in plan.notes


@pytest.mark.asyncio
async def test_plan_orders_cover_sell_then_scaled_buys() -> None:
    decisions = [
        _decision("SHORT", TradingAction.SELL, 50, intent=OrderIntent.OPEN_SHORT),
        _decision("LONG", TradingAction.SELL, 50),
        _decision("NEW1", TradingAction.BUY, 80),
        _decision("NEW2", TradingAction.BUY, 80),
        _decision("MISSING", TradingAction.SELL, 50),
    ]
    positions = [
        {"symbol": "SHORT", "quantity": -10, "market_value": -1000},
        {"symbol": "LONG", "quantity": 20, "market_value": 200},
    ]

    plan = await PlanBuilder.build_execution_plan(
        [_analysis(d.symbol) for d in decisions],
        {"buying_power": 1000, "positions": positions},
        "local",
        decisions,
    )

    assert plan is not None
    assert [order.symbol for order in plan.orders[:2]] == ["SHORT", "LONG"]
    assert plan.orders[0].is_cover is True
    assert plan.orders[1].side == "sell"
    assert plan.scaling_applied is True
    assert plan.scaling_factor is not None and plan.scaling_factor < 1
    assert plan.orders_skipped >= 1
    assert [order.priority for order in plan.orders] == sorted(
        order.priority for order in plan.orders
    )


class _OrderRepo:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.orders: list[object] = []

    async def create_many(self, orders: list[object]) -> None:
        if self.fail:
            raise RuntimeError("mongo failure")
        self.orders.extend(orders)


class _MessageRepo:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.updates: list[object] = []

    async def update_metadata_batch(self, updates: list[object]) -> None:
        if self.fail:
            raise RuntimeError("metadata failure")
        self.updates.extend(updates)


def _order(symbol: str, priority: int, *, skip: str | None = None) -> OptimizedOrder:
    return OptimizedOrder(
        symbol=symbol,
        side="buy",
        shares=2,
        estimated_price=100,
        estimated_cost=200,
        original_size_percent=10,
        priority=priority,
        skip_reason=skip,
    )


def _plan(orders: list[OptimizedOrder]) -> OrderExecutionPlan:
    return OrderExecutionPlan(
        orders=orders,
        total_sell_proceeds=0,
        total_buy_cost=400,
        available_buying_power=1000,
        scaling_applied=False,
        orders_skipped=0,
        notes="Fixture plan",
    )


@pytest.mark.asyncio
async def test_executor_persists_suggestions_and_message_metadata() -> None:
    order_repo = _OrderRepo()
    message_repo = _MessageRepo()
    executor = OrderExecutor(order_repo=order_repo, message_repo=message_repo)  # type: ignore[arg-type]

    result = await executor.execute_order_plan(
        _plan([_order("SKIP", 3, skip="insufficient"), _order("AAPL", 1)]),
        "local",
        [_analysis("AAPL")],
    )

    assert result == {
        "executed": 1,
        "failed": 0,
        "skipped": 1,
        "total_orders": 2,
        "mode": "suggestion_only",
    }
    assert len(order_repo.orders) == 1
    suggested = order_repo.orders[0]
    assert suggested.status == "suggested"  # type: ignore[attr-defined]
    assert suggested.analysis_id == "analysis_AAPL"  # type: ignore[attr-defined]
    assert len(message_repo.updates) == 1


@pytest.mark.asyncio
async def test_executor_reports_attempted_suggestions_when_persistence_degrades() -> (
    None
):
    executor = OrderExecutor(  # type: ignore[arg-type]
        order_repo=_OrderRepo(fail=True),
        message_repo=_MessageRepo(fail=True),
    )
    result = await executor.execute_order_plan(
        _plan([_order("AAPL", 1)]), "local", [_analysis("AAPL")]
    )
    assert result["executed"] == 1
    assert result["failed"] == 0


class _Phase3Harness(Phase3ExecutionMixin):
    pass


@pytest.mark.asyncio
async def test_phase3_persists_hold_and_executes_actionable_plan() -> None:
    harness = _Phase3Harness()
    harness.order_repo = AsyncMock()
    harness.react_agent = type(
        "Agent",
        (),
        {
            "data_manager": type(
                "DM",
                (),
                {"get_quote": AsyncMock(return_value=type("Q", (), {"price": 200})())},
            )()
        },
    )()
    plan = _plan([_order("AAPL", 1)])
    harness.order_optimizer = type(
        "Optimizer",
        (),
        {
            "optimize_trading_decisions": AsyncMock(return_value=plan),
            "execute_order_plan": AsyncMock(
                return_value={"executed": 1, "failed": 0, "skipped": 0}
            ),
        },
    )()
    summary: dict[str, object] = {}
    decisions = [
        _decision("MSFT", TradingAction.HOLD, None),
        _decision("AAPL", TradingAction.BUY, 10),
    ]

    await harness._run_phase3_execution(
        decisions, [_analysis("MSFT"), _analysis("AAPL")], {}, "local", summary
    )

    assert summary == {
        "holds_persisted": 1,
        "orders_executed": 1,
        "orders_failed": 0,
        "orders_skipped": 0,
    }
    harness.order_repo.create.assert_awaited_once()
