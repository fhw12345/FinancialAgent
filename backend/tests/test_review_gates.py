"""Real deterministic review gates against synthetic outer inputs, no mocked eligibility."""

import copy

import pytest
from pydantic import ValidationError

from src.models.decision_review import (
    ApproveReview,
    ProposeReview,
    ReviewTarget,
    RevisionRequest,
)
from src.models.holding import HoldingUpdate
from src.database.repositories.holding_repository import HoldingRepository
from src.services.decision_policy import control, review_service
from tests.review_fixtures import setup


def approval(view, **changes):
    return ApproveReview(
        **{
            "expected_revision": view.control_revision,
            "expected_generation": view.control_generation,
            "request_id": "approval-request",
            "symbols": [t.symbol for t in view.batch.request.targets],
            "confirm": True,
            "acknowledgment": "review-only-no-real-or-paper-fill",
            **changes,
        }
    )


@pytest.mark.asyncio
async def test_ready_approval_replay_and_account_staleness_without_ledger_writes(
    monkeypatch,
):
    db, request, source, _ = await setup(monkeypatch)
    unchanged = {
        name: copy.deepcopy(db.get_collection(name).rows)
        for name in (
            "holdings",
            "user_settings",
            "user_transactions",
            "portfolio_orders",
            "transactions",
        )
    }
    view = await review_service.propose(db, request)
    assert view.readiness == "ready", view.reasons
    assert view.approvable and not view.executable
    assert view.batch.trades[0].action == "BUY"
    assert view.batch.trades[0].intent == "add_long"
    assert view.batch.trades[0].delta_quantity == 10.0
    assert source.actionable is False and source.action is None
    assert (await review_service.propose(db, request)).batch == view.batch
    body = approval(view)
    approved = await review_service.approve(db, view.batch.batch_id, body)
    assert approved.lifecycle == "approved" and approved.approval_current
    assert not approved.approvable and not approved.executable
    assert len((await control.read(db)).approvals) == 1
    assert (
        await review_service.approve(db, view.batch.batch_id, body)
    ).approval == approved.approval
    for name, rows in unchanged.items():
        assert db.get_collection(name).rows == rows
    holdings = HoldingRepository(db.get_collection("holdings"))
    row = (await holdings.list_by_user())[0]
    await holdings.update(row.holding_id, HoldingUpdate(quantity=11.0))
    stale = await review_service.get(db, view.batch.batch_id)
    assert not stale.approval_current and not stale.approvable
    assert {r.code for r in stale.reasons} >= {
        "INPUT_REVISION_CHANGED",
        "ACCOUNT_CHANGED",
    }
    assert (
        await review_service.approve(db, view.batch.batch_id, body)
    ).approval == approved.approval
    assert len((await control.read(db)).approvals) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "defect",
    ["consistency", "run", "dossier", "strategy", "coverage", "monitoring", "market"],
)
async def test_missing_or_changed_inputs_never_ready(monkeypatch, defect):
    db, request, source, snaps = await setup(monkeypatch)
    row = db.get_collection("decision_assessments").rows[source.assessment_id]
    if defect == "consistency":
        row["results"][0].pop("consistency_status")
    elif defect == "run":
        db.get_collection("agent_runs").rows["run"]["status"] = "cancelled"
    elif defect == "dossier":
        db.get_collection("research_dossiers").rows.clear()
    elif defect == "strategy":
        row["strategy"]["reviews"][0]["conclusion"] = None
    elif defect == "coverage":
        from tests.strategy_evidence_fixtures import save

        snaps["AAPL"].coverage["income_statement"] = "missing"
        save(db, snaps["AAPL"])
    elif defect == "monitoring":
        row["strategy"]["reviews"][0]["checks"][0]["status"] = "triggered"
    else:
        from tests.review_fixtures import market_asset
        from src.services.portfolio_risk import service as risk

        risk.provider.fetch_asset.side_effect = lambda symbol, session: market_asset(
            symbol
        ).model_copy(update={"mark": 101.0})
    view = await review_service.propose(db, request)
    assert view.readiness != "ready" and not view.approvable
    with pytest.raises(control.ReviewConflict):
        await review_service.approve(db, view.batch.batch_id, approval(view))
    assert not (await control.read(db)).approvals


@pytest.mark.asyncio
async def test_cancel_and_conflicting_replays_cannot_resurrect(monkeypatch):
    db, request, _, _ = await setup(monkeypatch)
    view = await review_service.propose(db, request)
    with pytest.raises(control.ReviewConflict, match="different inputs"):
        await review_service.propose(
            db,
            request.model_copy(
                update={"targets": [ReviewTarget(symbol="AAPL", target_weight=0.3)]}
            ),
        )
    cancel = RevisionRequest(
        expected_revision=view.control_revision,
        expected_generation=view.control_generation,
        request_id="cancel-request",
    )
    cancelled = await review_service.cancel(db, view.batch.batch_id, cancel)
    assert cancelled.lifecycle == "cancelled" and not cancelled.approvable
    assert (await review_service.propose(db, request)).lifecycle == "cancelled"
    assert (
        await review_service.cancel(db, view.batch.batch_id, cancel)
    ).lifecycle == "cancelled"
    with pytest.raises(control.ReviewConflict):
        await review_service.approve(db, view.batch.batch_id, approval(cancelled))


@pytest.mark.parametrize(
    "weight", [True, "0.1", float("nan"), float("inf"), -0.01, 1.01]
)
def test_target_numbers_are_strict_finite_fractions(weight):
    with pytest.raises(ValidationError):
        ReviewTarget(symbol="AAPL", target_weight=weight)


def test_client_cannot_submit_readiness_prices_or_duplicate_targets():
    with pytest.raises(ValidationError):
        ReviewTarget(symbol="AAPL", target_weight=0.1, ready=True)
    with pytest.raises(ValidationError):
        ReviewTarget(symbol="AAPL", target_weight=0.1, reference_price=1.0)
    with pytest.raises(ValidationError):
        ProposeReview(
            expected_revision=0,
            expected_generation=0,
            request_id="test-request",
            assessment_id="assessment_" + "a" * 32,
            targets=[ReviewTarget(symbol="AAPL", target_weight=0.1)] * 2,
        )
