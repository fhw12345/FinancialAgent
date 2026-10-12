"""Shared full-account checks for legacy and explicitly bound post-cost sizing."""

from decimal import Decimal
from typing import Literal

from ...models.portfolio_risk import (
    AllocationReceipt,
    PortfolioRiskSnapshot,
    PostCostSizing,
    RiskMetrics,
    RiskPolicy,
    RiskPosition,
    SizedChange,
    TargetProposal,
)
from .estimator import estimate


def number(value: float) -> Decimal:
    return Decimal(str(value))


def prepare_inputs(
    snapshot: PortfolioRiskSnapshot, proposals: list[TargetProposal]
) -> tuple[RiskMetrics, RiskPolicy | None, list[str]]:
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
    return current, policy, failures


def finish_allocation(
    snapshot: PortfolioRiskSnapshot,
    policy: RiskPolicy,
    equity: Decimal,
    changes: list[SizedChange],
    cash: Decimal,
    available: Decimal,
    gross_turnover: Decimal,
    positions: dict[str, RiskPosition],
    failures: list[str],
    *,
    calculator_version: Literal["idq-002@1", "post-cost-targets@1"] = "idq-002@1",
    sizing: PostCostSizing | None = None,
) -> AllocationReceipt:
    assets = {a.symbol: a for a in snapshot.assets}
    if cash < 0:
        failures.append("CASH_INSUFFICIENT_AFTER_COSTS")
    if available < 0:
        failures.append("UNFILLED_SELL_PROCEEDS_REQUIRED")
    turnover = gross_turnover / equity
    if turnover > number(policy.max_turnover):
        failures.append("TURNOVER_LIMIT")
    proposed = None
    if cash >= 0:
        post_snapshot = snapshot.model_copy(
            update={"cash": float(cash), "positions": list(positions.values())}
        )
        proposed = estimate(post_snapshot)
        if proposed.status != "complete":
            failures.append("PROPOSED_RISK_UNAVAILABLE")
        post_equity = cash + sum(
            number(p.quantity) * number(assets[p.symbol].mark or 0)
            for p in positions.values()
        )
        if post_equity <= 0:
            failures.append("ZERO_POSTTRADE_EQUITY")
        else:
            if cash < post_equity * number(policy.min_cash_weight):
                failures.append("CASH_FLOOR")
            sectors: dict[str, Decimal] = {}
            for position in positions.values():
                weight = (
                    number(position.quantity)
                    * number(assets[position.symbol].mark or 0)
                    / post_equity
                )
                if weight > number(policy.max_position_weight):
                    failures.append("POSITION_LIMIT:" + position.symbol)
                sector = assets[position.symbol].sector
                sectors[sector] = sectors.get(sector, Decimal(0)) + weight
            for sector, weight in sectors.items():
                if sector == "Unknown":
                    failures.append("SECTOR_UNAVAILABLE")
                if weight > number(policy.max_sector_weight):
                    failures.append("SECTOR_LIMIT:" + sector)
    return AllocationReceipt(
        calculator_version=calculator_version,
        status="blocked" if failures else "feasible_preview",
        constraints=sorted(set(failures)),
        changes=changes,
        proposed=proposed,
        turnover=float(turnover),
        posttrade_cash=float(cash),
        cash_without_unfilled_sales=float(available),
        target_equity_basis=(
            "post_cost" if calculator_version == "post-cost-targets@1" else None
        ),
        post_cost_sizing=sizing,
    )
