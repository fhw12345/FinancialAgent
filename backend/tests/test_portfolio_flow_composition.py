"""Real Stage-A orchestration and policy with outer provider/storage fixtures."""

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
from src.models.trading_decision import OrderIntent, SymbolAnalysisResult, TradingAction
from src.services.decision_policy.builder import build_assessment

SETTINGS = PortfolioSettings(
    cash_balance=100000, risk_tolerance="moderate", max_position_pct=10
)


class _Collection:
    def __init__(self, name):
        self.name = name

    def find(self, query):
        return self

    def sort(self, *args):
        return self

    async def __aiter__(self):
        for h in _HoldingRepo.holdings:
            yield {
                "holding_id": h.symbol,
                "symbol": h.symbol,
                "quantity": 1,
                "avg_price": 100,
                "cost_basis": 100,
            }

    async def find_one(self, query):
        return {"cash_balance": 100000} if self.name == "user_settings" else None


class _Mongo:
    def __init__(self):
        from tests.evidence_fixtures import Database

        self.evidence = Database()

    def get_collection(self, name):
        if name in ("research_snapshots", "research_dossiers"):
            return self.evidence.get_collection(name)
        return _Collection(name)


@pytest.fixture(autouse=True)
def recorded_risk_provider(monkeypatch):
    from tests.portfolio_risk_fixtures import ASOF, asset
    from src.services.portfolio_risk import service, provider

    async def fetch(symbol, session):
        row = asset(symbol)
        row.mark = 200.0
        return row

    monkeypatch.setattr(provider, "fetch_asset", fetch)
    monkeypatch.setattr(service, "completed_session", lambda now: ASOF)


class _HoldingRepo:
    holdings = []

    def __init__(self, collection):
        pass

    async def list_by_user(self):
        return self.holdings


class _OrderRepo:
    batches = []

    def __init__(self, collection=None):
        self.fail = False

    async def assess(self, **kwargs):
        if self.fail:
            raise RuntimeError("mongo unavailable")
        batch = build_assessment(**kwargs)
        self.batches.append(batch)
        return batch


class _DataManager:
    def __init__(self, prices):
        from tests.evidence_fixtures import market

        self._av_service = market()
        self.get_ohlcv = AsyncMock(return_value=[])
        self.get_company_news = AsyncMock(return_value=[])
        self.get_insider_trades = AsyncMock(return_value=[])
        self.prices = prices

    async def get_quote(self, symbol):
        if symbol not in self.prices:
            raise RuntimeError("quote unavailable")
        return SimpleNamespace(price=self.prices[symbol])


def _app(pa, dm=None):
    return SimpleNamespace(
        state=SimpleNamespace(
            mongodb=_Mongo(),
            data_manager=dm or _DataManager({"AAPL": 200}),
            portfolio_agent=pa,
            redis=SimpleNamespace(),
        )
    )


def _research(symbol="AAPL"):
    from tests.evidence_fixtures import claim_block

    return SymbolAnalysisResult(
        symbol=symbol,
        analysis_type="holding",
        analysis_text="Grounded research" + claim_block(symbol),
        analysis_id=f"analysis_{symbol}",
        chat_id="ephemeral",
    )


def _decision(symbol="AAPL", action=TradingAction.BUY):
    return SimpleNamespace(
        symbol=symbol,
        decision=action,
        position_size_percent=5,
        entry_price=198.0,
        stop_loss=185.0,
        take_profit=225.0,
        reasoning_summary="Unverified research draft",
        intent=(
            OrderIntent.OPEN_LONG if action == TradingAction.BUY else OrderIntent.HOLD
        ),
    )


@pytest.mark.asyncio
async def test_consistency_annotations_flow_into_quality_metadata():
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
    quality = _build_data_quality_map([result])["AAPL"]
    assert quality["degraded_fields"] == ["cashflow unavailable"]
    assert quality["consistency_passed"] is False and not quality["check_unavailable"]
    assert result.prompt_versions["consistency-gate"] == "consistency-gate@2"


@pytest.mark.asyncio
async def test_persistence_retains_missing_symbols_and_propagates_whole_batch_failure():
    repo = _OrderRepo()
    repo.batches = []
    count = await _persist_decisions(
        [{"symbol": "AAPL", "decision": "HOLD", "reasoning_summary": "Wait"}],
        _DataManager({"AAPL": 200}),
        repo,
        source="holdings",
        run_id="r1",
        expected_symbols=["AAPL", "MISSING"],
        research_by_symbol={"AAPL": "Research"},
    )
    assert count == 2 and len(repo.batches) == 1 and not repo.batches[0].actionable
    assert repo.batches[0].results[1].readiness == "insufficient_evidence"
    repo.fail = True
    with pytest.raises(RuntimeError, match="mongo"):
        await _persist_decisions(
            [],
            _DataManager({}),
            repo,
            source="holdings",
            run_id="r2",
            expected_symbols=["AAPL"],
        )
    assert len(repo.batches) == 1


@pytest.mark.asyncio
async def test_persistence_does_not_generate_translations_or_orders():
    repo = _OrderRepo()
    repo.batches = []
    count = await _persist_decisions(
        [],
        _DataManager({"AAPL": 100}),
        repo,
        source="holdings",
        run_id="no-llm",
        expected_symbols=["AAPL"],
        research_by_symbol={"AAPL": "Research"},
        redis_cache=object(),
    )
    assert count == 1 and repo.batches[0].results[0].research == "Research"
    assert repo.batches[0].results[0].proposal is None


def test_decision_normalization_preserves_machine_fields():
    normalized = _trading_decisions_to_dicts([_decision()])
    assert normalized[0]["decision"] == "BUY" and normalized[0]["entry_price"] == 198


@pytest.mark.asyncio
async def test_holdings_full_pipeline_is_research_only_and_failed_gate_skips_phase2():
    _HoldingRepo.holdings = [SimpleNamespace(symbol="AAPL")]
    pa = SimpleNamespace(
        _run_phase1_research=AsyncMock(side_effect=lambda **kw: [_research()]),
        _run_phase2_decisions=AsyncMock(return_value=({}, [_decision()])),
    )
    with (
        patch("src.agent.portfolio.flows.HoldingRepository", _HoldingRepo),
        patch("src.agent.portfolio.flows.PortfolioOrderRepository", _OrderRepo),
        patch(
            "src.agent.portfolio.flows.build_context_from_mongo",
            AsyncMock(return_value={"positions": [], "cash": 100000}),
        ),
        patch(
            "src.agent.portfolio.flows.run_consistency_gate",
            AsyncMock(return_value=(GateVerdict(passed=True), [])),
        ),
    ):
        result = await run_analyze_holdings(_app(pa), SETTINGS)
    assert result["result_count"] == 1 and result["actionable_count"] == 0
    pa._run_phase2_decisions.assert_awaited_once()
    pa._run_phase2_decisions.reset_mock()
    with (
        patch("src.agent.portfolio.flows.HoldingRepository", _HoldingRepo),
        patch("src.agent.portfolio.flows.PortfolioOrderRepository", _OrderRepo),
        patch(
            "src.agent.portfolio.flows.build_context_from_mongo",
            AsyncMock(return_value={"positions": []}),
        ),
        patch(
            "src.agent.portfolio.flows.run_consistency_gate",
            AsyncMock(side_effect=RuntimeError("secret-provider-error")),
        ),
    ):
        await run_analyze_holdings(_app(pa), SETTINGS)
    pa._run_phase2_decisions.assert_not_awaited()
    assert _OrderRepo.batches[-1].readiness == "needs_review"


@pytest.mark.asyncio
async def test_empty_holdings_and_missing_agent_never_use_fallback():
    _HoldingRepo.holdings = []
    with patch("src.agent.portfolio.flows.HoldingRepository", _HoldingRepo):
        assert (await run_analyze_holdings(_app(None), SETTINGS))["result_count"] == 0
    _HoldingRepo.holdings = [SimpleNamespace(symbol="AAPL")]
    with (
        patch("src.agent.portfolio.flows.HoldingRepository", _HoldingRepo),
        patch("src.agent.portfolio.flows.PortfolioOrderRepository", _OrderRepo),
        patch(
            "src.agent.portfolio.flows.build_context_from_mongo",
            AsyncMock(return_value={}),
        ),
        patch("src.agent.portfolio.flows._phase2_for_symbols", AsyncMock()) as shortcut,
    ):
        result = await run_analyze_holdings(_app(None), SETTINGS)
    shortcut.assert_not_awaited()
    assert result["assessment_count"] == 1 and result["actionable_count"] == 0
    assert _OrderRepo.batches[-1].readiness == "insufficient_evidence"


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["picks", "single_symbol"])
async def test_candidate_research_uses_full_account_not_an_empty_portfolio(source):
    from src.agent.portfolio.flows import _research_and_assess

    _HoldingRepo.holdings = [SimpleNamespace(symbol="AAPL")]
    pa = SimpleNamespace(
        _run_phase1_research=AsyncMock(side_effect=lambda **kw: [_research("MSFT")]),
        _run_phase2_decisions=AsyncMock(return_value=({}, [_decision("MSFT")])),
    )
    with patch("src.agent.portfolio.flows.PortfolioOrderRepository", _OrderRepo):
        await _research_and_assess(
            _app(pa), SETTINGS, ["MSFT"], {"positions": []}, source, as_holdings=False
        )
    context = pa._run_phase2_decisions.await_args.kwargs["portfolio_context"]
    assert context["positions"][0]["symbol"] == "AAPL"
    assert context["positions"][0]["quantity"] == 1
    assert {a["symbol"] for a in context["risk_snapshot"]["assets"]} == {"AAPL", "MSFT"}
    assert _OrderRepo.batches[-1].portfolio_risk.current.equity == 100200
    assert not _OrderRepo.batches[-1].actionable


@pytest.mark.asyncio
async def test_single_symbol_validates_input_and_records_missing_research():
    pa = SimpleNamespace(_run_phase1_research=AsyncMock(return_value=[]))
    with (
        patch("src.agent.portfolio.flows.HoldingRepository", _HoldingRepo),
        patch("src.agent.portfolio.flows.PortfolioOrderRepository", _OrderRepo),
    ):
        result = await run_single_symbol(_app(pa), " msft ")
    assert result["symbol"] == "MSFT" and result["actionable_count"] == 0
    assert result["assessment_count"] == 1
    with pytest.raises(ValueError, match="Invalid requested symbol"):
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
