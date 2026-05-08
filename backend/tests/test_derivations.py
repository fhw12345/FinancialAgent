"""W2.9 unit tests — atr_stop, vol_adjusted_size + cross-validator."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models.derivations import (
    Derivation,
    atr_stop,
    vol_adjusted_size,
)
from src.models.trading_decision import TradingDecision


# ---------------------------------------------------------------------------
# atr_stop
# ---------------------------------------------------------------------------


def test_atr_stop_long_subtracts_n_atr() -> None:
    d = atr_stop(price=100.0, atr=2.0, n=1.5, side="long")
    assert d.value == pytest.approx(97.0, abs=1e-6)
    assert d.formula == "price - n * atr"
    assert d.inputs == {"price": 100.0, "atr": 2.0, "n": 1.5, "side": "long"}


def test_atr_stop_short_adds_n_atr() -> None:
    d = atr_stop(price=100.0, atr=2.0, n=2, side="short")
    assert d.value == pytest.approx(104.0, abs=1e-6)
    assert d.formula == "price + n * atr"


def test_atr_stop_default_n_is_1_5() -> None:
    d = atr_stop(price=100.0, atr=4.0)
    assert d.inputs["n"] == 1.5
    assert d.value == pytest.approx(94.0, abs=1e-6)


def test_atr_stop_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="price"):
        atr_stop(price=0, atr=1.0)
    with pytest.raises(ValueError, match="atr"):
        atr_stop(price=100, atr=-1.0)
    with pytest.raises(ValueError, match="n"):
        atr_stop(price=100, atr=1.0, n=0)
    with pytest.raises(ValueError, match="side"):
        atr_stop(price=100, atr=1.0, side="up")


# ---------------------------------------------------------------------------
# vol_adjusted_size
# ---------------------------------------------------------------------------


def test_vol_adjusted_size_floors_shares() -> None:
    # $100 risk / $4 stop distance = 25 shares
    d = vol_adjusted_size(account_risk_dollar=100.0, stop_distance_dollar=4.0)
    assert d.value == 25.0
    assert d.formula == "floor(account_risk_dollar / stop_distance_dollar)"


def test_vol_adjusted_size_floors_partial() -> None:
    # $100 / $7 = 14.28 -> floor 14
    d = vol_adjusted_size(account_risk_dollar=100.0, stop_distance_dollar=7.0)
    assert d.value == 14.0


def test_vol_adjusted_size_with_price_reports_position_value() -> None:
    d = vol_adjusted_size(
        account_risk_dollar=100.0, stop_distance_dollar=4.0, price=200.0
    )
    assert d.inputs["price"] == 200.0
    assert d.inputs["position_value_estimate"] == pytest.approx(25 * 200.0, abs=1e-6)


def test_vol_adjusted_size_zero_stop_returns_zero() -> None:
    d = vol_adjusted_size(account_risk_dollar=100.0, stop_distance_dollar=0.0)
    assert d.value == 0
    assert "stop_distance == 0" in d.formula


def test_vol_adjusted_size_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="account_risk_dollar"):
        vol_adjusted_size(account_risk_dollar=0, stop_distance_dollar=1.0)
    with pytest.raises(ValueError, match="stop_distance_dollar"):
        vol_adjusted_size(account_risk_dollar=10, stop_distance_dollar=-1.0)


# ---------------------------------------------------------------------------
# Cross-validator on TradingDecision
# ---------------------------------------------------------------------------


def _buy(**overrides):
    payload = {
        "symbol": "AAPL",
        "decision": "BUY",
        "position_size_percent": 10,
        "swap_from_symbol": None,
        "confidence": 7,
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "reasoning_summary": "test",
    }
    payload.update(overrides)
    return TradingDecision(**payload)


def test_derivation_matches_price_accepts() -> None:
    d = _buy(
        stop_derivation=Derivation(
            value=95.0,
            formula="price - n * atr",
            inputs={"price": 100, "atr": 2, "n": 2.5},
        )
    )
    assert d.stop_derivation.value == 95.0


def test_derivation_drift_within_tolerance_accepts() -> None:
    # 95 ± 0.5% = ±0.475; 95.4 within bounds
    d = _buy(
        stop_derivation=Derivation(
            value=95.4,
            formula="price - n * atr",
            inputs={"price": 100, "atr": 2.3, "n": 2},
        )
    )
    assert d.stop_derivation.value == 95.4


def test_derivation_drift_beyond_tolerance_rejects() -> None:
    # 95 ± 0.5% = ±0.475; 96.0 is 1.05% off, should reject
    with pytest.raises(ValidationError, match="does not match stop_loss"):
        _buy(
            stop_derivation=Derivation(
                value=96.0,
                formula="x",
                inputs={"x": 1},
            )
        )


def test_target_derivation_drift_rejects() -> None:
    with pytest.raises(ValidationError, match="does not match take_profit"):
        _buy(
            target_derivation=Derivation(
                value=120.0,
                formula="x",
                inputs={"x": 1},
            )
        )


def test_negative_size_derivation_rejects() -> None:
    with pytest.raises(ValidationError, match="size_derivation.value cannot"):
        _buy(
            size_derivation=Derivation(
                value=-5,
                formula="x",
                inputs={"x": 1},
            )
        )


def test_derivation_absent_fields_back_compat() -> None:
    # No derivations at all should still parse.
    d = _buy()
    assert d.entry_derivation is None
    assert d.stop_derivation is None
    assert d.target_derivation is None
    assert d.size_derivation is None
