"""W2.7+W2.8 unit tests — structured research blocks on TradingDecision.

All new fields are optional (back-compat); validators only run when a
field is provided. This file pins the contract.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models.trading_decision import (
    Catalyst,
    PriceTarget,
    ScenarioCase,
    ScenarioSet,
    TradingDecision,
    ValuationMethod,
)


def _base(**overrides):
    """Valid HOLD payload (zero geometry constraints)."""
    payload = {
        "symbol": "AAPL",
        "decision": "HOLD",
        "position_size_percent": None,
        "swap_from_symbol": None,
        "confidence": 7,
        "entry_price": None,
        "stop_loss": None,
        "take_profit": None,
        "reasoning_summary": "test",
    }
    payload.update(overrides)
    return TradingDecision(**payload)


# ---------------------------------------------------------------------------
# Backward compatibility: missing blocks parse fine
# ---------------------------------------------------------------------------


def test_decision_without_any_blocks_parses() -> None:
    d = _base()
    assert d.thesis is None
    assert d.valuation is None
    assert d.scenarios is None


# ---------------------------------------------------------------------------
# thesis
# ---------------------------------------------------------------------------


def test_thesis_three_bullets_accepted() -> None:
    d = _base(thesis=["a", "b", "c"])
    assert d.thesis == ["a", "b", "c"]


def test_thesis_two_bullets_rejected() -> None:
    with pytest.raises(ValidationError, match="exactly 3 bullet points"):
        _base(thesis=["a", "b"])


def test_thesis_four_bullets_rejected() -> None:
    with pytest.raises(ValidationError, match="exactly 3 bullet points"):
        _base(thesis=["a", "b", "c", "d"])


def test_thesis_empty_string_rejected() -> None:
    with pytest.raises(ValidationError, match="non-empty"):
        _base(thesis=["a", "  ", "c"])


# ---------------------------------------------------------------------------
# valuation
# ---------------------------------------------------------------------------


def test_valuation_two_methods_accepted() -> None:
    d = _base(
        valuation=[
            {"method": "pe_vs_peer", "value": 31.4, "note": "MAG7 median 28"},
            {"method": "ev_revenue", "value": 7.2, "note": "vs sector 5.5"},
        ]
    )
    assert len(d.valuation) == 2


def test_valuation_one_method_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 2 distinct methods"):
        _base(
            valuation=[{"method": "pe_vs_peer", "value": 31.4, "note": "x"}],
        )


def test_valuation_method_unknown_label_rejected() -> None:
    with pytest.raises(ValidationError):
        ValuationMethod(method="bogus_method", value=1.0, note="x")


# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------


def _scenarios(p_bull=0.3, p_base=0.5, p_bear=0.2):
    return {
        "bull": {"price_target": 350, "probability": p_bull, "rationale": "x"},
        "base": {"price_target": 300, "probability": p_base, "rationale": "x"},
        "bear": {"price_target": 250, "probability": p_bear, "rationale": "x"},
    }


def test_scenarios_prob_sum_one_accepted() -> None:
    d = _base(scenarios=_scenarios())
    assert d.scenarios is not None
    assert d.scenarios.bull.probability == 0.3


def test_scenarios_prob_sum_below_threshold_rejected() -> None:
    with pytest.raises(ValidationError, match="must sum to 1.0"):
        _base(scenarios=_scenarios(p_bull=0.3, p_base=0.3, p_bear=0.2))


def test_scenarios_prob_sum_above_threshold_rejected() -> None:
    with pytest.raises(ValidationError, match="must sum to 1.0"):
        _base(scenarios=_scenarios(p_bull=0.5, p_base=0.5, p_bear=0.5))


def test_scenarios_prob_within_002_tolerance_accepted() -> None:
    d = _base(scenarios=_scenarios(p_bull=0.301, p_base=0.499, p_bear=0.2))
    assert d.scenarios is not None


# ---------------------------------------------------------------------------
# price_target / catalysts / risks
# ---------------------------------------------------------------------------


def test_price_target_valid() -> None:
    d = _base(price_target={"value": 320.0, "horizon_days": 365})
    assert d.price_target is not None
    assert d.price_target.value == 320.0


def test_price_target_horizon_too_short_rejected() -> None:
    with pytest.raises(ValidationError):
        PriceTarget(value=100, horizon_days=3)


def test_catalysts_optional_list_ok() -> None:
    d = _base(
        catalysts=[
            {"event": "Q1 earnings", "eta_window": "2026-05-15"},
            {"event": "FOMC", "eta_window": "2026-06-12"},
        ]
    )
    assert len(d.catalysts) == 2


def test_risks_three_required_when_provided() -> None:
    d = _base(risks=["macro shock", "earnings miss", "supply constraint"])
    assert len(d.risks) == 3


def test_risks_two_rejected() -> None:
    with pytest.raises(ValidationError, match="exactly 3"):
        _base(risks=["a", "b"])


# ---------------------------------------------------------------------------
# Sub-model construction tests
# ---------------------------------------------------------------------------


def test_scenario_case_probability_out_of_range() -> None:
    with pytest.raises(ValidationError):
        ScenarioCase(price_target=100, probability=1.5, rationale="x")


def test_scenario_set_constructed_directly_validates_sum() -> None:
    with pytest.raises(ValidationError):
        ScenarioSet(
            bull=ScenarioCase(price_target=100, probability=0.5, rationale="x"),
            base=ScenarioCase(price_target=80, probability=0.3, rationale="x"),
            bear=ScenarioCase(price_target=60, probability=0.5, rationale="x"),
        )


def test_catalyst_long_event_rejected() -> None:
    with pytest.raises(ValidationError):
        Catalyst(event="x" * 200, eta_window="2026-05-15")
