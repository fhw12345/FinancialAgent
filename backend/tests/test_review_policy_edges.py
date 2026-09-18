"""Policy ownership, freshness, hash integrity and exact numeric boundary regressions."""

from datetime import timedelta
import math

import pytest
from pydantic import ValidationError

from src.models.decision_review import (
    ConfirmReviewPolicy,
    ReviewPolicyInput,
    RevisionRequest,
    ReviewTarget,
)
from src.services.decision_policy import (
    control,
    policies,
    review_service,
    review_storage,
)
from src.services.portfolio_risk import service as risk
from src.services.research_strategy.calculators import fcff_proxy, debt_to_fcff
from tests.evidence_fixtures import Database
from tests.review_fixtures import NOW, setup
from tests.strategy_fixtures import value
from tests.test_review_gates import approval


def confirm_request(state, policy, identifier="policy-next"):
    return ConfirmReviewPolicy(
        expected_revision=state.revision,
        expected_generation=state.generation,
        request_id=identifier,
        confirm=True,
        policy=policy,
    )


@pytest.mark.asyncio
async def test_empty_state_is_unconfirmed_and_no_personal_defaults():
    result = await policies.settings(Database())
    assert result.policy is None and result.strategy_version is None
    assert result.risk_policy_revision == 0 and result.versions == []
    assert result.reasons == ["REVIEW_POLICY_UNCONFIRMED"]


@pytest.mark.asyncio
async def test_policy_replay_does_not_resurrect_deactivation_or_mutate_inputs(
    monkeypatch,
):
    db, _, _, _ = await setup(monkeypatch)
    current = await control.read(db)
    original = current.policies[0]
    replay = ConfirmReviewPolicy(
        expected_revision=original.revision - 1,
        expected_generation=0,
        request_id=original.request_id,
        confirm=True,
        policy=original.policy,
    )
    assert (await policies.confirm(db, replay)).policy.version_id == original.version_id
    with pytest.raises(control.ReviewConflict, match="different inputs"):
        await policies.confirm(
            db,
            replay.model_copy(
                update={
                    "policy": original.policy.model_copy(
                        update={"lifetime_minutes": 30}
                    )
                }
            ),
        )
    disabled = RevisionRequest(
        expected_revision=current.revision,
        expected_generation=current.generation,
        request_id="disable-review",
    )
    assert (await policies.deactivate(db, disabled)).policy is None
    assert (await policies.deactivate(db, disabled)).policy is None
    assert (await policies.confirm(db, replay)).policy is None
    assert len((await control.read(db)).policies) == 1
    with pytest.raises(control.ReviewConflict, match="different inputs"):
        await policies.deactivate(
            db, disabled.model_copy(update={"expected_revision": 99})
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["cost", "strategy", "peer"])
async def test_confirmation_requires_matching_bound_costs_strategy_and_attested_peers(
    monkeypatch, change
):
    db, _, _, _ = await setup(monkeypatch)
    current = await control.read(db)
    updates = {
        "cost": {"risk_policy_revision": 99},
        "strategy": {"strategy_version": "strategy_" + "f" * 64},
        "peer": {"allowed_symbols": ["AAPL"]},
    }
    policy = current.policies[0].policy.model_copy(update=updates[change])
    with pytest.raises(control.ReviewConflict, match="matching risk/cost"):
        await policies.confirm(db, confirm_request(current, policy))
    assert (await control.read(db)) == current


@pytest.mark.asyncio
async def test_sigma_limit_equality_and_just_over_are_not_confidence_sizing(
    monkeypatch,
):
    db, request, _, _ = await setup(monkeypatch)
    original = await review_service.propose(db, request)
    sigma = original.batch.risk.allocation.proposed.account_sigma_annualized
    for index, limit in enumerate((sigma, math.nextafter(sigma, 0.0))):
        state = await control.read(db)
        await policies.confirm(
            db,
            confirm_request(
                state,
                state.policies[-1].policy.model_copy(
                    update={"max_account_sigma": limit}
                ),
                f"sigma-policy-{index}",
            ),
        )
        state = await control.read(db)
        result = await review_service.propose(
            db,
            request.model_copy(
                update={
                    "expected_revision": state.revision,
                    "expected_generation": state.generation,
                    "request_id": f"sigma-proposal-{index}",
                }
            ),
        )
        assert result.approvable is (index == 0)
        if index:
            assert "ACCOUNT_SIGMA_LIMIT" in {r.code for r in result.reasons}
        assert result.batch.trades[0].delta_quantity == 10.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target,readiness,intent,delta",
    [
        (0.155, "ready", "add_long", 5.5),
        (0.05, "ready", "reduce_long", -5.0),
        (0.1, "research_only", "hold", 0.0),
    ],
)
async def test_fractional_target_and_held_hold_are_not_execution_geometry(
    monkeypatch, target, readiness, intent, delta
):
    db, request, _, _ = await setup(monkeypatch, targets={"AAPL": target})
    view = await review_service.propose(db, request)
    assert view.readiness == readiness
    assert view.batch.trades[0].intent == intent
    assert view.batch.trades[0].delta_quantity == delta
    assert view.batch.trades[0].execution_price is None


@pytest.mark.asyncio
async def test_expiry_after_preparation_is_rejected_by_atomic_storage_clock(
    monkeypatch,
):
    db, request, _, _ = await setup(monkeypatch)
    view = await review_service.propose(db, request)
    original = review_storage.save

    async def slow_storage(db, name, identifier, value):
        result = await original(db, name, identifier, value)
        # Application clock still says valid. Only the final atomic storage
        # deadline can reject a write delayed past expiry.
        db.now = NOW + timedelta(hours=2)
        return result

    monkeypatch.setattr(review_storage, "save", slow_storage)
    with pytest.raises(control.ReviewConflict, match="expired lifetime"):
        await review_service.approve(db, view.batch.batch_id, approval(view))
    assert not (await control.read(db)).approvals


@pytest.mark.asyncio
async def test_history_supersession_and_sealed_receipt_tampering_are_not_approval(
    monkeypatch,
):
    db, request, _, _ = await setup(monkeypatch)
    first = await review_service.propose(db, request)
    current = await control.read(db)
    second = await review_service.propose(
        db,
        request.model_copy(
            update={
                "expected_generation": current.generation,
                "request_id": "replacement-review",
            }
        ),
    )
    assert second.approvable
    history = await review_service.recent(db)
    assert [v.lifecycle for v in history] == ["current", "superseded"]
    assert not history[1].approvable
    db.get_collection(review_storage.BATCHES).rows[first.batch.batch_id]["trades"][0][
        "delta_quantity"
    ] = 999.0
    with pytest.raises(control.ReviewConflict, match="hash mismatch"):
        await review_service.get(db, first.batch.batch_id)


@pytest.mark.asyncio
async def test_unconfirmed_or_changed_policy_does_not_make_provider_calls_for_readiness(
    monkeypatch,
):
    db, request, _, _ = await setup(monkeypatch)
    db.get_collection(control.COLLECTION).rows["local"]["active_policy"] = None
    risk.provider.fetch_asset.reset_mock()
    view = await review_service.propose(db, request)
    assert not view.approvable
    assert "REVIEW_POLICY_UNCONFIRMED" in {r.code for r in view.reasons}
    risk.provider.fetch_asset.assert_not_awaited()


@pytest.mark.asyncio
async def test_finite_statement_overflow_is_unavailable_not_zero_debt_risk(monkeypatch):
    db, request, _, _ = await setup(
        monkeypatch,
        parameter_changes={"methods": ["peer_pe_annual@1"], "tax_rate": 0.0},
        financial_changes={
            "operating_cash_flow": 1e308,
            "interest_expense": 1e308,
            "capital_expenditure": 0.0,
        },
    )
    view = await review_service.propose(db, request)
    assert not view.approvable
    assert view.batch.proofs[0].monitoring["debt_to_fcf"] == "unavailable"
    assert "BUY_MONITORING_REQUIRES_REVIEW" in {r.code for r in view.reasons}
    with pytest.raises(ValueError, match="NONFINITE"):
        fcff_proxy(
            value("operating_cash_flow", 1e308),
            value("capital_expenditure", 0),
            value("interest_expense", 1e308),
            0.0,
        )


def test_fcff_monitoring_rejects_sign_period_and_nonpositive_denominator():
    cfo, capex, interest = (
        value("operating_cash_flow", 150),
        value("capital_expenditure", 50),
        value("interest_expense", 10),
    )
    debt, cash = value("total_debt", 100), value("cash", 20)
    assert debt_to_fcff(cfo, capex, interest, debt, cash, 0.2) == pytest.approx(
        80 / 108
    )
    for bad_capex, bad_interest, tax in [
        (capex.model_copy(update={"value": -1.0}), interest, 0.2),
        (capex, interest, 1.1),
    ]:
        with pytest.raises(ValueError):
            fcff_proxy(cfo, bad_capex, bad_interest, tax)
    with pytest.raises(ValueError, match="ANNUAL"):
        fcff_proxy(cfo.model_copy(update={"period": "quarter"}), capex, interest, 0.2)
    with pytest.raises(ValueError, match="INVALID_DEBT"):
        debt_to_fcff(
            cfo, capex, interest, debt.model_copy(update={"value": -1.0}), cash, 0.2
        )
    with pytest.raises(ValueError, match="NONPOSITIVE"):
        debt_to_fcff(
            cfo.model_copy(update={"value": 1.0}), capex, interest, debt, cash, 0.2
        )


@pytest.mark.asyncio
async def test_confirmation_flags_duplicates_and_extra_authority_are_rejected(
    monkeypatch,
):
    db, request, _, _ = await setup(monkeypatch)
    state = await control.read(db)
    policy = state.policies[0].policy
    for confirmation in (False, 1, "true"):
        data = confirm_request(state, policy).model_dump()
        data["confirm"] = confirmation
        with pytest.raises(ValidationError):
            ConfirmReviewPolicy.model_validate(data)
    with pytest.raises(ValidationError):
        ReviewPolicyInput.model_validate(
            {**policy.model_dump(), "allowed_symbols": ["AAPL", "AAPL"]}
        )
    view = await review_service.propose(db, request)
    with pytest.raises(ValidationError):
        approval(view, symbols=["AAPL", "AAPL"])
    with pytest.raises(ValidationError):
        ReviewTarget(symbol="AAPL", target_weight=0.2, quantity=2)
