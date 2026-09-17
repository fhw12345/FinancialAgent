"""Whole-batch post-cost constraints are independent of LLM confidence or ordering."""

import pytest
from src.models.portfolio_risk import TargetProposal
from src.services.portfolio_risk.allocation import allocate
from tests.portfolio_risk_fixtures import snapshot, asset, policy


def test_existing_exposure_counts_and_original_target_is_not_mutated():
    s = snapshot(
        cash=9100, holdings={"AAPL": 9}, confirmed=policy(max_position_weight=0.1)
    )
    p = TargetProposal(symbol="AAPL", target_weight=0.11)
    receipt = allocate(s, [p])
    assert "POSITION_LIMIT:AAPL" in receipt.constraints and not receipt.actionable
    assert receipt.proposed.position_weights["AAPL"] == pytest.approx(0.11)
    assert p.target_weight == 0.11 and s.positions[0].quantity == 9


def test_two_individually_feasible_buys_fail_as_one_batch():
    s = snapshot(
        cash=500,
        holdings={"AAPL": 5},
        assets=[asset(s) for s in ["AAPL", "MSFT", "NVDA"]],
        confirmed=policy(min_cash_weight=0.1),
    )
    p = [TargetProposal(symbol=s, target_weight=0.3) for s in ["MSFT", "NVDA"]]
    assert all(allocate(s, [x]).status == "feasible_preview" for x in p)
    assert allocate(s, p).status == "blocked"
    assert "CASH_INSUFFICIENT_AFTER_COSTS" in allocate(s, p).constraints


def test_stop_sizing_is_capped_at_twenty_shares_and_records_the_change():
    s = snapshot(
        cash=10000, holdings={}, assets=[asset()], confirmed=policy(lot_size=1.0)
    )
    p = TargetProposal(symbol="AAPL", target_weight=1.0, stop=95.0)
    result = allocate(s, [p])
    assert result.status == "feasible_preview" and not result.actionable
    assert result.changes[0].delta_quantity == 20
    assert result.changes[0].stop_risk_quantity_cap == 20
    assert result.changes[0].requested_target_weight == 1


def test_unfilled_sales_are_not_cash_and_input_order_is_irrelevant():
    s = snapshot(
        cash=100,
        holdings={"AAPL": 9},
        assets=[asset(), asset("MSFT")],
        confirmed=policy(),
    )
    p = [
        TargetProposal(symbol="AAPL", target_weight=0.0),
        TargetProposal(symbol="MSFT", target_weight=0.5),
    ]
    result = allocate(s, p)
    assert "UNFILLED_SELL_PROCEEDS_REQUIRED" in result.constraints
    assert result.posttrade_cash == 500 and result.cash_without_unfilled_sales == -400
    assert result.model_dump() == allocate(s, list(reversed(p))).model_dump()


def test_posttrade_sector_concentration_not_only_current_is_checked():
    s = snapshot(
        cash=900,
        holdings={"AAPL": 1},
        assets=[asset(), asset("MSFT")],
        confirmed=policy(max_sector_weight=0.15),
    )
    result = allocate(s, [TargetProposal(symbol="MSFT", target_weight=0.1)])
    assert "SECTOR_LIMIT:Technology" in result.constraints
    assert result.proposed.sector_weights["Technology"] == pytest.approx(0.2)


@pytest.mark.parametrize(
    "kind",
    [
        "unconfirmed",
        "history",
        "unknown_sector",
        "costs",
        "duplicate",
        "stop",
        "turnover",
    ],
)
def test_failure_paths_cannot_become_approval(kind):
    s = snapshot(
        cash=1000,
        holdings={},
        assets=[asset()],
        confirmed=policy(),
    )
    p = [TargetProposal(symbol="AAPL", target_weight=0.2)]
    expected = {
        "unconfirmed": "POLICY_UNCONFIRMED",
        "history": "PROPOSED_RISK_UNAVAILABLE",
        "unknown_sector": "SECTOR_UNAVAILABLE",
        "costs": "CASH_INSUFFICIENT_AFTER_COSTS",
        "duplicate": "DUPLICATE_PROPOSAL",
        "stop": "INVALID_STOP_DISTANCE:AAPL",
        "turnover": "TURNOVER_LIMIT",
    }[kind]
    if kind == "unconfirmed":
        s.policy.policy = None
    if kind == "history":
        s.assets[0].returns = []
    if kind == "unknown_sector":
        s.assets[0].sector = "Unknown"
    if kind == "duplicate":
        p = p * 2
    if kind == "stop":
        p[0].stop = 100.0
    if kind == "costs":
        s.policy.policy.fee_bps = 10.0
        p[0].target_weight = 1.0
    if kind == "turnover":
        s.policy.policy.max_turnover = 0.1
    result = allocate(s, p)
    assert (
        result.status == "blocked"
        and result.actionable is False
        and expected in result.constraints
    )
