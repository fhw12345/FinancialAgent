"""Tests for OrderIntent + TradingDecision geometry validator (W1.1).

Why this exists: the CRWV-style hard bug from 2026-05-07 shipped a SELL
payload with stop_loss=142 > entry_price=138 > take_profit=122. With
intent inferred as `close_long`, that geometry must be rejected — it
matches the byte layout of an `open_short` order and a downstream OMS
would mis-route it.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models.trading_decision import (
    OrderIntent,
    TradingDecision,
)


def _base(decision="BUY", **overrides):
    """Helper to build a valid-shape TradingDecision and override fields."""
    payload = {
        "symbol": "AAPL",
        "decision": decision,
        "position_size_percent": 10 if decision != "HOLD" else None,
        "swap_from_symbol": None,
        "confidence": 7,
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "reasoning_summary": "test",
    }
    payload.update(overrides)
    return TradingDecision(**payload)


class TestIntentInference:
    def test_buy_infers_open_long(self) -> None:
        d = _base(decision="BUY")
        assert d.intent == OrderIntent.OPEN_LONG

    def test_sell_infers_close_long(self) -> None:
        # close_long needs stop < entry < take_profit (selling existing
        # long: limit at recovery, stop below to protect, target above for
        # extension). Use values that satisfy this geometry.
        d = _base(
            decision="SELL",
            entry_price=110.0,
            stop_loss=95.0,
            take_profit=120.0,
        )
        assert d.intent == OrderIntent.CLOSE_LONG

    def test_hold_infers_hold(self) -> None:
        d = _base(
            decision="HOLD",
            position_size_percent=None,
            entry_price=None,
            stop_loss=None,
            take_profit=None,
        )
        assert d.intent == OrderIntent.HOLD

    def test_explicit_intent_overrides_inference(self) -> None:
        # Open a new short: stop must be above entry, target below.
        d = _base(
            decision="SELL",
            intent=OrderIntent.OPEN_SHORT,
            entry_price=100.0,
            stop_loss=110.0,
            take_profit=85.0,
        )
        assert d.intent == OrderIntent.OPEN_SHORT


class TestGeometryValidation:
    def test_close_long_rejects_stop_above_entry(self) -> None:
        """CRWV-style historical payload must raise.

        Original CRWV decision: entry=138 stop=142 target=122. With intent
        inferred to close_long, the stop>entry geometry is byte-identical
        to an open_short and must be rejected.
        """
        with pytest.raises(ValidationError, match="close_long requires"):
            _base(
                decision="SELL",
                symbol="CRWV",
                entry_price=138.0,
                stop_loss=142.0,
                take_profit=122.0,
            )

    def test_open_long_rejects_stop_above_entry(self) -> None:
        with pytest.raises(ValidationError, match="open_long requires"):
            _base(
                decision="BUY",
                entry_price=100.0,
                stop_loss=110.0,
                take_profit=120.0,
            )

    def test_open_short_rejects_stop_below_entry(self) -> None:
        with pytest.raises(ValidationError, match="open_short requires"):
            _base(
                decision="SELL",
                intent=OrderIntent.OPEN_SHORT,
                entry_price=100.0,
                stop_loss=90.0,
                take_profit=110.0,
            )

    def test_close_short_rejects_stop_below_entry(self) -> None:
        # Closing a short: limit-buy at recovery, stop above to protect
        # against further upside, target below for extension. stop<entry
        # would be byte-identical to open_long and must be rejected.
        with pytest.raises(ValidationError, match="close_short requires"):
            _base(
                decision="BUY",
                intent=OrderIntent.CLOSE_SHORT,
                entry_price=100.0,
                stop_loss=90.0,
                take_profit=110.0,
            )

    def test_close_long_accepts_correct_geometry(self) -> None:
        # Selling 50% of an existing long: limit at recovery $110, stop at
        # $95 if it breaks down, target at $120 if rally extends.
        d = _base(
            decision="SELL",
            entry_price=110.0,
            stop_loss=95.0,
            take_profit=120.0,
        )
        assert d.intent == OrderIntent.CLOSE_LONG

    def test_hold_does_not_validate_prices(self) -> None:
        # HOLD with all None prices is fine.
        d = _base(
            decision="HOLD",
            position_size_percent=None,
            entry_price=None,
            stop_loss=None,
            take_profit=None,
        )
        assert d.intent == OrderIntent.HOLD

    def test_partial_prices_skipped(self) -> None:
        # If any of the three is None, geometry check is skipped (BUY/SELL
        # with missing prices fails other validators upstream, not this one).
        d = _base(
            decision="BUY",
            entry_price=100.0,
            stop_loss=None,
            take_profit=110.0,
        )
        assert d.intent == OrderIntent.OPEN_LONG
