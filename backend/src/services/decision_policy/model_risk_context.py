"""Frozen full-account diagnostics for decision prompts; pending checks are not absent data."""

from ...models.decision_assessment import DecisionAssessment
from ...models.decision_review import ReviewPolicyVersion


def context(
    source: DecisionAssessment, policy: ReviewPolicyVersion, symbols: list[str]
) -> tuple[dict[str, object], dict[str, object]]:
    risk = source.portfolio_risk
    if risk is None:
        return {"current_risk_status": "unavailable", "current_risk": None}, {
            "allocation_calculator": policy.allocation_calculator or "idq-002@1",
            "max_account_sigma": policy.policy.max_account_sigma,
        }
    snapshot, current = risk.snapshot, risk.current
    assets = {a.symbol: a for a in snapshot.assets}
    metrics = current.model_dump(mode="json")
    # Full-account weights/metrics/coverage remain intact. Only the optional
    # correlation presentation is bounded to this research scope, with omissions
    # disclosed; it is never used as subset risk clearance by the gate.
    included = set(symbols) & set(current.correlations)
    metrics["correlations"] = {
        a: {b: current.correlations[a].get(b) for b in sorted(included)}
        for a in sorted(included)
    }
    payload: dict[str, object] = {
        "account_scope": snapshot.account_scope,
        "account_revision": snapshot.account_revision,
        "risk_snapshot_id": snapshot.snapshot_id,
        "session": str(snapshot.session_date),
        "captured_at": snapshot.captured_at.isoformat(),
        "currency": "USD",
        "declared_cash": snapshot.cash,
        "cash_is_manual_declaration_not_settlement_ledger": True,
        "equity": current.equity,
        "current_risk_status": current.status,
        "current_risk": metrics,
        "risk_calculator": snapshot.calculator_version,
        "correlation_context_scope": sorted(included),
        "correlation_context_omitted_holdings": sorted(
            set(current.correlations) - included
        ),
        "proposed_risk_status": "pending_code_validation_after_target_set",
        "positions": [
            {
                "symbol": p.symbol,
                "quantity": p.quantity,
                "cost_basis": p.cost_basis,
                "closing_reference": (
                    assets[p.symbol].mark if p.symbol in assets else None
                ),
                "currency": assets[p.symbol].currency if p.symbol in assets else None,
                "sector": assets[p.symbol].sector if p.symbol in assets else None,
                "current_account_weight": current.position_weights.get(p.symbol),
            }
            for p in snapshot.positions
        ],
        "candidate_inputs": [
            {
                "symbol": symbol,
                "closing_reference": assets[symbol].mark if symbol in assets else None,
                "mark_session": (
                    str(assets[symbol].mark_session)
                    if symbol in assets and assets[symbol].mark_session
                    else None
                ),
                "currency": assets[symbol].currency if symbol in assets else None,
                "sector": assets[symbol].sector if symbol in assets else None,
                "beta": assets[symbol].beta if symbol in assets else None,
                "return_observations": (
                    len(assets[symbol].returns) if symbol in assets else None
                ),
                "history_errors": (
                    assets[symbol].errors
                    if symbol in assets
                    else ["ASSET_INPUT_UNAVAILABLE"]
                ),
            }
            for symbol in symbols
        ],
    }
    limits: dict[str, object] = {
        "risk_policy_revision": snapshot.policy.revision,
        "risk_policy": (
            snapshot.policy.policy.model_dump(
                mode="json", exclude={"risk_per_trade_weight"}
            )
            if snapshot.policy.policy
            else None
        ),
        "max_account_sigma": policy.policy.max_account_sigma,
        "allocation_calculator": policy.allocation_calculator or "idq-002@1",
        "target_equity_basis": (
            "post_cost" if policy.allocation_calculator else "pre_cost"
        ),
        "stop_risk_applicability": "not_applicable_target_only_no_stop_plan_or_max_loss_bound",
        "unfilled_sell_proceeds_are_buying_power": False,
    }
    return payload, limits
