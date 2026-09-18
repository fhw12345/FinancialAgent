"""Real strategy capture/adapter/evaluation/model-boundary composition and historical compatibility."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from src.models.research_strategy import StrategyConclusion, StrategyConclusions, Thesis
from src.services.evidence import service as evidence
from src.services.evidence.context import evidence_scope
from src.services.research_strategy import service, context, store
from src.services.research_strategy.deep import verdict
from tests.evidence_fixtures import manager
from tests.test_strategy_state import database
from tests.strategy_fixtures import parameters
from tests.portfolio_risk_fixtures import snapshot as risk_snapshot, asset, policy


async def prepared():
    db = database()
    config = await store.confirm(db, parameters(), 0, "test", 1)
    dm = manager()
    market = dm._av_service
    market.get_company_overview.side_effect = lambda symbol: {
        "Symbol": symbol,
        "Currency": "USD",
        "FinancialCurrency": "USD",
        "QuoteType": "EQUITY",
        "Country": "United States",
        "Sector": "Technology",
        "Industry": "Same industry",
        "_source": "yfinance",
    }

    def statements(fields):
        return {
            "_source": "yfinance",
            "annualReports": [{"fiscalDateEnding": "2025-12-31", **fields}],
        }

    market.get_cash_flow = AsyncMock(
        return_value=statements(
            {"operatingCashflow": 150, "capitalExpenditures": -50, "netIncome": 50}
        )
    )
    market.get_balance_sheet = AsyncMock(
        return_value=statements(
            {"totalDebt": 100, "cashAndCashEquivalentsAtCarryingValue": 20}
        )
    )
    market.get_research_income = AsyncMock(
        return_value=statements(
            {
                "dilutedEPS": 5,
                "dilutedAverageShares": 10,
                "interestExpense": 10,
                "totalRevenue": 200,
            }
        )
    )
    risk = risk_snapshot(assets=[asset(), asset("MSFT")], confirmed=policy())
    snapshots = await evidence.prepare(
        db, dm, market, ["AAPL"], "strategy-run", risk, strategy=config.versions[0]
    )
    values = await service.reviews(db, snapshots)
    return db, snapshots, values


@pytest.mark.asyncio
async def test_actual_capture_freezes_peers_and_model_conclusion_is_not_a_trade():
    db, snapshots, values = await prepared()
    s = snapshots["AAPL"]
    review = values["AAPL"]
    assert s.strategy_version == review.contract.version_id and s.strategy_peers["MSFT"]
    assert (
        review.valuations[0].per_share_usd == 100
        and review.valuations[1].per_share_usd > 0
    )
    fact = next(r for r in s.records if r.metric == "eps")
    conclusion = StrategyConclusion(
        symbol="AAPL",
        stance="bullish",
        theses=[
            Thesis(
                text="Unverified thesis",
                evidence_ids=[fact.evidence_id],
                monitoring_rule="earnings_decline",
            )
        ],
        scenarios=[],
        report_markdown="Research only",
    )
    agent = MagicMock()
    agent.ainvoke_structured = AsyncMock(
        return_value=StrategyConclusions(conclusions=[conclusion])
    )
    with evidence_scope(snapshots), context.strategy_scope(values):
        assert "SPY" in context.phase1_prompt("AAPL")
        result, orders = await service.conclude(agent, [], snapshots)
        assert not orders and result.conclusions[0].portfolio_action is None
    await service.record_prompts(db, "strategy-run", values)
    assert (
        values["AAPL"].prompt_versions["strategy-conclusion"] == "strategy-conclusion@1"
    )
    summary = service.summary(values)
    assert summary and not summary.actionable
    assert not (await service.project(db, summary)).reviews[0].stale
    await store.deactivate(db, 1)
    assert (await service.project(db, summary)).reviews[0].stale
    assert values["AAPL"].contract.parameters.growth_rate == 0.03


@pytest.mark.asyncio
async def test_deep_uses_strategy_schema_and_restores_summary_from_sealed_inputs():
    db, snapshots, values = await prepared()
    s = snapshots["AAPL"]
    fact = next(r for r in s.records if r.metric == "eps")
    c = StrategyConclusion(
        symbol="AAPL",
        stance="neutral",
        theses=[
            Thesis(
                text="Conditional",
                evidence_ids=[fact.evidence_id],
                monitoring_rule="earnings_decline",
            )
        ],
        scenarios=[],
        report_markdown="Research only",
    )
    agent = MagicMock()
    agent.verdict_llm.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=c
    )
    with evidence_scope(snapshots), context.strategy_scope(values):
        out = await verdict(
            agent, {"symbol": "AAPL", "research_report": "Research"}, None
        )
    assert out["verdict"]["portfolio_action"] is None and "action" not in out["verdict"]
    restored = await service.saved_deep_summary(db, "strategy-run", "AAPL", c)
    assert restored.reviews[0].valuations == values["AAPL"].valuations
    assert restored.reviews[0].conclusion.stance == "neutral"


@pytest.mark.asyncio
async def test_active_input_edit_after_capture_does_not_change_frozen_contract():
    db, snapshots, values = await prepared()
    before = values["AAPL"].model_dump(mode="json")
    await store.confirm(db, parameters(growth_rate=0.04), 1, "new-version", 1)
    after = await service.reviews(db, snapshots)
    assert after["AAPL"].model_dump(mode="json") == before
    assert (await service.project(db, service.summary(after))).reviews[0].stale
