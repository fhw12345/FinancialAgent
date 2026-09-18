"""Explicit freshness, conflict, cost and period rejection oracles for the confirmed pilot."""

from datetime import date, timedelta
import pytest
from src.services.research_strategy.evaluation import evaluate
from src.models.research_strategy import StrategyConclusion, Forecast
from tests.strategy_evidence_fixtures import fixture, save


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,expected",
    [
        ("cost", "COST_POLICY_REVISION_MISMATCH"),
        ("missing_identity", "IDENTITY_UNAVAILABLE:instrument.country"),
        ("identity_conflict", "IDENTITY_CONFLICT:instrument.country"),
        ("future", "FUTURE_INPUT:eps"),
        ("old", "STALE_FINANCIAL:eps"),
        ("publication", "FUTURE_PUBLICATION:eps"),
        ("conflict", "CONFLICTING_INPUT:eps"),
        ("pit", "HISTORICAL_PIT_UNPROVEN"),
        ("peer_set", "PEER_SET_MISMATCH"),
        ("peer_industry", "PEER_INDUSTRY_MISMATCH"),
        ("stale_price", "STALE_PRICE"),
    ],
)
async def test_bad_receipts_do_not_become_usable_research(case, expected):
    db, s, peer = fixture()
    eps = next(r for r in s.records if r.metric == "eps")
    if case == "cost":
        s.policy_revision = 2
    if case == "missing_identity":
        s.records = [r for r in s.records if r.metric != "instrument.country"]
    if case == "identity_conflict":
        s.records.append(
            next(r for r in s.records if r.metric == "instrument.country").model_copy(
                update={"value": "Canada"}
            )
        )
    if case == "future":
        eps.period_end = date(2027, 1, 1)
    if case == "old":
        eps.period_end = date(2023, 12, 31)
    if case == "publication":
        eps.published_at = s.requested_as_of + timedelta(days=1)
    if case == "conflict":
        s.records.append(eps.model_copy(update={"value": 7.0}))
    if case == "pit":
        s.mode = "strict_historical"
    if case == "peer_set":
        s.strategy_peers = {}
    if case == "peer_industry":
        next(r for r in peer.records if r.metric == "instrument.industry").value = (
            "Other industry"
        )
        save(db, peer)
    if case == "stale_price":
        next(r for r in s.records if r.metric == "price.close_reference").period_end = (
            date(2026, 9, 16)
        )
    save(db, s)
    review = await evaluate(db, s)
    assert expected in review.errors
    assert review.status != "research_only" and not review.actionable


def test_duplicate_conditional_scenarios_are_not_a_distribution():
    f = Forecast(scenario="base", condition="Conditional")
    with pytest.raises(ValueError):
        StrategyConclusion(
            symbol="AAPL",
            stance="unknown",
            theses=[],
            scenarios=[f, f],
            report_markdown="No probability estimate",
        )
