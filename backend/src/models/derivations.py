"""Numeric-derivation helpers (W2.9).

Why this exists:
  The sell-side analyst review flagged that decisions like "stop $620,
  size 30-40%" carry false precision: no formula behind the number,
  no inputs the reader can audit. This module gives the LLM (and tests)
  a small library of standard derivations:

    atr_stop(price, atr, n)                 -> price ± n * ATR
    vol_adjusted_size(account_risk_dollar,
                       stop_distance_dollar) -> shares (floor)

  Each helper returns a `Derivation` object — {value, formula, inputs}.
  When the W2.10 prompt nudges the LLM to attach a Derivation alongside
  every concrete stop / target / size, downstream UI (W2.11 e2e checks
  this) can render a hover tooltip with `formula(inputs) = value` so
  the reader can audit and challenge the number.

Optional Derivation fields are added to TradingDecision via
`models/trading_decision.py` — kept optional so existing decisions
parse unchanged.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field


class Derivation(BaseModel):
    """Audit-trail object accompanying a concrete numeric trade level."""

    value: float = Field(description="The derived number (price or quantity).")
    formula: str = Field(
        max_length=200,
        description=(
            "Compact symbolic form, e.g. 'price - n * atr'. Should be "
            "human-readable and re-runnable against inputs."
        ),
    )
    inputs: dict[str, Any] = Field(
        default_factory=dict,
        description="Named inputs the formula references; types match the helper.",
    )


# ---------------------------------------------------------------------------
# atr_stop — protective stop a fixed multiple of ATR away from price
# ---------------------------------------------------------------------------


def atr_stop(
    *,
    price: float,
    atr: float,
    n: float = 1.5,
    side: str = "long",
) -> Derivation:
    """ATR-based protective stop.

    Args:
        price: anchor price (entry).
        atr: average true range (same units as price). Must be > 0.
        n: ATR multiple (PRD example uses 1.5; 2-3 for swing).
        side: 'long' (stop below price) or 'short' (stop above).

    Returns:
        Derivation with formula `price - n * atr` (long) or
        `price + n * atr` (short).
    """
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")
    if atr <= 0:
        raise ValueError(f"atr must be positive, got {atr}")
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    side = side.lower()
    if side not in ("long", "short"):
        raise ValueError(f"side must be 'long' or 'short', got {side!r}")

    if side == "long":
        value = price - n * atr
        formula = "price - n * atr"
    else:
        value = price + n * atr
        formula = "price + n * atr"

    return Derivation(
        value=round(value, 4),
        formula=formula,
        inputs={
            "price": round(price, 4),
            "atr": round(atr, 4),
            "n": n,
            "side": side,
        },
    )


# ---------------------------------------------------------------------------
# vol_adjusted_size — dollar-risk-anchored position sizing
# ---------------------------------------------------------------------------


def vol_adjusted_size(
    *,
    account_risk_dollar: float,
    stop_distance_dollar: float,
    price: float | None = None,
) -> Derivation:
    """Position size such that (price - stop) * shares == account_risk.

    Args:
        account_risk_dollar: how many $ you're willing to lose if stop hits.
        stop_distance_dollar: |entry - stop| per share.
        price: optional reference price; if provided, also reports
               position_value as inputs['position_value_estimate'].

    Returns:
        Derivation with value = floor(account_risk / stop_distance).
        If stop_distance is 0 (or larger than account_risk), value
        clamps to 0 with a formula note (we never divide by zero).
    """
    if account_risk_dollar <= 0:
        raise ValueError(
            f"account_risk_dollar must be positive, got {account_risk_dollar}"
        )
    if stop_distance_dollar < 0:
        raise ValueError(
            f"stop_distance_dollar must be non-negative, got {stop_distance_dollar}"
        )

    if stop_distance_dollar == 0:
        return Derivation(
            value=0,
            formula="0  # stop_distance == 0 -> infinite size; clamped",
            inputs={
                "account_risk_dollar": account_risk_dollar,
                "stop_distance_dollar": 0.0,
            },
        )

    shares = math.floor(account_risk_dollar / stop_distance_dollar)
    inputs: dict[str, Any] = {
        "account_risk_dollar": round(account_risk_dollar, 2),
        "stop_distance_dollar": round(stop_distance_dollar, 4),
    }
    if price is not None:
        inputs["price"] = round(price, 4)
        inputs["position_value_estimate"] = round(shares * price, 2)
    return Derivation(
        value=float(shares),
        formula="floor(account_risk_dollar / stop_distance_dollar)",
        inputs=inputs,
    )
