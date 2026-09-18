"""CAS, preparation failure and subset races. No test replaces the readiness result."""

import asyncio
import copy
from unittest.mock import AsyncMock

import pytest

from src.database.repositories.holding_repository import HoldingRepository
from src.models.decision_review import ReconcileReview, RevisionRequest
from src.models.holding import HoldingUpdate
from src.services.decision_policy import (
    control,
    policies,
    review_service,
    review_storage,
)
from tests.review_fixtures import setup
from tests.test_review_gates import approval


@pytest.mark.asyncio
async def test_exact_subset_does_not_borrow_omitted_sale_cash_floor(monkeypatch):
    db, request, _, _ = await setup(
        monkeypatch,
        targets={"AAPL": 0.0, "MSFT": 0.8},
        limits={"min_cash_weight": 0.15},
    )
    view = await review_service.propose(db, request)
    assert view.approvable, view.reasons
    with pytest.raises(control.ReviewConflict, match="CASH_FLOOR"):
        await review_service.approve(
            db, view.batch.batch_id, approval(view, symbols=["MSFT"])
        )
    assert not (await control.read(db)).approvals
    accepted = await review_service.approve(
        db, view.batch.batch_id, approval(view, request_id="full-approval")
    )
    receipt = accepted.approval_receipt.evaluation.risk.allocation
    assert receipt.posttrade_cash == 2000.0
    assert receipt.cash_without_unfilled_sales == 1000.0
    assert {t.intent for t in accepted.batch.trades} == {"close_long", "open_long"}


@pytest.mark.asyncio
async def test_sell_proceeds_cannot_fund_buy_even_when_posttrade_cash_positive(
    monkeypatch,
):
    db, request, _, _ = await setup(
        monkeypatch, cash=1000.0, quantity=90.0, targets={"AAPL": 0.0, "MSFT": 0.5}
    )
    view = await review_service.propose(db, request)
    assert view.readiness == "blocked"
    assert "UNFILLED_SELL_PROCEEDS_REQUIRED" in {r.code for r in view.reasons}
    assert view.batch.risk.allocation.posttrade_cash == 5000.0


@pytest.mark.asyncio
async def test_monitoring_rejects_increase_but_does_not_automatically_create_exit(
    monkeypatch,
):
    db, request, _, _ = await setup(monkeypatch, prior_eps=8.0)
    view = await review_service.propose(db, request)
    assert not view.approvable
    assert "BUY_MONITORING_REQUIRES_REVIEW" in {r.code for r in view.reasons}
    assert view.batch.trades[0].action == "BUY"
    db, request, _, _ = await setup(monkeypatch, prior_eps=8.0, targets={"AAPL": 0.0})
    reduced = await review_service.propose(db, request)
    assert reduced.approvable, reduced.reasons
    assert reduced.batch.trades[0].intent == "close_long"


@pytest.mark.asyncio
async def test_peer_pe_only_is_not_forced_into_a_second_valuation_method(monkeypatch):
    db, request, _, _ = await setup(
        monkeypatch, parameter_changes={"methods": ["peer_pe_annual@1"]}
    )
    view = await review_service.propose(db, request)
    assert view.approvable, view.reasons
    assert view.batch.proofs[0].monitoring["debt_to_fcf"] == "not_triggered"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["propose", "approve"])
@pytest.mark.parametrize(
    "change", ["account", "risk_policy", "review_policy", "strategy"]
)
async def test_input_change_after_preparation_cannot_cross_final_cas(
    monkeypatch, operation, change
):
    db, request, _, _ = await setup(monkeypatch)
    view = await review_service.propose(db, request) if operation == "approve" else None
    original = review_storage.save

    async def racing_save(db, collection, identifier, value):
        saved = await original(db, collection, identifier, value)
        if change == "account":
            holdings = HoldingRepository(db.get_collection("holdings"))
            holding = (await holdings.list_by_user())[0]
            await holdings.update(holding.holding_id, HoldingUpdate(quantity=11.0))
        elif change == "risk_policy":
            from src.services.portfolio_risk import service as risk

            state = await risk.policy_state(db)
            await risk.confirm_policy(db, state.policy, state.revision)
        elif change == "strategy":
            from src.services.research_strategy import store

            await store.deactivate(db, (await store.state(db)).revision)
        else:
            state = await control.read(db)
            await policies.deactivate(
                db,
                RevisionRequest(
                    expected_revision=state.revision,
                    expected_generation=state.generation,
                    request_id="deactivate-during-publication",
                ),
            )
        return saved

    monkeypatch.setattr(review_storage, "save", racing_save)
    with pytest.raises(control.ReviewConflict, match="Concurrent input/review"):
        if view:
            await review_service.approve(db, view.batch.batch_id, approval(view))
        else:
            await review_service.propose(db, request)
    current = await control.read(db)
    assert not current.approvals
    assert len(current.published) == int(view is not None)
    if view is None:
        with pytest.raises(control.ReviewConflict, match="Unpublished"):
            await review_service.propose(db, request)
        orphan = next(iter(db.get_collection(review_storage.BATCHES).rows.values()))
        assert not (await review_service.get(db, orphan["batch_id"])).approvable


@pytest.mark.asyncio
async def test_cancel_after_approval_preparation_wins_the_atomic_boundary(monkeypatch):
    db, request, _, _ = await setup(monkeypatch)
    view = await review_service.propose(db, request)
    original = review_storage.save

    async def cancelled_save(db, collection, identifier, value):
        saved = await original(db, collection, identifier, value)
        await review_service.cancel(
            db,
            view.batch.batch_id,
            RevisionRequest(
                expected_revision=view.control_revision,
                expected_generation=view.control_generation,
                request_id="cancel-during-approval",
            ),
        )
        return saved

    monkeypatch.setattr(review_storage, "save", cancelled_save)
    with pytest.raises(control.ReviewConflict):
        await review_service.approve(db, view.batch.batch_id, approval(view))
    result = await review_service.get(db, view.batch.batch_id)
    assert result.lifecycle == "cancelled" and result.approval is None
    assert not result.approvable


@pytest.mark.asyncio
async def test_parallel_approvals_have_one_authoritative_event(monkeypatch):
    db, request, _, _ = await setup(monkeypatch)
    view = await review_service.propose(db, request)
    results = await asyncio.gather(
        *[
            review_service.approve(
                db, view.batch.batch_id, approval(view, request_id=f"approval-{i}")
            )
            for i in range(5)
        ],
        return_exceptions=True,
    )
    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert len((await control.read(db)).approvals) == 1
    assert all(
        not isinstance(r, Exception) or isinstance(r, control.ReviewConflict)
        for r in results
    )


@pytest.mark.asyncio
async def test_preparation_failure_does_not_publish_ready_or_approval(monkeypatch):
    db, request, _, _ = await setup(monkeypatch)
    db.get_collection(review_storage.BATCHES).find_one_and_update = AsyncMock(
        side_effect=RuntimeError("disk unavailable")
    )
    with pytest.raises(RuntimeError, match="disk unavailable"):
        await review_service.propose(db, request)
    state = await control.read(db)
    assert state.current is None and not state.published and not state.approvals


@pytest.mark.asyncio
async def test_nested_and_failed_mutations_pause_review_not_bookkeeping(monkeypatch):
    db, request, _, _ = await setup(monkeypatch)
    initial = await control.read(db)
    async with control.mutation(db):
        during = await control.read(db)
        assert during.revision == initial.revision + 1 and len(during.mutations) == 1
        async with control.mutation(db):
            assert (await control.read(db)) == during
        with pytest.raises(control.ReviewConflict):
            await review_service.propose(db, request)
    with pytest.raises(RuntimeError):
        async with control.mutation(db):
            raise RuntimeError("partial ledger failure")
    failed = await control.read(db)
    assert failed.uncertain and not failed.mutations
    # No AI/policy readiness guard blocks independent actual-trade bookkeeping.
    repository = HoldingRepository(db.get_collection("holdings"))
    row = (await repository.list_by_user())[0]
    await repository.update(row.holding_id, HoldingUpdate(quantity=11.0))
    state = await policies.settings(db)
    assert state.uncertain
    body = ReconcileReview(
        expected_revision=state.revision,
        expected_generation=state.generation,
        request_id="reconcile-request",
        account_revision=state.account_revision,
        acknowledgment="declared-account-inspected-no-writers-in-flight",
    )
    unchanged = copy.deepcopy(db.get_collection("holdings").rows)
    assert not (await policies.reconcile(db, body)).uncertain
    revision = (await control.read(db)).revision
    assert not (await policies.reconcile(db, body)).uncertain
    assert (await control.read(db)).revision == revision
    assert db.get_collection("holdings").rows == unchanged
