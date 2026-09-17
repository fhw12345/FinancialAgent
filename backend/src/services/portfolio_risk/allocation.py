"""Deterministic target-to-share previews and whole-batch checks. Never executes orders."""

from decimal import ROUND_FLOOR, Decimal

from ...models.portfolio_risk import (
    AllocationReceipt,
    PortfolioRiskSnapshot,
    RiskPosition,
    SizedChange,
    TargetProposal,
)
from .estimator import estimate


def decimal(value: float) -> Decimal:
    return Decimal(str(value))


def lot_floor(quantity: Decimal, lot: Decimal) -> Decimal:
    return (quantity / lot).to_integral_value(rounding=ROUND_FLOOR) * lot


def allocate(
    snapshot: PortfolioRiskSnapshot, proposals: list[TargetProposal]
) -> AllocationReceipt:
    current = estimate(snapshot)
    failures = list(snapshot.errors)
    policy = snapshot.policy.policy
    if policy is None or snapshot.policy.confirmed_at is None:
        failures.append("POLICY_UNCONFIRMED")
    if current.status != "complete" or current.equity is None or current.equity <= 0:
        failures.append("CURRENT_RISK_UNAVAILABLE")
    if len({p.symbol for p in proposals}) != len(proposals):
        failures.append("DUPLICATE_PROPOSAL")
    assets = {a.symbol: a for a in snapshot.assets}
    for p in proposals:
        asset = assets.get(p.symbol)
        if (
            asset is None
            or asset.mark is None
            or asset.mark_session != snapshot.session_date
            or asset.currency != "USD"
        ):
            failures.append("PROPOSAL_MARK_UNAVAILABLE:" + p.symbol)
        elif p.stop is not None and p.stop >= asset.mark:
            failures.append("INVALID_STOP_DISTANCE:" + p.symbol)
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
    if cash < 0:
        failures.append("CASH_INSUFFICIENT_AFTER_COSTS")
    # Estimated sales are not settled buying power, regardless of request ordering.
    if available < 0:
        failures.append("UNFILLED_SELL_PROCEEDS_REQUIRED")
    turnover = gross_turnover / equity
    if turnover > decimal(policy.max_turnover):
        failures.append("TURNOVER_LIMIT")
    proposed = None
    if cash >= 0:
        post_snapshot = snapshot.model_copy(
            update={"cash": float(cash), "positions": list(positions.values())}
        )
        proposed = estimate(post_snapshot)
        if proposed.status != "complete":
            failures.append("PROPOSED_RISK_UNAVAILABLE")
        # Use post-cost equity for exposures. Original draft/target is never mutated.
        post_equity = cash + sum(
            decimal(p.quantity) * decimal(assets[p.symbol].mark or 0)
            for p in positions.values()
        )
        if post_equity <= 0:
            failures.append("ZERO_POSTTRADE_EQUITY")
        else:
            if cash < post_equity * decimal(policy.min_cash_weight):
                failures.append("CASH_FLOOR")
            sectors: dict[str, Decimal] = {}
            for position in positions.values():
                weight = (
                    decimal(position.quantity)
                    * decimal(assets[position.symbol].mark or 0)
                    / post_equity
                )
                if weight > decimal(policy.max_position_weight):
                    failures.append("POSITION_LIMIT:" + position.symbol)
                sector = assets[position.symbol].sector
                sectors[sector] = sectors.get(sector, Decimal(0)) + weight
            for sector, weight in sectors.items():
                if sector == "Unknown":
                    failures.append("SECTOR_UNAVAILABLE")
                if weight > decimal(policy.max_sector_weight):
                    failures.append("SECTOR_LIMIT:" + sector)
    return AllocationReceipt(
        status="blocked" if failures else "feasible_preview",
        constraints=sorted(set(failures)),
        changes=changes,
        proposed=proposed,
        turnover=float(turnover),
        posttrade_cash=float(cash),
        cash_without_unfilled_sales=float(available),
    )
