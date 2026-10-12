"""Truthful frozen risk context and versioned target-basis/provenance contracts."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.agent.prompt_registry import get_prompt
from src.models.decision_review import (
    ConfirmReviewPolicy,
    PreparedReview,
    ReviewPolicyVersion,
)
from src.services.decision_policy import (
    control,
    model_decision,
    policies,
    review_storage,
)
from src.services.decision_policy.model_risk_context import context
from src.services.portfolio_risk import service as risk
from tests.review_fixtures import setup
from tests.test_model_decisions import ENABLED, Agent, request


@pytest.mark.asyncio
async def test_prompt_uses_actual_frozen_risk_cash_positions_and_pending_check_semantics(
    monkeypatch,
):
    db, _, source, _ = await setup(monkeypatch, model_policy=ENABLED)
    policy = policies.active(await control.read(db))
    account, limits = context(source, policy, ["AAPL", "MSFT"])
    assert account["declared_cash"] == 9000
    assert account["positions"][0]["quantity"] == 10
    assert account["positions"][0]["closing_reference"] == 100
    assert (
        account["current_risk"]["account_sigma_annualized"]
        == source.portfolio_risk.current.account_sigma_annualized
    )
    assert (
        account["current_risk"]["invested_sigma_annualized"]
        == source.portfolio_risk.current.invested_sigma_annualized
    )
    assert account["current_risk"]["history_equity_coverage"] == 1
    assert len(account["current_risk"]["common_sessions"]) == 60
    assert limits["target_equity_basis"] == "pre_cost"
    assert "risk_per_trade_weight" not in limits["risk_policy"]
    assert limits["stop_risk_applicability"].startswith("not_applicable")
    old_fees = limits["risk_policy"]["fee_bps"]
    await risk.confirm_policy(
        db,
        source.portfolio_risk.snapshot.policy.policy.model_copy(
            update={"fee_bps": 5.0}
        ),
        1,
    )
    frozen = await model_decision.prompt(db, policy, source, ["AAPL", "MSFT"])
    assert json.dumps(old_fees) in frozen
    assert json.dumps({"risk_policy_revision": 1})[1:-1] in frozen
    assert "pending_code_validation_after_target_set" in frozen
    assert "Do not demand a finalized proposal" in frozen
    assert "no stop plan" in frozen
    assert (
        get_prompt("portfolio-model-decision").versioned_id
        == "portfolio-model-decision@2"
    )


@pytest.mark.asyncio
async def test_unknown_beta_and_context_correlation_slice_are_disclosed_not_zeroed(
    monkeypatch,
):
    db, _, source, _ = await setup(monkeypatch)
    source.portfolio_risk.current.beta_exposure = None
    source.portfolio_risk.snapshot.assets[0].beta = None
    source.portfolio_risk.current.correlations["MSFT"] = {"AAPL": 0.8, "MSFT": 1.0}
    account, _ = context(source, policies.active(await control.read(db)), ["AAPL"])
    assert account["current_risk"]["beta_exposure"] is None
    assert account["candidate_inputs"][0]["beta"] is None
    assert account["correlation_context_scope"] == ["AAPL"]
    assert account["correlation_context_omitted_holdings"] == ["MSFT"]
    assert (
        account["current_risk"]["position_weights"]
        == source.portfolio_risk.current.position_weights
    )


@pytest.mark.asyncio
async def test_incomplete_current_risk_cannot_spend_a_model_call(monkeypatch):
    db, _, source, _ = await setup(monkeypatch, model_policy=ENABLED)
    stored = db.get_collection("decision_assessments").rows[source.assessment_id]
    stored["portfolio_risk"]["current"]["status"] = "unavailable"
    agent = Agent()
    with pytest.raises(control.ReviewConflict, match="SOURCE_ACCOUNT_RISK_UNAVAILABLE"):
        await model_decision.decide(db, agent, await request(db, source))
    assert agent.calls == 0


@pytest.mark.asyncio
async def test_new_acknowledgment_binds_allocator_and_legacy_policy_serializes_unchanged(
    monkeypatch,
):
    db, _, source, _ = await setup(monkeypatch)
    current = await control.read(db)
    old = policies.active(current)
    assert old.allocation_calculator is None
    assert "allocation_calculator" not in old.model_dump(mode="json")
    requested = old.policy.model_copy(
        update={"acknowledged_contract": "post-cost-target-paper-review@2"}
    )
    await policies.confirm(
        db,
        ConfirmReviewPolicy(
            expected_revision=current.revision,
            expected_generation=current.generation,
            request_id="post-cost-policy",
            confirm=True,
            policy=requested,
        ),
    )
    new = policies.active(await control.read(db))
    assert new.allocation_calculator == "post-cost-targets@1"
    assert context(source, new, ["AAPL"])[1]["target_equity_basis"] == "post_cost"
    with pytest.raises(ValidationError):
        ReviewPolicyVersion.model_validate(
            {
                **old.model_dump(mode="json"),
                "allocation_calculator": "post-cost-targets@1",
            }
        )
    assert (await control.read(db)).policies[0].version_id == old.version_id


def test_original_paid_review_hash_and_prompt_remain_verifiable_without_backfill():
    path = Path("../docs/features/assets/idq-009-a/live/run-report.json")
    report = json.loads(path.read_text(encoding="utf-8"))
    captured = next(c for c in report["results"] if c["case_id"] == "concentrated")
    batch = PreparedReview.model_validate(captured["review"]["batch"])
    assert review_storage.receipt_hash(batch) == batch.receipt_hash
    assert batch.model_decision.provenance.prompt == "portfolio-model-decision@1"
    assert batch.policy.allocation_calculator is None
    assert batch.risk.allocation.calculator_version == "idq-002@1"
    assert batch.risk.allocation.proposed.position_weights["AAPL"] > 0.3
