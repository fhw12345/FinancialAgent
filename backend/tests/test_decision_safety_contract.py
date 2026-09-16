import math
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from src.models.decision_assessment import DecisionAssessment, DraftProposal
from src.services.decision_policy.builder import build_assessment
from src.database.repositories.decision_assessment_repository import (
    DecisionWriteRejected,
)
from src.database.repositories.portfolio_order_repository import (
    PortfolioOrderRepository,
)
from src.models.trading_decision import TradingDecision


def inputs(**kwargs):
    return {
        "request_key": "run_one",
        "source": "holdings",
        "symbols": ["AAPL"],
        "proposals": [],
        **kwargs,
    }


def test_empty_buy_is_legacy_readable_but_not_a_valid_new_draft():
    old = TradingDecision(
        symbol="AAPL", decision="BUY", confidence=8, reasoning_summary="Old record"
    )
    result = build_assessment(**inputs(proposals=[old.model_dump()]))
    assert (
        result.readiness == "blocked"
        and result.action is None
        and not result.actionable
    )
    assert "INVALID_PROPOSAL" in {r.code for r in result.results[0].reasons}
    with pytest.raises(ValidationError):
        DraftProposal(
            symbol="AAPL",
            proposed_action="BUY",
            intent="open_long",
            reasoning="Missing all prices",
        )


def test_complete_research_still_cannot_be_ready_in_stage_a():
    raw = {
        "symbol": "AAPL",
        "decision": "BUY",
        "position_size_percent": 10,
        "entry_price": 100,
        "stop_loss": 95,
        "take_profit": 110,
        "reasoning_summary": "A research draft",
    }
    report = build_assessment(
        **inputs(
            proposals=[raw],
            research={"AAPL": "Recorded research"},
            quotes={"AAPL": 100},
            holdings=[],
        )
    )
    assert report.readiness == "research_only" and not report.actionable
    assert report.results[0].proposal.proposed_action == "BUY"
    data = report.model_dump()
    data["readiness"] = "ready"
    with pytest.raises(ValidationError):
        DecisionAssessment.model_validate(data)
    data = report.model_dump()
    data["actionable"] = True
    with pytest.raises(ValidationError):
        DecisionAssessment.model_validate(data)


@pytest.mark.parametrize("value", [math.nan, math.inf, -1, 0])
def test_invalid_numeric_trade_drafts_are_blocked(value):
    raw = {
        "symbol": "AAPL",
        "decision": "BUY",
        "position_size_percent": 10,
        "entry_price": value,
        "stop_loss": 95,
        "take_profit": 110,
        "reasoning_summary": "Draft",
    }
    assert build_assessment(**inputs(proposals=[raw])).readiness == "blocked"


def test_unknown_symbol_and_duplicate_proposals_are_retained_as_blocked():
    raw = {
        "symbol": "MSFT",
        "decision": "HOLD",
        "reasoning_summary": "Outside requested universe",
    }
    report = build_assessment(**inputs(proposals=[raw, raw]))
    assert len(report.results) == 2 and report.readiness == "blocked"
    assert {"SYMBOL_NOT_AUTHORIZED", "DUPLICATE_PROPOSAL"} <= {
        r.code for r in report.results[1].reasons
    }


def test_missing_and_failed_checks_are_not_hold():
    missing = build_assessment(**inputs())
    assert (
        missing.readiness == "insufficient_evidence"
        and missing.results[0].proposal is None
    )
    failed = build_assessment(
        **inputs(
            research={"AAPL": "Research"}, quality={"AAPL": {"check_unavailable": True}}
        )
    )
    assert failed.readiness == "needs_review" and failed.action is None


def valid_draft(**changes):
    return {
        "symbol": "AAPL",
        "decision": "BUY",
        "position_size_percent": 10,
        "entry_price": 100,
        "stop_loss": 90,
        "take_profit": 120,
        "reasoning_summary": "Recorded draft",
        **changes,
    }


@pytest.mark.parametrize(
    "change",
    [
        {"intent": "open_short"},
        {"position_size_percent": 101},
        {"position_size_percent": "10"},
        {"stop_loss": 100},
        {"take_profit": 99},
        {"decision": "HOLD"},
        {"readiness": "ready"},
        {"approved": True},
        {"actionable": True},
        {"ready": True},
    ],
)
def test_unsupported_geometry_intents_and_forged_model_authority(change):
    report = build_assessment(
        **inputs(proposals=[valid_draft(**change)], research={"AAPL": "Research"})
    )
    assert report.readiness == "blocked"
    assert "INVALID_PROPOSAL" in {r.code for r in report.results[0].reasons}


@pytest.mark.parametrize("held", [None, [], ["MSFT"]])
def test_sell_cannot_invent_a_long_holding(held):
    report = build_assessment(
        **inputs(proposals=[valid_draft(decision="SELL")], holdings=held)
    )
    assert report.readiness == "blocked"
    assert "UNSUPPORTED_EXPOSURE" in {r.code for r in report.results[0].reasons}


def test_valid_sell_and_hold_remain_only_untrusted_research():
    sell = build_assessment(
        **inputs(
            proposals=[valid_draft(decision="SELL")],
            holdings=["AAPL"],
            research={"AAPL": "Research"},
        )
    )
    assert sell.readiness == "research_only" and sell.action is None
    hold = build_assessment(
        **inputs(
            proposals=[
                {
                    "symbol": "AAPL",
                    "decision": "HOLD",
                    "reasoning_summary": "Wait for evidence",
                }
            ],
            holdings=[],
            research={"AAPL": "Research"},
        )
    )
    assert (
        hold.readiness == "research_only" and hold.results[0].exposure_context == "flat"
    )
    assert hold.results[0].proposal.entry is None and hold.action is None
    with pytest.raises(ValidationError):
        DraftProposal(
            symbol="AAPL",
            proposed_action="HOLD",
            intent="hold",
            reasoning="Research",
            approved=True,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["create", "upsert", "create_many", "mark_filled"])
async def test_old_ai_write_paths_cannot_bypass_containment(method):
    repo = PortfolioOrderRepository(MagicMock())
    with pytest.raises(DecisionWriteRejected):
        if method == "create_many":
            await repo.create_many([MagicMock()])
        elif method == "mark_filled":
            await repo.mark_filled("order", 1, 100, None, None)
        else:
            await getattr(repo, method)(MagicMock())
    repo.collection.insert_one.assert_not_called()
    repo.collection.find_one_and_update.assert_not_called()
