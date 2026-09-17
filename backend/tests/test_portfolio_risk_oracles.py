"""IDQ-002 oracles replace the unsafe anonymous-return/subset sigma contract."""

import math
from datetime import date, timedelta, UTC, datetime
import pytest
from pydantic import ValidationError
from src.models.holding import HoldingCreate
from src.models.portfolio_risk import SessionReturn
from src.services.portfolio_risk.estimator import estimate
from src.services.portfolio_risk.calendar import sessions, completed_session
from tests.portfolio_risk_fixtures import snapshot, asset, ASOF


def test_cash_is_not_renormalized_away():
    result = estimate(snapshot())
    assert result.account_sigma_annualized == pytest.approx(0.03202, abs=1e-4)
    assert result.invested_sigma_annualized == pytest.approx(0.3202, abs=1e-4)
    assert result.invested_hhi == 1 and result.cash_weight == 0.9
    assert result.beta_exposure == 0.1


def test_fractional_holding_survives_domain_boundary():
    assert HoldingCreate(symbol="AAPL", quantity=0.5, avg_price=100).quantity == 0.5
    assert estimate(snapshot(cash=450, holdings={"AAPL": 0.5})).equity == 500


@pytest.mark.parametrize(
    "correlated,expected", [(True, 0.2), (False, 0.2 / math.sqrt(2))]
)
def test_known_covariance(correlated, expected):
    scale = 0.2 / math.sqrt(252 * 60 / 59)
    a = [x * scale for x in [-1, -1, 1, 1] * 15]
    b = a if correlated else [x * scale for x in [-1, 1, -1, 1] * 15]
    result = estimate(
        snapshot(
            cash=0,
            holdings={"AAPL": 5, "MSFT": 5},
            assets=[asset("AAPL", a), asset("MSFT", b)],
        )
    )
    assert result.account_sigma_annualized == pytest.approx(expected, abs=1e-10)


def test_only_common_dates_and_no_length_alignment():
    dates = sessions(ASOF)
    a = asset("AAPL", [-0.02, 0.02] * 15, dates[:30])
    b = asset("MSFT", [-0.02, 0.02] * 15, dates[30:])
    result = estimate(snapshot(cash=0, holdings={"AAPL": 5, "MSFT": 5}, assets=[a, b]))
    assert result.status == "unavailable" and result.account_sigma_annualized is None
    assert "INSUFFICIENT_COMMON_SESSIONS" in result.errors


@pytest.mark.parametrize(
    "fault", ["mark", "history", "future", "duplicate", "currency", "non_session"]
)
def test_required_asset_cannot_disappear_from_full_account_risk(fault):
    a = asset("MSFT")
    if fault == "mark":
        a.mark = None
    if fault == "history":
        a.returns = []
    if fault == "currency":
        a.currency = "HKD"
    if fault == "future":
        a.returns[-1] = SessionReturn(
            session_date=ASOF + timedelta(days=1), total_return=0.02
        )
    if fault == "duplicate":
        a.returns[-1] = a.returns[0]
    if fault == "non_session":
        a.returns[-1] = SessionReturn(session_date=date(2026, 9, 13), total_return=0.02)
    result = estimate(
        snapshot(cash=0, holdings={"AAPL": 5, "MSFT": 5}, assets=[asset(), a])
    )
    assert result.status == "unavailable" and result.account_sigma_annualized is None
    assert "MSFT" in result.exclusions


def test_empty_zero_constant_and_missing_beta_are_not_fabricated():
    cash = estimate(snapshot(cash=1000, holdings={}))
    assert cash.account_sigma_annualized == 0 and cash.cash_weight == 1
    assert cash.invested_sigma_annualized is None and cash.invested_hhi is None
    zero = estimate(snapshot(cash=0, holdings={}))
    assert zero.cash_weight is None and zero.status == "unavailable"
    a = asset(values=[0] * 60)
    a.beta = None
    constant = estimate(snapshot(assets=[a]))
    assert constant.account_sigma_annualized == 0
    assert (
        constant.correlations["AAPL"]["AAPL"] is None and constant.beta_exposure is None
    )


def test_calendar_holiday_early_close_and_future_cutoff():
    assert completed_session(datetime(2026, 11, 27, 18, 1, tzinfo=UTC)) == date(
        2026, 11, 27
    )
    assert completed_session(datetime(2026, 11, 27, 17, 59, tzinfo=UTC)) == date(
        2026, 11, 25
    )
    with pytest.raises(ValueError):
        sessions(date(2026, 12, 25))
    with pytest.raises(ValidationError):
        snapshot(cash=-1)
    with pytest.raises(ValidationError):
        SessionReturn(session_date=ASOF, total_return=math.nan)
