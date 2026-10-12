"""Deterministic target-to-share previews and whole-batch checks. Never executes orders."""

from decimal import ROUND_FLOOR, Decimal

from ...models.portfolio_risk import (
    AllocationReceipt,
    PortfolioRiskSnapshot,
    RiskPosition,
    SizedChange,
    TargetProposal,
)
from .allocation_checks import finish_allocation, prepare_inputs


def decimal(value: float) -> Decimal:
    return Decimal(str(value))


def lot_floor(quantity: Decimal, lot: Decimal) -> Decimal:
    return (quantity / lot).to_integral_value(rounding=ROUND_FLOOR) * lot


def allocate(
    snapshot: PortfolioRiskSnapshot, proposals: list[TargetProposal]
) -> AllocationReceipt:
    current, policy, failures = prepare_inputs(snapshot, proposals)
    assets = {a.symbol: a for a in snapshot.assets}
    if failures or policy is None or current.equity is None:
        return AllocationReceipt(status="blocked", constraints=sorted(set(failures)))
    equity = decimal(current.equity)
    cash = decimal(snapshot.cash or 0)
    available = cash
    lot = decimal(policy.lot_size)
    positions = {p.symbol: p.model_copy() for p in snapshot.positions}
    gross_turnover = Decimal(0)
    changes: list[SizedChange] = []
    for p in sorted(proposals, key=lambda p: p.symbol):
        mark = decimal(assets[p.symbol].mark or 0)
        old = positions.get(p.symbol)
        qty = decimal(old.quantity) if old else Decimal(0)
        target = equity * decimal(p.target_weight) / mark
        direction = Decimal(1) if target >= qty else Decimal(-1)
        delta = lot_floor(abs(target - qty), lot) * direction
        cap = None
        if delta > 0 and p.stop is not None:
            cap = lot_floor(
                equity
                * decimal(policy.risk_per_trade_weight)
                / (
                    mark
                    - decimal(p.stop)
                    + mark
                    * (decimal(policy.fee_bps) + decimal(policy.slippage_bps))
                    / Decimal(10000)
                ),
                lot,
            )
            delta = min(delta, cap)
        notional = abs(delta) * mark
        buffer = (
            notional
            * (decimal(policy.fee_bps) + decimal(policy.slippage_bps))
            / Decimal(10000)
        )
        cash -= delta * mark + buffer
        available -= max(delta, Decimal(0)) * mark + buffer
        gross_turnover += notional
        new_qty = qty + delta
        changes.append(
            SizedChange(
                symbol=p.symbol,
                requested_target_weight=p.target_weight,
                current_quantity=float(qty),
                proposed_quantity=float(new_qty),
                delta_quantity=float(delta),
                mark=float(mark),
                estimated_cost_buffer=float(buffer),
                stop_risk_quantity_cap=float(cap) if cap is not None else None,
            )
        )
        if new_qty > 0:
            positions[p.symbol] = RiskPosition(
                symbol=p.symbol,
                quantity=float(new_qty),
                cost_basis=old.cost_basis if old else 0.0,
            )
        else:
            positions.pop(p.symbol, None)
    return finish_allocation(
        snapshot,
        policy,
        equity,
        changes,
        cash,
        available,
        gross_turnover,
        positions,
        failures,
    )
