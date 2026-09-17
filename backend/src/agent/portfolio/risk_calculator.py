"""Compatibility entry point for versioned full-account risk; old sigma is not relabeled."""

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any, TypedDict

from ...models.portfolio_risk import (
    PortfolioRiskSnapshot,
    RiskAsset,
    RiskMetrics,
    RiskPosition,
    SessionReturn,
)
from ...services.portfolio_risk.calendar import completed_session
from ...services.portfolio_risk.estimator import estimate

_TRADING_DAYS_PER_YEAR = 252


class SymbolMeta(TypedDict, total=False):
    sector: str | None
    beta: float | None


MetaFetcher = Callable[[str], Awaitable[SymbolMeta]]
ReturnsFetcher = Callable[[str], Awaitable[list[SessionReturn]]]


async def compute_portfolio_risk(
    holdings: list[Any],
    cash: float,
    fetch_meta: MetaFetcher,
    fetch_returns: ReturnsFetcher | None = None,
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    session = as_of or completed_session(datetime.now(UTC))
    assets = []
    positions = []
    for h in holdings:
        positions.append(
            RiskPosition(
                symbol=h.symbol,
                quantity=float(h.quantity),
                cost_basis=float(getattr(h, "cost_basis", 0) or 0),
            )
        )
        try:
            meta = await fetch_meta(h.symbol)
        except Exception:
            meta = {}
        try:
            points = await fetch_returns(h.symbol) if fetch_returns else []
        except Exception:
            points = []
        dated = all(isinstance(p, SessionReturn) for p in points)
        price = getattr(h, "current_price", None)
        assets.append(
            RiskAsset(
                symbol=h.symbol,
                mark=price if price and price > 0 else None,
                mark_session=getattr(h, "mark_session", None),
                currency=getattr(h, "currency", "USD"),
                sector=meta.get("sector") or "Unknown",
                beta=meta.get("beta"),
                returns=points if dated else [],
                errors=[] if dated else ["DATED_RETURNS_REQUIRED"],
            )
        )
    snapshot = PortfolioRiskSnapshot(
        account_revision="legacy_context",
        captured_at=datetime.now(UTC),
        session_date=session,
        cash=cash,
        positions=positions,
        assets=assets,
    )
    result = estimate(snapshot).model_dump(mode="json")
    result["portfolio_sigma_annualised"] = None
    result["legacy_definition"] = (
        "Legacy invested-subset sigma is retired; use explicitly named account/invested metrics."
    )
    return result


def render_risk_block_for_prompt(risk: dict[str, Any]) -> str:
    if "current" in risk:
        risk = risk["current"]
    report = RiskMetrics.model_validate(
        {k: v for k, v in risk.items() if k in RiskMetrics.model_fields}
    )
    return (
        "\n".join(
            [
                "## Portfolio Risk (idq-002@1; diagnostic, not approval)",
                f"- status: {report.status}",
                f"- total_equity: {report.equity}",
                f"- cash_weight: {report.cash_weight}",
                f"- account_sigma_annualized: {report.account_sigma_annualized}",
                f"- invested_sigma_annualized: {report.invested_sigma_annualized}",
                f"- invested_hhi: {report.invested_hhi} (invested weights only; 1=one stock)",
                f"- beta_exposure: {report.beta_exposure} (benchmark sensitivity, NOT total volatility)",
                f"- position_weights: {report.position_weights}",
                f"- sector_weights: {report.sector_weights}",
                f"- common_sessions: {len(report.common_sessions)}",
                f"- exclusions: {report.exclusions}; errors: {report.errors}",
                *report.assumptions,
                "No ready/approval eligibility. Whole-batch allocation is checked by code after this model draft.",
            ]
        )
        + "\n"
    )
