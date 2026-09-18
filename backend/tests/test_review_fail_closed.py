"""Critical negatives: unavailable inputs, corrupted preparations and mutation fences."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import DuplicateKeyError

from src.models.decision_review import RevisionRequest, ReviewTarget
from src.services.decision_policy import (
    control,
    evidence_gate,
    policies,
    review_service,
    review_storage,
)
from src.services.portfolio_risk import service as risk
from tests.evidence_fixtures import Database
from tests.review_fixtures import NOW, setup
from tests.strategy_evidence_fixtures import save
from tests.test_review_gates import approval


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "defect,code",
    [
        ("absent", "SOURCE_ASSESSMENT_REQUIRED"),
        ("legacy", "CONFIRMED_STRATEGY_SOURCE_REQUIRED"),
        ("risk", "SOURCE_ACCOUNT_RISK_REQUIRED"),
        ("evidence", "SOURCE_EVIDENCE_UNVERIFIED"),
        ("universe", "TARGET_SYMBOL_NOT_AUTHORIZED"),
        ("cost", "RISK_POLICY_CHANGED"),
        ("expired", "PROPOSAL_EXPIRED"),
    ],
)
async def test_required_inputs_and_universe_are_not_inferred(monkeypatch, defect, code):
    db, request, source, _ = await setup(monkeypatch)
    stored = db.get_collection("decision_assessments").rows[source.assessment_id]
    if defect == "absent":
        db.get_collection("decision_assessments").rows.clear()
    elif defect == "legacy":
        stored["strategy"] = None
        stored["legacy_strategy"] = True
    elif defect == "risk":
        stored["portfolio_risk"] = None
    elif defect == "evidence":
        stored["evidence"]["errors"] = ["MATERIAL_CLAIM_UNVERIFIED"]
    elif defect == "universe":
        request.targets = [ReviewTarget(symbol="NVDA", target_weight=0.2)]
    elif defect == "cost":
        await risk.confirm_policy(db, (await risk.policy_state(db)).policy, 1)
        request.expected_revision = (await control.read(db)).revision
        assert "RISK_POLICY_CHANGED" in (await policies.settings(db)).reasons
    else:
        stored["created_at"] = NOW - timedelta(hours=2)
    view = await review_service.propose(db, request)
    assert not view.approvable and view.readiness != "ready"
    assert code in {r.code for r in view.reasons}
    assert not (await control.read(db)).approvals


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "defect,code",
    [
        ("review", "SOURCE_SYMBOL_SCOPE_MISMATCH"),
        ("scope", "SEALED_SOURCE_SCOPE_MISMATCH"),
        ("dossier", "REPORT_DOSSIER_MISMATCH"),
        ("claims", "STRUCTURED_CLAIMS_UNVERIFIED"),
        ("peer", "PEER_INPUT_SCOPE_MISMATCH"),
        ("age", "FINANCIAL_PERIOD_EXPIRED"),
    ],
)
async def test_sealed_membership_and_current_financial_age_revalidate(
    monkeypatch, defect, code
):
    db, _, source, snapshots = await setup(monkeypatch)
    now = NOW
    if defect == "review":
        source.strategy.reviews = []
    elif defect == "scope":
        source.strategy.reviews[0].snapshot_id = "snapshot_MSFT"
    elif defect == "dossier":
        source.evidence.dossier_ids = []
    elif defect == "claims":
        row = next(
            r
            for r in db.get_collection("research_dossiers").rows.values()
            if r["symbol"] == "AAPL"
        )
        row["claims"] = []
    elif defect == "peer":
        snapshots["MSFT"].risk_snapshot_id = "wrong-account-capture"
        save(db, snapshots["MSFT"])
    else:
        now += timedelta(days=400)
    _, reasons, _ = await evidence_gate.validate(
        db, source, "AAPL", policies.active(await control.read(db)), now
    )
    assert code in {r.code for r in reasons}


@pytest.mark.asyncio
async def test_missing_and_changed_storage_receipts_cannot_attest_success(monkeypatch):
    db, request, _, _ = await setup(monkeypatch)
    view = await review_service.propose(db, request)
    broken = view.batch.model_copy(update={"receipt_hash": "wrong"})
    with pytest.raises(control.ReviewConflict, match="hash mismatch"):
        await review_storage.save(db, review_storage.BATCHES, broken.batch_id, broken)
    changed = view.batch.model_copy(update={"created_at": NOW + timedelta(seconds=1)})
    changed.receipt_hash = review_storage.receipt_hash(changed)
    with pytest.raises(control.ReviewConflict, match="different preparation"):
        await review_storage.save(db, review_storage.BATCHES, changed.batch_id, changed)
    collection = db.get_collection(review_storage.BATCHES)
    collection.find_one_and_update = AsyncMock(
        side_effect=DuplicateKeyError("first-writer race")
    )
    assert (
        await review_storage.save(
            db, review_storage.BATCHES, view.batch.batch_id, view.batch
        )
        == view.batch
    )
    collection.find_one_and_update = AsyncMock(return_value=None)
    with pytest.raises(RuntimeError, match="no record"):
        await review_storage.save(
            db, review_storage.BATCHES, view.batch.batch_id, view.batch
        )
    with pytest.raises(control.ReviewConflict, match="missing"):
        await review_storage.approval(db, "absent")
    accepted = await review_service.approve(db, view.batch.batch_id, approval(view))
    db.get_collection(review_storage.APPROVALS).rows[accepted.approval.approval_id][
        "receipt_hash"
    ] = "changed"
    with pytest.raises(control.ReviewConflict, match="hash mismatch"):
        await review_service.get(db, view.batch.batch_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("pointer", ["current", "published"])
async def test_control_pointer_cannot_attest_a_different_preparation(
    monkeypatch, pointer
):
    db, request, _, _ = await setup(monkeypatch)
    view = await review_service.propose(db, request)
    state = db.get_collection(control.COLLECTION).rows["local"]
    if pointer == "current":
        state["current"]["receipt_hash"] = "wrong"
    else:
        state["published"][0]["receipt_hash"] = "wrong"
    with pytest.raises(control.ReviewConflict, match="hash mismatch"):
        await review_service.get(db, view.batch.batch_id)


@pytest.mark.asyncio
async def test_inflight_and_uncertain_inputs_have_no_force_unlock():
    db = Database()
    assert (await control.read(db)).revision == 0
    async with control.mutation(db):
        current = await control.read(db)
        request = RevisionRequest(
            expected_revision=current.revision,
            expected_generation=0,
            request_id="current-input",
        )
        with pytest.raises(control.ReviewConflict, match="in flight"):
            control.check(current, request)
    current = await control.read(db)
    current.uncertain = True
    with pytest.raises(control.ReviewConflict, match="reconciliation"):
        control.check(
            current, request.model_copy(update={"expected_revision": current.revision})
        )
    collection = db.get_collection(control.COLLECTION)
    collection.update_one = AsyncMock(
        side_effect=DuplicateKeyError("existing aggregate")
    )
    await control.ensure(db)
    assert (await control.read(db)).revision == current.revision
    collection.update_one = AsyncMock(return_value=SimpleNamespace(modified_count=0))
    entered = False
    with pytest.raises(control.ReviewConflict, match="announcement"):
        async with control.mutation(db):
            entered = True
    assert not entered


@pytest.mark.asyncio
async def test_cancellation_during_ticket_cleanup_does_not_leave_a_clean_partial_write():
    db = Database()
    collection = db.get_collection(control.COLLECTION)
    write = collection.update_one
    finishing, release = asyncio.Event(), asyncio.Event()

    async def delayed(query, update, **kwargs):
        if "$unset" in update:
            finishing.set()
            await release.wait()
        return await write(query, update, **kwargs)

    collection.update_one = delayed

    async def worker():
        async with control.mutation(db):
            # Actual input work has completed; cancellation races only its cleanup.
            pass

    task = asyncio.create_task(worker())
    await finishing.wait()
    assert (await control.read(db)).mutations
    task.cancel()
    await asyncio.sleep(0)
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not (await control.read(db)).mutations
