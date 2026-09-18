"""ST-01/03/08/10: scoped facts, frozen peers and data quality remain independent of model stance."""

import pytest
from src.services.research_strategy.evaluation import evaluate
from src.services.research_strategy import service, context
from src.models.research_strategy import (
    StrategyConclusion,
    StrategyConclusions,
    Thesis,
    Forecast,
    StrategySummary,
)
from src.models.portfolio_risk import PortfolioRiskReview
from src.services.portfolio_risk.estimator import estimate
from src.services.portfolio_risk.allocation import allocate
from src.services.decision_policy.builder import build_assessment
from tests.strategy_evidence_fixtures import fixture, save
from tests.portfolio_risk_fixtures import snapshot as risk_snapshot, policy


@pytest.mark.asyncio
async def test_frozen_peers_and_scoped_annual_evidence_produce_100_dollars():
    db, s, p = fixture()
    review = await evaluate(db, s)
    assert (
        review.status == "research_only" and review.valuations[0].per_share_usd == 100
    )
    assert review.valuations[1].enterprise_value > review.valuations[1].equity_value
    assert all(v.inputs for v in review.valuations)
    flags = {c.rule: c for c in review.checks}
    assert flags["earnings_decline"].status == "unavailable"
    assert flags["debt_to_fcf"].status == "not_triggered"
    assert flags["valuation_discount:peer_pe_annual@1"].status == "triggered"
    assert flags["valuation_discount:peer_pe_annual@1"].value == 0
    with context.strategy_scope({"AAPL": review}):
        prompt = context.phase1_prompt("AAPL")
        assert "252 XNYS" in prompt and "SPY" in prompt
        assert "REQUIRED for BUY/SELL" not in prompt
        assert review.prompt_versions == {
            "strategy-fundamental": "strategy-fundamental@1"
        }
    assert context.phase1_prompt("AAPL") is None
    p.run_id = "other"
    save(db, p)
    bad = await evaluate(db, s)
    assert (
        bad.valuations[0].status == "unavailable"
        and "PEER_SCOPE_MISMATCH" in bad.errors
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metric,change,reason",
    [
        ("instrument.type", {"value": "ETF"}, "INSTRUMENT_INAPPLICABLE"),
        ("instrument.country", {"value": "United Kingdom"}, "COUNTRY_INAPPLICABLE"),
        (
            "instrument.sector",
            {"value": "Financial Services"},
            "FINANCIAL_SECTOR_INAPPLICABLE",
        ),
        ("instrument.industry", {"value": "Insurance"}, "INDUSTRY_INAPPLICABLE"),
        ("eps", {"value": None, "quality": "missing"}, "INPUT_UNAVAILABLE:eps"),
        ("eps", {"unit": "USD million"}, "UNIT_MISMATCH:eps"),
    ],
)
async def test_missing_or_inapplicable_facts_never_produce_a_fair_value(
    metric, change, reason
):
    db, s, _ = fixture()
    s.records = [
        r.model_copy(update=change) if r.metric == metric else r for r in s.records
    ]
    save(db, s)
    review = await evaluate(db, s)
    assert reason in review.errors
    assert review.valuations[0].per_share_usd is None


@pytest.mark.asyncio
async def test_bullish_stance_does_not_override_account_risk_or_add_execution_intent():
    db, s, _ = fixture()
    review = await evaluate(db, s)
    fact = next(r for r in s.records if r.metric == "eps")
    conclusion = StrategyConclusion(
        symbol="AAPL",
        stance="bullish",
        theses=[
            Thesis(
                text="Conditional thesis",
                evidence_ids=[fact.evidence_id],
                monitoring_rule="earnings_decline",
            )
        ],
        scenarios=[],
        report_markdown="Unverified research",
    )
    service.apply_conclusions(
        {"AAPL": review}, {"AAPL": s}, StrategyConclusions(conclusions=[conclusion])
    )
    rs = risk_snapshot(confirmed=policy(max_position_weight=0.01))
    risk = PortfolioRiskReview(
        snapshot=rs, current=estimate(rs), allocation=allocate(rs, [])
    )
    assessment = build_assessment(
        request_key="risk",
        source="holdings",
        symbols=["AAPL"],
        proposals=[],
        research={"AAPL": "research"},
        portfolio_risk=risk,
        strategy=StrategySummary(reviews=[review], errors=[]),
    )
    assert assessment.readiness == "blocked" and not assessment.actionable
    assert assessment.strategy.reviews[0].conclusion.stance == "bullish"
    assert conclusion.portfolio_action is None and conclusion.execution_intent is None


@pytest.mark.asyncio
async def test_prior_year_monitoring_uses_history_without_relabeling_it_as_current():
    from datetime import date
    from src.services.evidence.identity import identify

    db, s, _ = fixture()
    current = next(r for r in s.records if r.metric == "eps")
    s.records.append(
        identify(
            current.model_copy(update={"period_end": date(2024, 12, 31), "value": 10.0})
        )
    )
    save(db, s)
    review = await evaluate(db, s)
    flag = next(c for c in review.checks if c.rule == "earnings_decline")
    assert flag.status == "triggered" and flag.value == 0.5 and flag.threshold == 0.2
    assert review.valuations[0].per_share_usd == 100


@pytest.mark.asyncio
async def test_model_claims_cannot_expand_scope_or_invent_verifiable_theses():
    db, s, _ = fixture()
    review = await evaluate(db, s)
    conclusion = StrategyConclusion(
        symbol="AAPL",
        stance="bullish",
        theses=[
            Thesis(
                text="Unsupported",
                evidence_ids=["ev_fake"],
                monitoring_rule="earnings_decline",
            )
        ],
        scenarios=[],
        report_markdown="Unverified",
    )
    service.apply_conclusions(
        {"AAPL": review}, {"AAPL": s}, StrategyConclusions(conclusions=[conclusion])
    )
    assert "THESIS_EVIDENCE_UNVERIFIED" in review.errors
    with pytest.raises(ValueError):
        service.apply_conclusions(
            {"AAPL": review},
            {"AAPL": s},
            StrategyConclusions(conclusions=[conclusion, conclusion]),
        )
    with pytest.raises(ValueError):
        StrategyConclusion(**conclusion.model_dump(), confidence=10)
