"""Model decides; the real review gate validates; approval never trades. Outer model stubbed."""

import asyncio
import copy

import pytest
from pydantic import ValidationError

from src.models.decision_review import RevisionRequest
from src.models.model_decision import ModelDecision, ModelDecisionSet
from src.services.decision_policy import (
    control,
    model_decision,
    model_review,
    review_service,
)
from src.services.decision_policy.model_decision import RequestModelDecision
from tests.review_fixtures import setup
from tests.test_review_gates import approval

ENABLED = {
    "model_decisions": "propose_for_human_review",
    "model_may_open": True,
    "model_may_exit": True,
    "model_acknowledgment": "model-proposes-code-validates-human-decides-no-trade",
}


class Agent:
    """Outer model transport stub: returns the model's structured output, counts calls."""

    def __init__(self, output=None, error=None, during=None):
        self.calls, self.prompts = 0, []
        self.output, self.error, self.during = output, error, during
        self.react_agent = self

    async def ainvoke_structured(self, prompt, schema, context=None):
        self.calls += 1
        self.prompts.append(prompt)
        assert schema is ModelDecisionSet
        if self.during:
            await self.during()
        if self.error:
            raise self.error
        return self.output


def evidence(snaps, symbol, metric="eps"):
    return [next(r.evidence_id for r in snaps[symbol].records if r.metric == metric)]


def decisions(snaps, **actions):
    rows = []
    for symbol, (action, weight) in actions.items():
        rows.append(
            ModelDecision(
                symbol=symbol,
                action=action,
                target_weight=weight,
                rationale="Recorded conditional rationale",
                evidence_ids=evidence(snaps, symbol),
                key_risks=["Growth slows"],
                review_triggers=["EPS decline"],
            )
        )
    return ModelDecisionSet(decisions=rows, portfolio_summary="Recorded summary")


async def request(db, source, identifier="model-request"):
    state = await control.read(db)
    return RequestModelDecision(
        expected_revision=state.revision,
        expected_generation=state.generation,
        request_id=identifier,
        assessment_id=source.assessment_id,
        confirm=True,
        acknowledgment="uses-model-allowance-recommendation-only-no-trade",
    )


async def ready_case(monkeypatch, **kwargs):
    db, _, source, snaps = await setup(monkeypatch, model_policy=ENABLED, **kwargs)
    return db, source, snaps


@pytest.mark.asyncio
async def test_model_decision_becomes_ready_for_human_approval_without_trading(
    monkeypatch,
):
    db, source, snaps = await ready_case(monkeypatch)
    ledger = {
        n: copy.deepcopy(db.get_collection(n).rows)
        for n in ("holdings", "user_settings", "user_transactions")
    }
    agent = Agent(decisions(snaps, AAPL=("ADD", 0.2), MSFT=("HOLD", None)))
    body = await request(db, source)
    view = await model_decision.decide(db, agent, body)
    assert agent.calls == 1 and view.record.status == "completed"
    assert view.record.provenance.prompt == "portfolio-model-decision@1"
    assert "AAPL, MSFT" in agent.prompts[0] and "ev_" in agent.prompts[0]
    review = view.review
    assert review.readiness == "ready", review.reasons
    assert review.batch.model_decision.decision_id == view.record.decision_id
    assert [(t.symbol, t.delta_quantity) for t in review.batch.trades] == [
        ("AAPL", 10.0)
    ]
    approved = await review_service.approve(db, review.batch.batch_id, approval(review))
    assert approved.approval_current and not approved.executable
    assert approved.approval_receipt.evaluation.model_decision == view.record
    # Replay reuses the stored output and its published review; no second paid call.
    replay = await model_decision.decide(
        db,
        agent,
        body.model_copy(
            update={
                "expected_revision": approved.control_revision,
                "expected_generation": approved.control_generation,
            }
        ),
    )
    assert agent.calls == 1 and replay.review.batch.batch_id == review.batch.batch_id
    for name, rows in ledger.items():
        assert db.get_collection(name).rows == rows


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,code,severity",
    [
        ("missing", "MODEL_DECISION_SCOPE_MISMATCH", "blocked"),
        ("buy_held", "MODEL_ACTION_EXPOSURE_CONFLICT", "blocked"),
        ("add_flat", "MODEL_ACTION_EXPOSURE_CONFLICT", "blocked"),
        ("reduce_up", "MODEL_ACTION_DELTA_CONFLICT", "blocked"),
        ("wrong_evidence", "MODEL_EVIDENCE_UNVERIFIED", "insufficient_evidence"),
        ("no_open", "MODEL_NEW_POSITION_NOT_PERMITTED", "blocked"),
        ("bearish_add", "MODEL_ACTION_STANCE_CONFLICT", "needs_review"),
        ("below_lot", "MODEL_TARGET_BELOW_LOT", "research_only"),
    ],
)
async def test_invalid_model_decisions_are_shown_not_rewritten(
    monkeypatch, case, code, severity
):
    policy = dict(ENABLED, model_may_open=False) if case == "no_open" else ENABLED
    db, _, source, snaps = await setup(monkeypatch, model_policy=policy)
    output = {
        "missing": decisions(snaps, AAPL=("ADD", 0.2)),
        "buy_held": decisions(snaps, AAPL=("BUY", 0.2), MSFT=("HOLD", None)),
        "add_flat": decisions(snaps, AAPL=("HOLD", None), MSFT=("ADD", 0.1)),
        "reduce_up": decisions(snaps, AAPL=("REDUCE", 0.3), MSFT=("HOLD", None)),
        "wrong_evidence": decisions(snaps, AAPL=("ADD", 0.2), MSFT=("HOLD", None)),
        "no_open": decisions(snaps, AAPL=("HOLD", None), MSFT=("BUY", 0.1)),
        "bearish_add": decisions(snaps, AAPL=("ADD", 0.2), MSFT=("HOLD", None)),
        "below_lot": decisions(snaps, AAPL=("ADD", 0.1000001), MSFT=("HOLD", None)),
    }[case]
    if case == "wrong_evidence":
        output.decisions[0].evidence_ids = evidence(snaps, "MSFT")
    if case == "bearish_add":
        row = db.get_collection("decision_assessments").rows[source.assessment_id]
        row["strategy"]["reviews"][0]["conclusion"]["stance"] = "bearish"
    view = await model_decision.decide(db, Agent(output), await request(db, source))
    reasons = {(r.code, r.severity) for r in view.review.reasons}
    assert (code, severity) in reasons
    assert not view.review.approvable
    # The stored recommendation is kept verbatim; no silent resize/HOLD rewrite.
    assert view.record.output == output


@pytest.mark.asyncio
async def test_disabled_policy_and_ineligible_source_make_no_model_call(monkeypatch):
    db, _, source, _ = await setup(monkeypatch)
    agent = Agent()
    with pytest.raises(control.ReviewConflict, match="not enabled"):
        await model_decision.decide(db, agent, await request(db, source))
    db, _, source, _ = await setup(monkeypatch, model_policy=ENABLED)
    db.get_collection("agent_runs").rows["run"]["status"] = "cancelled"
    with pytest.raises(control.ReviewConflict, match="SOURCE_RUN_NOT_COMPLETED"):
        await model_decision.decide(db, agent, await request(db, source))
    assert agent.calls == 0 and not db.get_collection(model_decision.COLLECTION).rows


@pytest.mark.asyncio
async def test_failed_call_is_recorded_and_cannot_be_resumed(monkeypatch):
    db, source, _ = await ready_case(monkeypatch)
    body = await request(db, source)
    with pytest.raises(RuntimeError):
        await model_decision.decide(db, Agent(error=RuntimeError("upstream")), body)
    record = next(iter(db.get_collection(model_decision.COLLECTION).rows.values()))
    assert record["status"] == "failed" and record["error_code"] == "RuntimeError"
    agent = Agent()
    with pytest.raises(control.ReviewConflict, match="failed"):
        await model_decision.decide(db, agent, body)
    assert agent.calls == 0


@pytest.mark.asyncio
async def test_concurrent_same_request_makes_one_call(monkeypatch):
    db, source, snaps = await ready_case(monkeypatch)
    started, release = asyncio.Event(), asyncio.Event()

    async def wait():
        started.set()
        await release.wait()

    agent = Agent(decisions(snaps, AAPL=("ADD", 0.2), MSFT=("HOLD", None)), during=wait)
    body = await request(db, source)
    first = asyncio.create_task(model_decision.decide(db, agent, body))
    await started.wait()
    with pytest.raises(control.ReviewConflict, match="already running"):
        await model_decision.decide(db, agent, body)
    release.set()
    assert (await first).review.readiness == "ready" and agent.calls == 1
    with pytest.raises(control.ReviewConflict, match="different inputs"):
        await model_decision.decide(
            db,
            agent,
            body.model_copy(update={"assessment_id": "assessment_" + "0" * 32}),
        )


@pytest.mark.asyncio
async def test_input_change_during_call_needs_revalidation_without_another_call(
    monkeypatch,
):
    db, source, snaps = await ready_case(monkeypatch)

    async def edit_account():
        async with control.mutation(db):
            pass

    agent = Agent(
        decisions(snaps, AAPL=("ADD", 0.2), MSFT=("HOLD", None)), during=edit_account
    )
    view = await model_decision.decide(db, agent, await request(db, source))
    assert view.review is None and "reload" in view.review_error
    state = await control.read(db)
    again = await model_review.revalidate(
        db,
        view.record.decision_id,
        RevisionRequest(
            expected_revision=state.revision,
            expected_generation=state.generation,
            request_id="revalidate-1",
        ),
    )
    assert agent.calls == 1 and again.review.readiness == "ready"
    assert (await model_review.view(db, view.record.decision_id)).review == again.review


@pytest.mark.asyncio
async def test_all_hold_has_nothing_to_approve_and_subset_keeps_model_checks(
    monkeypatch,
):
    db, source, snaps = await ready_case(monkeypatch)
    hold = await model_decision.decide(
        db,
        Agent(decisions(snaps, AAPL=("HOLD", None), MSFT=("HOLD", None))),
        await request(db, source),
    )
    assert hold.review is None and "HOLD/WAIT" in hold.review_error
    both = decisions(snaps, AAPL=("REDUCE", 0.05), MSFT=("BUY", 0.1))
    view = await model_decision.decide(
        db, Agent(both), await request(db, source, "model-request-2")
    )
    assert view.review.approvable, view.review.reasons
    subset = await review_service.approve(
        db, view.review.batch.batch_id, approval(view.review, symbols=["MSFT"])
    )
    evaluated = subset.approval_receipt.evaluation
    assert [t.symbol for t in evaluated.request.targets] == ["MSFT"]
    assert evaluated.model_decision.decision_id == view.record.decision_id


@pytest.mark.parametrize(
    "data",
    [
        {"action": "HOLD", "target_weight": 0.1},
        {"action": "SELL", "target_weight": 0.5},
        {"action": "ADD", "target_weight": None},
        {"action": "REDUCE", "target_weight": 0.0},
        {"action": "BUY", "target_weight": float("nan")},
        {"action": "BUY", "target_weight": 1.5},
        {"action": "BUY", "target_weight": 0.1, "quantity": 3},
        {"action": "BUY", "target_weight": 0.1, "ready": True},
        {"action": "SHORT", "target_weight": 0.1},
    ],
)
def test_model_output_cannot_forge_authority_or_invalid_geometry(data):
    with pytest.raises(ValidationError):
        ModelDecision(symbol="AAPL", rationale="x", **data)


def test_model_permission_answers_are_required_only_when_enabled():
    from src.models.decision_review import ReviewPolicyInput

    fields = {
        "risk_policy_revision": 1,
        "strategy_version": "strategy_" + "a" * 64,
        "allowed_symbols": ["AAPL"],
        "max_account_sigma": 0.5,
        "lifetime_minutes": 60,
        "acknowledged_contract": "manual-target-paper-review@1",
        "instrument_attestation": "USD-US-nonfinancial-common-equities",
        "evidence_acknowledgment": "forward-close-not-truth-or-historical-PIT",
    }
    assert ReviewPolicyInput(**fields).model_decisions == "disabled"
    with pytest.raises(ValidationError):
        ReviewPolicyInput(**fields, model_decisions="propose_for_human_review")
    with pytest.raises(ValidationError):
        ReviewPolicyInput(**fields, model_may_open=True)
    assert ReviewPolicyInput(**fields, **ENABLED).model_may_exit is True
