"""The genuine live finding is a target-basis mismatch, not a policy gate to weaken."""

from fractions import Fraction

import pytest

from src.models.portfolio_risk import TargetProposal
from src.services.portfolio_risk.allocation import allocate
from src.services.portfolio_risk.post_cost import allocate_post_cost
from tests.portfolio_risk_fixtures import asset, policy, snapshot


def concentrated():
    return snapshot(
        cash=3000.0,
        holdings={"AAPL": 70.0},
        assets=[asset(), asset("MSFT")],
        confirmed=policy(
            max_position_weight=0.3,
            max_sector_weight=0.6,
            min_cash_weight=0.2,
            fee_bps=1.0,
            slippage_bps=10.0,
        ),
    )


def test_recorded_boundary_target_has_correct_post_cost_basis_without_changing_target():
    source = concentrated()
    target = TargetProposal(symbol="AAPL", target_weight=0.3)
    legacy = allocate(source, [target])
    assert legacy.status == "blocked" and "POSITION_LIMIT:AAPL" in legacy.constraints
    assert legacy.changes[0].proposed_quantity == 30.0
    assert legacy.proposed.position_weights["AAPL"] == pytest.approx(0.3001320581055664)
    result = allocate_post_cost(source, [target])
    assert result.changes[0].proposed_quantity == 29.9
    assert result.status == "feasible_preview", result.constraints
    assert (
        result.changes[0].requested_target_weight == 0.3 and target.target_weight == 0.3
    )
    assert result.posttrade_cash == pytest.approx(7005.589)
    assert result.proposed.position_weights["AAPL"] <= 0.3
    assert result.actionable is False and source.positions[0].quantity == 70.0


def test_requested_above_policy_limit_is_not_repaired_into_a_ready_proposal():
    result = allocate_post_cost(
        concentrated(), [TargetProposal(symbol="AAPL", target_weight=0.4)]
    )
    assert result.status == "blocked" and "POSITION_LIMIT:AAPL" in result.constraints
    assert result.changes[0].requested_target_weight == 0.4


def test_full_investment_can_pay_costs_from_pre_cost_cash():
    source = snapshot(
        cash=10000.0,
        holdings={},
        assets=[asset()],
        confirmed=policy(fee_bps=10.0, slippage_bps=0.0, lot_size=0.1),
    )
    result = allocate_post_cost(
        source, [TargetProposal(symbol="AAPL", target_weight=1.0)]
    )
    # Independent exact oracle: E*=10000/(1+0.001), q*=E*/100;
    # lot floor gives 99.9 shares, costs9.99, remaining cash0.01.
    q = (
        (Fraction(10000) / Fraction(1001, 1000) / 100)
        // Fraction(1, 10)
        * Fraction(1, 10)
    )
    assert result.changes[0].proposed_quantity == float(q) == 99.9
    assert result.posttrade_cash == pytest.approx(0.01)
    assert result.status == "feasible_preview"
