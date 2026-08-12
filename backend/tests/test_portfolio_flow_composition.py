"""Composition tests for dashboard Portfolio orchestration.

Internal flow functions, domain models, consistency metadata, and persistence
translation are real. Mongo repositories, market providers, and LLM execution
are replaced only at their outer boundaries.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.agent.portfolio.consistency_gate import GateVerdict, GateViolation
from src.agent.portfolio.flows import (
    _apply_consistency_gate,
    _build_data_quality_map,
    _persist_decisions,
    _trading_decisions_to_dicts,
    run_analyze_holdings,
    run_single_symbol,
)
from src.agent.portfolio.phase1_research import Phase1ResearchMixin
from src.agent.portfolio.phase2_decisions import Phase2DecisionsMixin
from src.agent.portfolio_phase2_prompt import GovernedPortfolioDecisionList
from src.models.portfolio_analysis import PortfolioSettings
from src.models.trading_decision import (
    OrderIntent,
    SymbolAnalysisResult,
    TradingAction,
)

SETTINGS = PortfolioSettings(
    cash_balance=100_000,
    risk_tolerance="moderate",
    max_position_pct=10,
)


class _Mongo:
    def get_collection(self, name: str) -> object:
        return object()


class _HoldingRepo:
    holdings: list[Any] = []

    def __init__(self, collection: object) -> None:
        self.collection = collection

    async def list_by_user(self) -> list[Any]:
        return self.holdings


class _OrderRepo:
    created: list[Any] = []
    fail_symbols: set[str] = set()

    def __init__(self, collection: object | None = None) -> None:
        self.collection = collection

    async def create(self, order: Any) -> Any:
        if order.symbol in self.fail_symbols:
            raise RuntimeError("mongo unavailable")
        self.created.append(order)
        return order


class _DataManager:
    def __init__(self, prices: dict[str, float]) -> None:
        self.prices = prices

    async def get_quote(self, symbol: str) -> Any:
        if symbol not in self.prices:
            raise RuntimeError("quote unavailable")
        return SimpleNamespace(
            price=self.prices[symbol], session="regular", source="fixture"
        )


def _app(pa: object | None, dm: object | None = None) -> Any:
    return SimpleNamespace(
        state=SimpleNamespace(
            mongodb=_Mongo(),
            data_manager=dm or _DataManager({"AAPL": 200}),
            portfolio_agent=pa,
            redis=SimpleNamespace(),
        )
    )


def _research(symbol: str = "AAPL") -> SymbolAnalysisResult:
    return SymbolAnalysisResult(
        symbol=symbol,
        analysis_type="holding",
        analysis_text="Grounded research",
        analysis_id=f"analysis_{symbol}",
        chat_id="ephemeral",
    )


def _decision(symbol: str = "AAPL", action: TradingAction = TradingAction.BUY) -> Any:
    return SimpleNamespace(
        symbol=symbol,
        decision=action,
        position_size_percent=5,
        confidence=8,
        entry_price=198.0,
        stop_loss=185.0,
        take_profit=225.0,
        reasoning_summary="Grounded decision",
        intent=(
            OrderIntent.OPEN_LONG if action == TradingAction.BUY else OrderIntent.HOLD
        ),
        thesis=None,
        valuation=None,
        price_target=None,
        scenarios=None,
        catalysts=None,
        risks=None,
        entry_derivation=None,
        stop_derivation=None,
        target_derivation=None,
        size_derivation=None,
    )


@pytest.mark.asyncio
async def test_consistency_annotations_flow_into_quality_metadata() -> None:
    result = _research()
    verdict = GateVerdict(
        passed=False,
        violations=[GateViolation(field="cashflow", quote="unsupported claim")],
        prompt_versions={"consistency-gate": "consistency-gate@2"},
    )
    with patch(
        "src.agent.portfolio.flows.run_consistency_gate",
        AsyncMock(return_value=(verdict, ["cashflow unavailable"])),
    ):
        await _apply_consistency_gate([result])

    quality = _build_data_quality_map([result])
    assert quality["AAPL"] == {
        "degraded_fields": ["cashflow unavailable"],
        "consistency_violations": [{"field": "cashflow", "quote": "unsupported claim"}],
        "consistency_passed": False,
    }
    assert result.prompt_versions["consistency-gate"] == "consistency-gate@2"


@pytest.mark.asyncio
async def test_persistence_keeps_valid_rows_and_isolates_failures() -> None:
    repo = _OrderRepo()
    repo.created = []
    repo.fail_symbols = {"FAIL"}
    decisions = [
        {
            "symbol": "AAPL",
            "decision": "buy",
            "position_size_percent": 5,
            "confidence": 8,
            "reasoning_summary": "Buy reasoning",
            "entry_price": 198.0,
            "stop_loss": 185.0,
            "take_profit": 225.0,
            "intent": "open_long",
        },
        {"symbol": "BAD", "decision": "watch"},
        {"symbol": "NOPRICE", "decision": "hold"},
        {"symbol": "FAIL", "decision": "sell"},
    ]

    written = await _persist_decisions(
        decisions,
        _DataManager({"AAPL": 200, "FAIL": 50}),
        repo,
        source="holdings",
        run_id="run_composition",
        research_by_symbol={"AAPL": "Full evidence"},
        data_quality_by_symbol={
            "AAPL": {"degraded_fields": ["fundamentals unavailable"]}
        },
    )

    assert written == 1
    assert len(repo.created) == 1
    order = repo.created[0]
    assert order.symbol == "AAPL"
    assert order.analysis_id == "run_composition"
    assert order.metadata["full_research"] == "Full evidence"
    assert order.metadata["data_quality"]["degraded_fields"]
    assert order.decision_price == 200


@pytest.mark.asyncio
async def test_persistence_pretranslates_reasoning_and_research() -> None:
    repo = _OrderRepo()
    repo.created = []
    repo.fail_symbols = set()

    async def translate(values: dict[str, str], redis_cache: object) -> dict[str, str]:
        return {f"{key}_zh": f"ZH:{value}" for key, value in values.items()}

    with patch(
        "src.agent.portfolio.flows.translate_for_persistence",
        side_effect=translate,
    ):
        written = await _persist_decisions(
            [
                {
                    "symbol": "AAPL",
                    "decision": "hold",
                    "confidence": 6,
                    "reasoning_summary": "Wait for evidence",
                }
            ],
            _DataManager({"AAPL": 200}),
            repo,
            source="holdings",
            run_id="translated_run",
            research_by_symbol={"AAPL": "Long research"},
            redis_cache=object(),
        )

    assert written == 1
    metadata = repo.created[0].metadata
    assert metadata["reasoning_zh"] == "ZH:Wait for evidence"
    assert metadata["full_research_zh"] == "ZH:Long research"


def test_decision_normalization_preserves_machine_fields() -> None:
    normalized = _trading_decisions_to_dicts([_decision()])
    assert normalized[0]["decision"] == "BUY"
    assert normalized[0]["intent"] == "open_long"
    assert normalized[0]["entry_price"] == 198.0


@pytest.mark.asyncio
async def test_holdings_full_pipeline_composes_phase1_phase2_and_persistence() -> None:
    _HoldingRepo.holdings = [SimpleNamespace(symbol="AAPL")]
    pa = SimpleNamespace(
        _run_phase1_research=AsyncMock(return_value=[_research()]),
        _run_phase2_decisions=AsyncMock(return_value=({}, [_decision()])),
    )
    persist = AsyncMock(return_value=1)

    with (
        patch("src.agent.portfolio.flows.HoldingRepository", _HoldingRepo),
        patch("src.agent.portfolio.flows.PortfolioOrderRepository", _OrderRepo),
        patch(
            "src.agent.portfolio.flows.build_context_from_mongo",
            AsyncMock(return_value={"positions": [], "cash": 100_000}),
        ),
        patch("src.agent.portfolio.flows._apply_consistency_gate", AsyncMock()),
        patch("src.agent.portfolio.flows._persist_decisions", persist),
    ):
        result = await run_analyze_holdings(_app(pa), SETTINGS)

    assert result["result_count"] == 1
    pa._run_phase1_research.assert_awaited_once()
    pa._run_phase2_decisions.assert_awaited_once()
    persisted = persist.await_args.args[0]
    assert persisted[0]["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_holdings_empty_and_phase1_failure_are_terminal_without_writes() -> None:
    _HoldingRepo.holdings = []
    with (
        patch("src.agent.portfolio.flows.HoldingRepository", _HoldingRepo),
        patch("src.agent.portfolio.flows.PortfolioOrderRepository", _OrderRepo),
    ):
        empty = await run_analyze_holdings(_app(SimpleNamespace()), SETTINGS)
    assert empty == {"message": "Add holdings first", "result_count": 0}

    _HoldingRepo.holdings = [SimpleNamespace(symbol="AAPL")]
    pa = SimpleNamespace(_run_phase1_research=AsyncMock(return_value=[]))
    with (
        patch("src.agent.portfolio.flows.HoldingRepository", _HoldingRepo),
        patch("src.agent.portfolio.flows.PortfolioOrderRepository", _OrderRepo),
        patch(
            "src.agent.portfolio.flows.build_context_from_mongo",
            AsyncMock(return_value={}),
        ),
    ):
        failed = await run_analyze_holdings(_app(pa), SETTINGS)
    assert failed["result_count"] == 0
    assert "no research" in failed["message"]


@pytest.mark.asyncio
async def test_single_symbol_validates_input_and_runs_same_pipeline() -> None:
    pa = SimpleNamespace(
        _run_phase1_research=AsyncMock(return_value=[_research("MSFT")]),
        _run_phase2_decisions=AsyncMock(
            return_value=({}, [_decision("MSFT", TradingAction.HOLD)])
        ),
    )
    persist = AsyncMock(return_value=1)
    with (
        patch("src.agent.portfolio.flows.HoldingRepository", _HoldingRepo),
        patch("src.agent.portfolio.flows.PortfolioOrderRepository", _OrderRepo),
        patch("src.agent.portfolio.flows._apply_consistency_gate", AsyncMock()),
        patch("src.agent.portfolio.flows._persist_decisions", persist),
    ):
        result = await run_single_symbol(_app(pa), " msft ")

    assert result["symbol"] == "MSFT"
    assert result["result_count"] == 1
    with pytest.raises(ValueError, match="invalid symbol"):
        await run_single_symbol(_app(pa), "bad symbol!")


class _Phase1Harness(Phase1ResearchMixin):
    pass


@pytest.mark.asyncio
async def test_phase1_batches_deduplicates_and_stamps_real_watchlist_rows() -> None:
    harness = _Phase1Harness()
    harness.settings = SimpleNamespace(portfolio_analysis_batch_size=2)
    harness.watchlist_repo = SimpleNamespace(update_last_analyzed=AsyncMock())

    async def analyze(symbol: str, **kwargs: Any) -> SymbolAnalysisResult | None:
        if symbol == "NONE":
            return None
        if symbol == "ERROR":
            raise RuntimeError("provider failed")
        return _research(symbol)

    harness._analyze_symbol = AsyncMock(side_effect=analyze)  # type: ignore[method-assign]
    summary: dict[str, Any] = {
        "holdings_analyzed": 0,
        "watchlist_analyzed": 0,
        "errors": [],
    }
    positions = [SimpleNamespace(symbol="AAPL"), SimpleNamespace(symbol="NONE")]
    watchlist = [
        SimpleNamespace(symbol="AAPL", watchlist_id="duplicate"),
        SimpleNamespace(symbol="MSFT", watchlist_id="watch_msft"),
        SimpleNamespace(symbol="ERROR", watchlist_id="watch_error"),
    ]

    results = await harness._run_phase1_research(
        positions, watchlist, "local", False, summary, suppress_chat=True
    )

    assert [result.symbol for result in results] == ["AAPL", "MSFT"]
    assert summary["holdings_analyzed"] == 1
    assert summary["watchlist_analyzed"] == 1
    assert summary["total_symbols_analyzed"] == 2
    assert {error["symbol"] for error in summary["errors"]} == {"NONE", "ERROR"}
    harness.watchlist_repo.update_last_analyzed.assert_awaited_once()


@pytest.mark.asyncio
async def test_phase1_dry_run_counts_without_external_work() -> None:
    harness = _Phase1Harness()
    harness.settings = SimpleNamespace(portfolio_analysis_batch_size=2)
    harness.watchlist_repo = SimpleNamespace(update_last_analyzed=AsyncMock())
    harness._analyze_symbol = AsyncMock()  # type: ignore[method-assign]
    summary: dict[str, Any] = {
        "holdings_analyzed": 0,
        "watchlist_analyzed": 0,
        "errors": [],
    }

    results = await harness._run_phase1_research(
        [SimpleNamespace(symbol="AAPL")],
        [SimpleNamespace(symbol="MSFT")],
        "local",
        True,
        summary,
    )

    assert results == []
    assert summary["total_symbols_analyzed"] == 2
    harness._analyze_symbol.assert_not_awaited()


class _Phase2Harness(Phase2DecisionsMixin):
    pass


def _governed_decisions() -> GovernedPortfolioDecisionList:
    return GovernedPortfolioDecisionList(
        decisions=[], portfolio_assessment="No action required"
    )


@pytest.mark.asyncio
async def test_phase2_handles_preconditions_and_persists_success_message() -> None:
    harness = _Phase2Harness()
    harness.chat_repo = SimpleNamespace(
        list_by_user=AsyncMock(return_value=[]),
        create=AsyncMock(return_value=SimpleNamespace(chat_id="portfolio_chat")),
    )
    harness.message_repo = SimpleNamespace(
        create=AsyncMock(return_value=SimpleNamespace(message_id="message_1"))
    )
    harness._make_portfolio_decisions = AsyncMock(  # type: ignore[method-assign]
        return_value=_governed_decisions()
    )

    assert await harness._run_phase2_decisions([], {}, "local", True) == (None, [])
    assert await harness._run_phase2_decisions([], {"cash": 1}, "local", False) == (
        None,
        [],
    )
    missing_context = await harness._run_phase2_decisions(
        [_research()], {}, "local", False
    )
    assert missing_context == (None, [])

    result, decisions = await harness._run_phase2_decisions(
        [_research()],
        {"total_equity": 1000, "buying_power": 500},
        "local",
        False,
        flow="holdings",
    )
    assert result is not None
    assert decisions == []
    assert harness.message_repo.create.await_count == 3
    success_message = harness.message_repo.create.await_args_list[-1].args[0]
    assert "Portfolio Trading Decisions" in success_message.content
    assert success_message.metadata.raw_data["flow"] == "holdings"


@pytest.mark.asyncio
async def test_phase2_reuses_existing_chat_and_swallows_storage_failure() -> None:
    harness = _Phase2Harness()
    harness.chat_repo = SimpleNamespace(
        list_by_user=AsyncMock(
            return_value=[
                SimpleNamespace(title="Portfolio Decisions", chat_id="existing")
            ]
        ),
        create=AsyncMock(),
    )
    harness.message_repo = SimpleNamespace(
        create=AsyncMock(side_effect=RuntimeError("mongo failure"))
    )

    chat_id = await harness._get_portfolio_decisions_chat_id()
    assert chat_id == "existing"
    harness.chat_repo.create.assert_not_awaited()

    await harness._store_portfolio_decision_message(
        _governed_decisions(), [_research()], {"total_equity": 1000}
    )
    harness.message_repo.create.assert_awaited_once()
