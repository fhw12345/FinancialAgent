"""Whole-batch authority and stable terminal runs remain separate from individual sizing."""

from datetime import UTC, date, datetime

import pytest

from src.database.repositories.agent_run_repository import AgentRunRepository
from src.services.decision_policy import control, review_service
from src.services.portfolio_risk.calendar import next_close
from tests.review_fixtures import setup
from tests.test_review_gates import approval


@pytest.mark.asyncio
async def test_individually_affordable_buys_cannot_be_partially_approved_from_blocked_batch(
    monkeypatch,
):
    db, request, _, _ = await setup(monkeypatch, targets={"AAPL": 0.6, "MSFT": 0.6})
    view = await review_service.propose(db, request)
    assert view.readiness == "blocked"
    assert "CASH_INSUFFICIENT_AFTER_COSTS" in {r.code for r in view.reasons}
    with pytest.raises(control.ReviewConflict, match="not currently ready"):
        await review_service.approve(
            db, view.batch.batch_id, approval(view, symbols=["AAPL"])
        )
    assert not (await control.read(db)).approvals


@pytest.mark.asyncio
async def test_completed_source_status_cannot_be_overridden_outside_legal_transitions(
    monkeypatch,
):
    db, _, _, _ = await setup(monkeypatch)
    repository = AgentRunRepository(db.get_collection("agent_runs"))
    with pytest.raises(ValueError, match="legal transition"):
        await repository.update_fields("run", status="failed")
    with pytest.raises(ValueError, match="override"):
        await repository.transition(
            "run", from_statuses=["running"], to_status="completed", status="failed"
        )
    assert (
        await repository.transition(
            "run", from_statuses=["completed"], to_status="running"
        )
        is None
    )
    assert db.get_collection("agent_runs").rows["run"]["status"] == "completed"


def test_expiry_boundary_uses_next_actual_session_close_including_holiday_and_early_close():
    assert next_close(date(2026, 11, 25)) == datetime(2026, 11, 27, 18, tzinfo=UTC)
