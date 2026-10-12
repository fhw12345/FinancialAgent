"""Independent exact/brute-force boundaries for versioned sizing; no policy exceptions."""

from fractions import Fraction

import pytest
from src.models.portfolio_risk import TargetProposal
from src.services.portfolio_risk.allocation import allocate
from src.services.portfolio_risk.post_cost import (
    allocate_post_cost,
    continuous_equity,
    rational,
)
from tests.portfolio_risk_fixtures import asset, policy, snapshot


def test_single_symbol_result_is_maximum_lot_grid_quantity_under_post_cost_target():
    for cash, old_qty, target, rate in [
        (900, 1, 0.3, 0.001),
        (1000, 9, 0.3, 0.2),
        (300, 7, 0.7, 0.02),
        (900, 3, 0.1, 0.1),
        (1000, 0, 1, 0.001),
        (100, 9, 0, 0.2),
    ]:
        s = snapshot(
            cash=cash,
            holdings={"AAPL": old_qty} if old_qty else {},
            assets=[asset()],
            confirmed=policy(
                fee_bps=float(rate * 10000 / 2), slippage_bps=float(rate * 10000 / 2)
            ),
        )
        result = allocate_post_cost(
            s, [TargetProposal(symbol="AAPL", target_weight=target)]
        )
        equity = Fraction(cash + old_qty * 100)
        r, t = rational(rate), rational(target)
        possible = [
            Fraction(i, 10)
            for i in range(int(equity / 100 * 10) + 1)
            if Fraction(i, 10) * 100
            <= t * (equity - r * abs(Fraction(i, 10) - old_qty) * 100)
        ]
        assert Fraction(str(result.changes[0].proposed_quantity)) == max(possible)
        assert result.post_cost_sizing.total_estimated_cost == pytest.approx(
            float(r * abs(max(possible) - old_qty) * 100)
        )


def test_mixed_batch_is_order_independent_and_fixes_omitted_holdings():
    s = snapshot(
        cash=3000,
        holdings={"AAPL": 70},
        assets=[asset(), asset("MSFT")],
        confirmed=policy(fee_bps=100.0, slippage_bps=100.0),
    )
    proposals = [
        TargetProposal(symbol="AAPL", target_weight=0.3),
        TargetProposal(symbol="MSFT", target_weight=0.2),
    ]
    result = allocate_post_cost(s, proposals)
    assert result.model_dump(mode="json") == allocate_post_cost(
        s, list(reversed(proposals))
    ).model_dump(mode="json")
    assert result.post_cost_sizing.continuous_equity == pytest.approx(
        float(Fraction(9860) / Fraction(998, 1000))
    )
    assert [(c.symbol, c.proposed_quantity) for c in result.changes] == [
        ("AAPL", 29.6),
        ("MSFT", 19.7),
    ]
    assert result.posttrade_cash == pytest.approx(4949.8)
    assert result.post_cost_sizing.actual_post_cost_equity == pytest.approx(9879.8)
    # Excluding the reduction cannot silently change the existing AAPL holding.
    alone = allocate_post_cost(s, [proposals[1]])
    assert alone.proposed.position_weights["AAPL"] > 0.7
    assert alone.changes[0].symbol == "MSFT"


def test_unfilled_sale_proceeds_and_subset_risks_still_block():
    s = snapshot(
        cash=100,
        holdings={"AAPL": 99},
        assets=[asset(), asset("MSFT")],
        confirmed=policy(fee_bps=1.0, slippage_bps=10.0),
    )
    result = allocate_post_cost(
        s,
        [
            TargetProposal(symbol="AAPL", target_weight=0.0),
            TargetProposal(symbol="MSFT", target_weight=0.5),
        ],
    )
    assert (
        result.status == "blocked"
        and "UNFILLED_SELL_PROCEEDS_REQUIRED" in result.constraints
    )
    assert result.posttrade_cash > 0 and result.cash_without_unfilled_sales < 0
    assert result.changes[1].requested_target_weight == 0.5


def test_exit_consumes_odd_lot_but_does_not_invent_short_quantity():
    s = snapshot(
        cash=1000,
        holdings={"AAPL": 0.05},
        assets=[asset()],
        confirmed=policy(lot_size=0.1),
    )
    result = allocate_post_cost(s, [TargetProposal(symbol="AAPL", target_weight=0.0)])
    assert result.changes[0].delta_quantity == -0.05
    assert result.changes[0].proposed_quantity == 0
    assert result.proposed.invested_value == 0


@pytest.mark.parametrize(
    "bad", ["duplicate", "sum", "stop", "unconfirmed", "marks", "history"]
)
def test_new_basis_missing_inputs_and_unsupported_plans_fail_closed(bad):
    s = snapshot(
        cash=1000, holdings={}, assets=[asset(), asset("MSFT")], confirmed=policy()
    )
    proposals = [TargetProposal(symbol="AAPL", target_weight=0.2)]
    expected = {
        "duplicate": "DUPLICATE_PROPOSAL",
        "sum": "TARGET_WEIGHTS_EXCEED_EQUITY",
        "stop": "POST_COST_STOP_PLAN_UNSUPPORTED",
        "unconfirmed": "POLICY_UNCONFIRMED",
        "marks": "PROPOSAL_MARK_UNAVAILABLE:AAPL",
        "history": "PROPOSED_RISK_UNAVAILABLE",
    }[bad]
    if bad == "duplicate":
        proposals *= 2
    if bad == "sum":
        proposals = [
            TargetProposal(symbol=symbol, target_weight=0.7)
            for symbol in ("AAPL", "MSFT")
        ]
    if bad == "stop":
        proposals[0].stop = 90.0
    if bad == "unconfirmed":
        s.policy.policy = None
    if bad == "marks":
        s.assets[0].mark = None
    if bad == "history":
        s.assets[0].returns = []
    result = allocate_post_cost(s, proposals)
    assert result.status == "blocked" and expected in result.constraints
    assert result.target_equity_basis == "post_cost"


def test_zero_cost_compatible_sizing_and_legacy_wire_has_no_new_hash_fields():
    s = snapshot(cash=9000, holdings={"AAPL": 10}, confirmed=policy())
    target = [TargetProposal(symbol="AAPL", target_weight=0.2)]
    old, new = allocate(s, target), allocate_post_cost(s, target)
    assert old.changes == new.changes
    assert old.posttrade_cash == new.posttrade_cash
    assert "target_equity_basis" not in old.model_dump(mode="json")
    assert "post_cost_sizing" not in old.model_dump(mode="json")
    assert new.calculator_version == "post-cost-targets@1"


def test_signed_lot_rounding_interaction_rechecks_actual_equity_without_policy_clipping():
    s = snapshot(
        cash=100,
        holdings={"AAPL": 1},
        assets=[asset(), asset("MSFT")],
        confirmed=policy(fee_bps=1000.0, slippage_bps=1000.0),
    )
    s.assets[1].mark = 7.0
    result = allocate_post_cost(
        s,
        [
            TargetProposal(symbol="AAPL", target_weight=0.1),
            TargetProposal(symbol="MSFT", target_weight=0.3),
        ],
    )
    assert result.status == "feasible_preview", result.constraints
    assert result.post_cost_sizing.rounding_iterations == 1
    assert [(c.symbol, c.proposed_quantity) for c in result.changes] == [
        ("AAPL", 0.1),
        ("MSFT", 7.3),
    ]
    assert result.post_cost_sizing.actual_post_cost_equity == pytest.approx(171.78)
    assert all(
        t.effective_post_cost_weight <= t.requested_target_weight
        for t in result.post_cost_sizing.targets
    )


def test_numeric_output_range_fails_closed_without_publishing_fake_sizes():
    s = snapshot(cash=10000, holdings={}, assets=[asset()], confirmed=policy())
    s.assets[0].mark = 1e-308
    result = allocate_post_cost(s, [TargetProposal(symbol="AAPL", target_weight=1.0)])
    assert result.status == "blocked" and result.changes == []
    assert result.constraints == ["POST_COST_NUMERIC_RANGE_UNSUPPORTED"]


def test_v2_receipt_cannot_claim_feasibility_without_a_sizing_proof():
    from pydantic import ValidationError
    from src.models.portfolio_risk import AllocationReceipt

    with pytest.raises(ValidationError, match="sizing proof"):
        AllocationReceipt(
            calculator_version="post-cost-targets@1",
            target_equity_basis="post_cost",
            status="feasible_preview",
            constraints=[],
        )
    with pytest.raises(ValidationError, match="Legacy allocator"):
        AllocationReceipt(
            calculator_version="idq-002@1",
            target_equity_basis="post_cost",
            status="blocked",
            constraints=["reason"],
        )
    with pytest.raises(ValidationError, match="bind post-cost"):
        AllocationReceipt(
            calculator_version="post-cost-targets@1",
            status="blocked",
            constraints=["reason"],
        )


def test_exact_solver_checks_piecewise_boundary_and_rejects_unsupported_range():
    assert (
        continuous_equity(Fraction(100), Fraction(0), [(Fraction(0.5), Fraction(50))])
        == 100
    )
    with pytest.raises(ValueError, match="UNSOLVABLE"):
        continuous_equity(Fraction(0), Fraction(0.1), [])
