"""Synthetic research assumptions, not recommended or automatically applied personal defaults."""

from datetime import UTC, datetime, date
from src.models.research_strategy import (
    StrategyParameters,
    StrategyVersion,
    ValuationInput,
)
from tests.portfolio_risk_fixtures import policy


def parameters(**changes):
    return StrategyParameters(
        **{
            "methods": ["peer_pe_annual@1", "fcff_proxy_dcf@1"],
            "peer_symbols": ["MSFT"],
            "peer_rationale": "Synthetic same-industry peer fixed before data collection",
            "discount_rate": 0.1,
            "growth_rate": 0.03,
            "terminal_growth": 0.02,
            "tax_rate": 0.2,
            "projection_years": 5,
            "valuation_discount": 0.2,
            "earnings_decline_fraction": 0.2,
            "debt_to_fcf_limit": 3.0,
            "max_financial_age_days": 400,
            "max_price_lag_sessions": 0,
            "fcff_proxy_acknowledged": True,
            **changes,
        }
    )


def version(**changes):
    return StrategyVersion(
        version_id="strategy_test",
        revision=1,
        parameters=parameters(),
        cost_policy_revision=1,
        cost_policy=policy().policy,
        confirmed_at=datetime(2026, 9, 18, tzinfo=UTC),
        request_id="test",
        input_hash="h",
        **changes,
    )


def value(metric, value, unit="USD", period="annual", symbol="AAPL"):
    return ValuationInput(
        snapshot_id="snapshot_" + symbol,
        evidence_id="ev_" + metric,
        symbol=symbol,
        metric=metric,
        value=float(value),
        unit=unit,
        period=period,
        period_end=date(2025, 12, 31) if period == "annual" else date(2026, 9, 17),
    )
