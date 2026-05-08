"""W1.13 integration test — Phase2 ValidationError stops bad orders.

End-to-end safety check: even if a future LLM provider, prompt drift,
or schema-bypass returns a CRWV-style payload (close_long with stop
above entry), the geometry validator added in W1.1 must raise
ValidationError BEFORE the order touches the repository. The W1.1
unit tests cover the validator itself; this integration test covers
the failure mode at the seam between Phase2 output and persistence.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models.trading_decision import (
    OrderIntent,
    PortfolioDecisionList,
    TradingDecision,
)


def _make_invalid_crwv_decision() -> dict:
    """Raw dict mirroring the historical CRWV bug from 2026-05-07."""
    return {
        "symbol": "CRWV",
        "decision": "SELL",
        "position_size_percent": 50,
        "swap_from_symbol": None,
        "confidence": 7,
        "entry_price": 138.0,
        "stop_loss": 142.0,  # above entry = open_short geometry
        "take_profit": 122.0,
        "reasoning_summary": "Closing half of long.",
    }


def _make_valid_close_long_decision() -> dict:
    return {
        "symbol": "TSLA",
        "decision": "SELL",
        "position_size_percent": 30,
        "swap_from_symbol": None,
        "confidence": 8,
        "entry_price": 278.0,
        "stop_loss": 260.0,  # below entry = correct close_long
        "take_profit": 295.0,
        "reasoning_summary": "Trim 30% at recovery $278.",
    }


def test_phase2_payload_with_crwv_geometry_raises_validationerror() -> None:
    """When LLM tries to return the CRWV-style payload, the model layer
    rejects it before any persistence call runs."""
    raw = {
        "decisions": [_make_invalid_crwv_decision()],
        "portfolio_assessment": "test",
    }
    with pytest.raises(ValidationError) as exc:
        PortfolioDecisionList.model_validate(raw)

    msg = str(exc.value)
    assert "close_long" in msg
    assert "stop_loss > entry_price" not in msg  # we want the LONG-side error
    assert "stop_loss < entry_price" in msg


def test_phase2_payload_with_clean_close_long_passes() -> None:
    raw = {
        "decisions": [_make_valid_close_long_decision()],
        "portfolio_assessment": "test",
    }
    parsed = PortfolioDecisionList.model_validate(raw)
    assert parsed.decisions[0].intent == OrderIntent.CLOSE_LONG


def test_phase2_payload_mixed_one_bad_one_good_rejects_whole_batch() -> None:
    """If ANY decision is invalid, the entire structured output fails to
    parse. This is the desired blast radius — Phase2 must re-emit a
    fully clean batch rather than a half-good list that's hard to
    reconcile downstream."""
    raw = {
        "decisions": [
            _make_valid_close_long_decision(),
            _make_invalid_crwv_decision(),
        ],
        "portfolio_assessment": "test",
    }
    with pytest.raises(ValidationError):
        PortfolioDecisionList.model_validate(raw)


def test_explicit_open_short_with_short_geometry_passes() -> None:
    """The escape hatch: if the LLM means a real short trade, it must
    set intent=open_short explicitly. Then the short-side geometry
    (stop > entry > target) is valid."""
    raw_dec = _make_invalid_crwv_decision()
    raw_dec["intent"] = "open_short"
    parsed = TradingDecision.model_validate(raw_dec)
    assert parsed.intent == OrderIntent.OPEN_SHORT
