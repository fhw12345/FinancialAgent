"""Exact post-cost target conversion. No policy clipping, unfilled-sale funding or execution."""

from decimal import Decimal, localcontext
from fractions import Fraction

from ...models.portfolio_risk import (
    AllocationReceipt,
    EffectiveTarget,
    PortfolioRiskSnapshot,
    PostCostSizing,
    RiskPosition,
    SizedChange,
    TargetProposal,
)
from .allocation_checks import finish_allocation, prepare_inputs


class SizingUnavailable(ValueError):
    pass


def rational(value: float) -> Fraction:
    return Fraction(Decimal(str(value)))


def as_decimal(value: Fraction) -> Decimal:
    return Decimal(value.numerator) / Decimal(value.denominator)


def continuous_equity(
    equity: Fraction, rate: Fraction, terms: list[tuple[Fraction, Fraction]]
) -> Fraction:
    """Solve E = E0 - rate*sum(abs(target*E-old_notional)) over exact linear slots."""
    breaks = sorted(
        {
            Fraction(0),
            equity,
            *(
                old / target
                for target, old in terms
                if target > 0 and 0 < old / target < equity
            ),
        }
    )
    for low, high in zip(breaks[:-1], breaks[1:], strict=True):
        mid = (low + high) / 2
        signs = [1 if target * mid >= old else -1 for target, old in terms]
        slope = sum(
            (sign * target for sign, (target, _) in zip(signs, terms, strict=True)),
            Fraction(0),
        )
        offset = sum(
            (sign * old for sign, (_, old) in zip(signs, terms, strict=True)),
            Fraction(0),
        )
        denominator = 1 + rate * slope
        if denominator <= 0:
            raise SizingUnavailable("POST_COST_EQUITY_UNSOLVABLE")
        root = (equity + rate * offset) / denominator
        if low <= root <= high and root > 0:
            return root
    raise SizingUnavailable("POST_COST_EQUITY_UNSOLVABLE")


def rounded_quantity(
    old: Fraction, target: Fraction, equity: Fraction, mark: Fraction, lot: Fraction
) -> Fraction:
    if target == 0:
        return Fraction(0)  # A full exit may consume the remaining odd lot.
    desired_delta = (target * equity / mark - old) / lot
    signed_lots = desired_delta.numerator // desired_delta.denominator
    return max(Fraction(0), old + signed_lots * lot)


def allocate_post_cost(
    snapshot: PortfolioRiskSnapshot, proposals: list[TargetProposal]
) -> AllocationReceipt:
    current, policy, failures = prepare_inputs(snapshot, proposals)
    if any(p.stop is not None for p in proposals):
        failures.append("POST_COST_STOP_PLAN_UNSUPPORTED")
    if sum((rational(p.target_weight) for p in proposals), Fraction(0)) > 1:
        failures.append("TARGET_WEIGHTS_EXCEED_EQUITY")
    if failures or policy is None or current.equity is None:
        return AllocationReceipt(
            calculator_version="post-cost-targets@1",
            target_equity_basis="post_cost",
            status="blocked",
            constraints=sorted(set(failures)),
        )
    try:
        with localcontext() as context:
            context.prec = 60
            return _allocate(snapshot, proposals, failures)
    except (ValueError, OverflowError) as error:
        code = (
            str(error)
            if isinstance(error, SizingUnavailable)
            else "POST_COST_NUMERIC_RANGE_UNSUPPORTED"
        )
        return AllocationReceipt(
            calculator_version="post-cost-targets@1",
            target_equity_basis="post_cost",
            status="blocked",
            constraints=[code],
        )


def _allocate(
    snapshot: PortfolioRiskSnapshot,
    proposals: list[TargetProposal],
    failures: list[str],
) -> AllocationReceipt:
    policy = snapshot.policy.policy
    if policy is None:
        raise SizingUnavailable("POLICY_UNCONFIRMED")
    assets = {a.symbol: a for a in snapshot.assets}
    positions = {p.symbol: p.model_copy() for p in snapshot.positions}
    marks = {s: rational(a.mark or 0) for s, a in assets.items()}
    old = {s: rational(p.quantity) for s, p in positions.items()}
    initial_cash = rational(snapshot.cash or 0)
    equity = initial_cash + sum((q * marks[s] for s, q in old.items()), Fraction(0))
    rate = (rational(policy.fee_bps) + rational(policy.slippage_bps)) / 10000
    lot = rational(policy.lot_size)
    ordered = sorted(proposals, key=lambda p: p.symbol)
    targets = {p.symbol: rational(p.target_weight) for p in ordered}
    terms = [
        (targets[p.symbol], old.get(p.symbol, Fraction(0)) * marks[p.symbol])
        for p in ordered
    ]
    root = continuous_equity(equity, rate, terms)
    quantities = {
        s: rounded_quantity(old.get(s, Fraction(0)), t, root, marks[s], lot)
        for s, t in targets.items()
    }
    for iteration in range(101):
        total_cost = rate * sum(
            (abs(quantities[s] - old.get(s, Fraction(0))) * marks[s] for s in targets),
            Fraction(0),
        )
        after = equity - total_cost
        if after <= 0:
            raise SizingUnavailable("ZERO_POSTTRADE_EQUITY")
        if all(q * marks[s] <= targets[s] * after for s, q in quantities.items()):
            break
        if iteration == 100:
            raise SizingUnavailable("POST_COST_ROUNDING_UNRESOLVED")
        quantities = {
            s: min(
                q,
                rounded_quantity(
                    old.get(s, Fraction(0)), targets[s], after, marks[s], lot
                ),
            )
            for s, q in quantities.items()
        }
    cash, available = initial_cash, initial_cash
    gross = Fraction(0)
    changes = []
    for p in ordered:
        symbol = p.symbol
        qty, new = old.get(symbol, Fraction(0)), quantities[symbol]
        delta = new - qty
        notional = abs(delta) * marks[symbol]
        cost = rate * notional
        cash -= delta * marks[symbol] + cost
        available -= max(delta, Fraction(0)) * marks[symbol] + cost
        gross += notional
        changes.append(
            SizedChange(
                symbol=symbol,
                requested_target_weight=p.target_weight,
                current_quantity=float(qty),
                proposed_quantity=float(new),
                delta_quantity=float(delta),
                mark=float(marks[symbol]),
                estimated_cost_buffer=float(cost),
            )
        )
        if new > 0:
            positions[symbol] = RiskPosition(
                symbol=symbol,
                quantity=float(new),
                cost_basis=positions[symbol].cost_basis if symbol in positions else 0.0,
            )
        else:
            positions.pop(symbol, None)
    sizing = PostCostSizing(
        original_equity=float(equity),
        continuous_equity=float(root),
        actual_post_cost_equity=float(after),
        total_estimated_cost=float(total_cost),
        rounding_iterations=iteration,
        targets=[
            EffectiveTarget(
                symbol=p.symbol,
                requested_target_weight=p.target_weight,
                effective_post_cost_weight=float(
                    quantities[p.symbol] * marks[p.symbol] / after
                ),
            )
            for p in ordered
        ],
    )
    return finish_allocation(
        snapshot,
        policy,
        as_decimal(equity),
        changes,
        as_decimal(cash),
        as_decimal(available),
        as_decimal(gross),
        positions,
        failures,
        calculator_version="post-cost-targets@1",
        sizing=sizing,
    )
