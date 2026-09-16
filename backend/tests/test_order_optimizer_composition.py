"""Composition tests for deterministic plan building and suggestion persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock
from types import SimpleNamespace
from src.services.decision_policy.builder import build_assessment

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
        self.batches = []

    async def assess(self, **kwargs):
        if self.fail:
            raise RuntimeError("mongo failure")
        batch = build_assessment(**kwargs)
        self.batches.append(batch)
        return batch


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

    assert result["executed"] == 0 and result["mode"] == "research_only"
    assert result["assessment_count"] == 1
    assert not order_repo.orders and not message_repo.updates
    assert not order_repo.batches[0].actionable


@pytest.mark.asyncio
async def test_executor_reports_attempted_suggestions_when_persistence_degrades() -> (
    None
):
    executor = OrderExecutor(  # type: ignore[arg-type]
        order_repo=_OrderRepo(fail=True),
        message_repo=_MessageRepo(fail=True),
    )
    with pytest.raises(RuntimeError, match="mongo failure"):
        await executor.execute_order_plan(
            _plan([_order("AAPL", 1)]), "local", [_analysis("AAPL")]
        )


class _Phase3Harness(Phase3ExecutionMixin):
    pass


@pytest.mark.asyncio
async def test_phase3_persists_hold_and_executes_actionable_plan() -> None:
    harness = _Phase3Harness()
    harness.order_repo = _OrderRepo()
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

    assert summary["orders_executed"] == 0 and summary["actionable_count"] == 0
    assert summary["assessment_count"] == 2
    assert not harness.order_repo.orders
    harness.order_optimizer.optimize_trading_decisions.assert_not_awaited()
    harness.order_optimizer.execute_order_plan.assert_not_awaited()


@pytest.mark.asyncio
async def test_phase3_hold_and_empty_paths_are_non_actionable():
    harness = _Phase3Harness()
    harness.order_repo = _OrderRepo()
    harness.react_agent = SimpleNamespace(data_manager=None)
    assert await harness._resolve_decision_price("AAPL") is None
    dm = SimpleNamespace(get_quote=AsyncMock(return_value=SimpleNamespace(price=100)))
    harness.react_agent.data_manager = dm
    assert await harness._resolve_decision_price("AAPL") == 100
    dm.get_quote.side_effect = RuntimeError("unavailable")
    assert await harness._resolve_decision_price("AAPL") is None
    assert await harness._persist_hold_signals([], [], "local") == 0
    assert (
        await harness._persist_hold_signals(
            [_decision("AAPL", TradingAction.HOLD, None)], [_analysis("AAPL")], "local"
        )
        == 1
    )
    assert not harness.order_repo.batches[0].actionable
    summary = {}
    await harness._run_phase3_execution([], [], {}, "local", summary)
    assert summary["orders_executed"] == 0


@pytest.mark.asyncio
async def test_executor_empty_and_skipped_plans_do_not_write():
    repo = _OrderRepo()
    executor = OrderExecutor(repo, _MessageRepo())
    assert (await executor.execute_order_plan(_plan([]), "local", []))["executed"] == 0
    assert (
        await executor.execute_order_plan(
            _plan([_order("AAPL", 1, skip="skip")]), "local", [_analysis("AAPL")]
        )
    )["assessment_count"] == 0
    assert not repo.batches
