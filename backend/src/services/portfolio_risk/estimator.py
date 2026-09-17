"""Full-account sample covariance; no subset normalization or fabricated missing values."""

import math
from datetime import date

from ...models.portfolio_risk import PortfolioRiskSnapshot, RiskMetrics
from .calendar import sessions


def estimate(snapshot: PortfolioRiskSnapshot) -> RiskMetrics:
    snapshot = PortfolioRiskSnapshot.model_validate(snapshot)
    allowed = set(sessions(snapshot.session_date))
    assets = {a.symbol: a for a in snapshot.assets}
    report = RiskMetrics(status="unavailable", errors=list(snapshot.errors))
    market: dict[str, float] = {}
    returns: dict[str, dict[date, float]] = {}
    for position in sorted(snapshot.positions, key=lambda p: p.symbol):
        symbol = position.symbol
        asset = assets.get(symbol)
        reasons: list[str] = []
        if (
            asset is None
            or asset.mark is None
            or asset.mark_session != snapshot.session_date
        ):
            reasons.append("MARK_UNAVAILABLE_OR_STALE")
        elif asset.currency != "USD":
            reasons.append("CURRENCY_UNSUPPORTED")
        else:
            market[symbol] = position.quantity * asset.mark
        if asset is None:
            reasons.append("HISTORY_UNAVAILABLE")
        else:
            reasons.extend(asset.errors)
            dates = [r.session_date for r in asset.returns]
            if len(set(dates)) != len(dates):
                reasons.append("DUPLICATE_SESSION")
            if any(d > snapshot.session_date for d in dates):
                reasons.append("FUTURE_SESSION")
            if any(
                d <= snapshot.session_date
                and d not in set(sessions(snapshot.session_date, 160))
                for d in dates
            ):
                reasons.append("NON_SESSION_OR_OUT_OF_WINDOW")
            data = {
                r.session_date: r.total_return
                for r in asset.returns
                if r.session_date in allowed
            }
            if len(data) < 30:
                reasons.append("INSUFFICIENT_HISTORY")
            if not reasons:
                returns[symbol] = data
        if reasons:
            report.exclusions[symbol] = sorted(set(reasons))
    if snapshot.cash is None:
        report.errors.append("CASH_UNCONFIRMED")
    if len(market) != len(snapshot.positions) or snapshot.cash is None:
        return report
    invested = sum(market.values())
    equity = snapshot.cash + invested
    report.equity, report.invested_value = equity, invested
    if equity <= 0:
        report.errors.append("ZERO_EQUITY")
        return report
    report.cash_weight = snapshot.cash / equity
    report.position_weights = {s: mv / equity for s, mv in market.items()}
    report.invested_hhi = (
        sum((mv / invested) ** 2 for mv in market.values()) if invested else None
    )
    report.history_equity_coverage = (
        snapshot.cash + sum(market[s] for s in returns)
    ) / equity
    for symbol, weight in report.position_weights.items():
        sector = assets[symbol].sector or "Unknown"
        report.sector_weights[sector] = report.sector_weights.get(sector, 0) + weight
    if all(assets[s].beta is not None for s in market):
        report.beta_exposure = sum(
            report.position_weights[s] * float(assets[s].beta or 0) for s in market
        )
    if not market:
        report.account_sigma_annualized = 0.0
        report.status = "unavailable" if report.errors else "complete"
        return report
    if report.exclusions or report.errors:
        return report
    common = sorted(set.intersection(*(set(r) for r in returns.values())))
    report.common_sessions = common  # dates retained; never zip anonymous arrays
    if len(common) < 30:
        report.errors.append("INSUFFICIENT_COMMON_SESSIONS")
        return report
    symbols = sorted(market)
    vectors = {s: [returns[s][d] for d in common] for s in symbols}
    centered = {
        s: [x - sum(vectors[s]) / len(common) for x in vectors[s]] for s in symbols
    }
    cov = {
        a: {
            b: sum(x * y for x, y in zip(centered[a], centered[b], strict=True))
            / (len(common) - 1)
            for b in symbols
        }
        for a in symbols
    }
    report.correlations = {
        a: {
            b: (
                cov[a][b] / math.sqrt(cov[a][a] * cov[b][b])
                if cov[a][a] * cov[b][b] > 0
                else None
            )
            for b in symbols
        }
        for a in symbols
    }
    # Covariance remains full precision; display rounding happens only in the UI.
    variance = sum(
        report.position_weights[a] * report.position_weights[b] * cov[a][b]
        for a in symbols
        for b in symbols
    )
    report.account_sigma_annualized = math.sqrt(max(variance, 0) * 252)
    report.invested_sigma_annualized = (
        report.account_sigma_annualized * equity / invested
    )
    report.status = "complete"
    return report
