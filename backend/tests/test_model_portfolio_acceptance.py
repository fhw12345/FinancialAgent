"""Budget/model-quality oracles run without any real network or private credentials."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import yfinance as yf

from src.services.decision_policy import control, model_decision
from src.services.decision_policy.model_decision import RequestModelDecision
from tests.evidence_fixtures import Database
from tests.model_portfolios import budget as limits
from tests.model_portfolios.budget import (
    Budget,
    BudgetStopped,
    CURRENT_CASE,
    GuardedTransport,
)
from tests.model_portfolios.cases import CASES, manifest
from tests.model_portfolios.inputs import SyntheticTicker, seed
from tests.model_portfolios.report import ledger_hashes, observe
from tests.test_model_decisions import Agent

BODY = {"model": "gpt-6-astra", "max_output_tokens": 4096}


@pytest.mark.asyncio
async def test_budget_survives_reregister_and_counts_at_most_six_actual_attempts():
    db = Database()
    first = Budget(db, "test-run", "replay")
    initial = await first.register()
    for selected in CASES[:6]:
        await first.reserve(selected.case_id, BODY)
    after = await Budget(db, "test-run", "replay").register()
    assert len(after["attempts"]) == 6 and after["deadline"] == initial["deadline"]
    with pytest.raises(BudgetStopped):
        await first.reserve("cash-rich", BODY)
    assert manifest()["max_calls"] == 6
    assert len(CASES) == 9 and sum(c.negative is None for c in CASES) == 6


@pytest.mark.asyncio
async def test_retry_zero_call_expiry_model_and_token_limits():
    db = Database()
    budget = Budget(db, "test-limits", "replay")
    with pytest.raises(BudgetStopped, match="Register"):
        await budget.state()
    await budget.register()
    for body in (
        {**BODY, "model": "other"},
        {**BODY, "max_output_tokens": 4097},
        {**BODY, "max_output_tokens": True},
    ):
        with pytest.raises(BudgetStopped, match="ceiling"):
            await budget.reserve("cash-rich", body)
    with pytest.raises(BudgetStopped, match="Zero-call"):
        await budget.reserve("disabled", BODY)
    await budget.reserve("cash-rich", BODY)
    with pytest.raises(BudgetStopped, match="retry"):
        await budget.reserve("cash-rich", BODY)
    row = db.get_collection(limits.COLLECTION).rows["test-limits"]
    row["deadline"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    with pytest.raises(BudgetStopped, match="expired"):
        await budget.reserve("concentrated", BODY)
    with pytest.raises(BudgetStopped, match="conflict"):
        await Budget(db, "test-limits", "live").register()


@pytest.mark.asyncio
async def test_forwarded_401_attempt_is_counted_and_native_retry_cannot_reach_network():
    db = Database()
    budget = Budget(db, "test-transport", "replay")
    await budget.register()
    forwarded = []

    def external(request):
        forwarded.append(request.url.path)
        return httpx.Response(401, json={"error": "recorded refusal"})

    guarded = GuardedTransport(budget, httpx.MockTransport(external), lambda: None)
    token = CURRENT_CASE.set("cash-rich")
    try:
        async with httpx.AsyncClient(transport=guarded) as client:
            assert (
                await client.post(
                    "https://api.individual.githubcopilot.com/responses", json=BODY
                )
            ).status_code == 401
            with pytest.raises(BudgetStopped):
                await client.post(
                    "https://api.individual.githubcopilot.com/responses", json=BODY
                )
    finally:
        CURRENT_CASE.reset(token)
    assert forwarded == ["/responses"]
    state = await budget.state()
    assert state["attempts"][0]["http_status"] == 401 and len(state["attempts"]) == 1
    assert state["attempts"][0]["usage"] is None


@pytest.mark.asyncio
async def test_guard_refuses_unknown_host_path_context_and_preserves_transport_failures():
    db = Database()
    budget = Budget(db, "test-guard", "replay")
    await budget.register()
    count = 0

    def external(request):
        nonlocal count
        count += 1
        raise httpx.ConnectError("recorded connection fault")

    guarded = GuardedTransport(budget, httpx.MockTransport(external), lambda: None)
    async with httpx.AsyncClient(transport=guarded) as client:
        with pytest.raises(BudgetStopped):
            await client.post(
                "https://api.individual.githubcopilot.com/responses", json=BODY
            )
        token = CURRENT_CASE.set("cash-rich")
        try:
            with pytest.raises(BudgetStopped, match="host"):
                await client.post("https://attacker.invalid/responses", json=BODY)
            with pytest.raises(Exception, match="not_allowlisted"):
                await client.post(
                    "https://api.individual.githubcopilot.com/chat/completions",
                    json=BODY,
                )
            with pytest.raises(httpx.ConnectError):
                await client.post(
                    "https://api.individual.githubcopilot.com/responses", json=BODY
                )
        finally:
            CURRENT_CASE.reset(token)
    assert (
        count == 1
        and (await budget.state())["attempts"][0]["status"] == "transport_failed"
    )


@pytest.mark.asyncio
async def test_all_synthetic_sources_precompute_real_evidence_risk_and_zero_call_rejections(
    monkeypatch,
):
    monkeypatch.setattr(yf, "Ticker", SyntheticTicker)
    for selected in CASES:
        db = Database()
        seeded = await seed(db, selected.case_id, "unit-suite")
        source = await __import__(
            "src.services.decision_policy.review_gate", fromlist=["source_record"]
        ).source_record(db, seeded["assessment_id"])
        assert (
            source.portfolio_risk.current.equity
            == selected.cash + selected.quantity * 100
        )
        if selected.negative:
            state = await control.read(db)
            agent = Agent()
            with pytest.raises(control.ReviewConflict):
                await model_decision.decide(
                    db,
                    agent,
                    RequestModelDecision(
                        expected_revision=state.revision,
                        expected_generation=state.generation,
                        request_id="negative-source-case",
                        assessment_id=source.assessment_id,
                        confirm=True,
                        acknowledgment="uses-model-allowance-recommendation-only-no-trade",
                    ),
                )
            assert agent.calls == 0
        else:
            _, eligible, scope = await model_decision.eligible(db, source.assessment_id)
            assert eligible.input_hash == source.input_hash and scope == [
                "AAPL",
                "MSFT",
            ]


@pytest.mark.asyncio
async def test_known_bad_model_has_quality_findings_even_when_gate_safely_blocks(
    monkeypatch,
):
    monkeypatch.setattr(yf, "Ticker", SyntheticTicker)
    db = Database()
    source = await seed(db, "cash-rich", "oracle-suite")
    budget = Budget(db, "oracle-suite", "replay")
    await budget.register()
    await budget.reserve("cash-rich", BODY)
    baseline = await ledger_hashes(db)
    record = await __import__(
        "src.services.decision_policy.review_gate", fromlist=["source_record"]
    ).source_record(db, source["assessment_id"])
    ev = record.strategy.reviews[0].conclusion.theses[0].evidence_ids
    from src.models.model_decision import ModelDecisionSet

    bad = ModelDecisionSet.model_validate(
        {
            "decisions": [
                {
                    "symbol": "AAPL",
                    "action": "BUY",
                    "target_weight": 0.9,
                    "rationale": "Known bad exposure/limit test",
                    "evidence_ids": ev,
                },
                {
                    "symbol": "MSFT",
                    "action": "HOLD",
                    "target_weight": None,
                    "rationale": "Wait",
                },
            ],
            "portfolio_summary": "Deliberately invalid test decision",
        }
    )
    state = await control.read(db)
    await model_decision.decide(
        db,
        Agent(bad),
        RequestModelDecision(
            expected_revision=state.revision,
            expected_generation=state.generation,
            request_id="known-bad-model-test",
            assessment_id=source["assessment_id"],
            confirm=True,
            acknowledgment="uses-model-allowance-recommendation-only-no-trade",
        ),
    )
    result = await observe(db, budget, "cash-rich", source["assessment_id"], baseline)
    assert result["engineering_containment_pass"] is True
    assert result["model_contract_quality"] == "findings"
    assert "open_permission_or_exposure:AAPL" in result["model_contract_findings"]
    assert "position_limit:AAPL" in result["model_contract_findings"]
    assert (
        result["review"]["readiness"] == "blocked"
        and not result["review"]["approvable"]
    )
