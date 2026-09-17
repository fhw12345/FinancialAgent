"""Synthetic test constraints, never application/user defaults."""

from datetime import UTC, datetime, date
from src.models.portfolio_risk import (
    PortfolioRiskSnapshot,
    RiskPosition,
    RiskAsset,
    SessionReturn,
    RiskPolicy,
    PolicyState,
)
from src.services.portfolio_risk.calendar import sessions

ASOF = date(2026, 9, 16)


def policy(**changes):
    return PolicyState(
        revision=1,
        confirmed_at=datetime(2026, 9, 16, tzinfo=UTC),
        policy=RiskPolicy(
            **{
                "max_position_weight": 1.0,
                "max_sector_weight": 1.0,
                "min_cash_weight": 0.0,
                "max_turnover": 2.0,
                "risk_per_trade_weight": 0.01,
                "lot_size": 0.1,
                "fee_bps": 0.0,
                "slippage_bps": 0.0,
                **changes,
            }
        ),
    )


def asset(symbol="AAPL", values=None, dates=None, **changes):
    dates = dates if dates is not None else sessions(ASOF)
    values = values if values is not None else [-0.02, 0.02] * 30
    return RiskAsset(
        symbol=symbol,
        currency="USD",
        mark=100.0,
        mark_session=ASOF,
        sector="Technology",
        beta=1.0,
        returns=[
            SessionReturn(session_date=d, total_return=float(r))
            for d, r in zip(dates, values, strict=True)
        ],
        **changes,
    )


def snapshot(cash=9000.0, holdings=None, assets=None, confirmed=None):
    holdings = {"AAPL": 10.0} if holdings is None else holdings
    return PortfolioRiskSnapshot(
        account_revision="fixture",
        captured_at=datetime(2026, 9, 16, 21, tzinfo=UTC),
        session_date=ASOF,
        cash=float(cash),
        positions=[
            RiskPosition(symbol=s, quantity=float(q), cost_basis=float(q * 90))
            for s, q in holdings.items()
        ],
        assets=assets if assets is not None else [asset(s) for s in holdings],
        policy=confirmed or PolicyState(),
    )
