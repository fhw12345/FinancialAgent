"""Outer provider transport validation, with actual date/adjustment adapter execution."""

import pandas as pd
import pytest
from types import SimpleNamespace
from datetime import date
from src.services.portfolio_risk import provider
from src.services.portfolio_risk.calendar import sessions
from tests.portfolio_risk_fixtures import ASOF


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,expected",
    [
        ("good", None),
        ("gap", None),
        ("missing", "ADJUSTED_HISTORY_UNAVAILABLE"),
        ("duplicate", "INVALID_PROVIDER_SESSIONS"),
        ("future", "INVALID_PROVIDER_SESSIONS"),
        ("non_session", "NON_SESSION_PROVIDER_DATA"),
        ("zero", "PROVIDER_UNAVAILABLE_OR_INVALID"),
        ("exception", "PROVIDER_UNAVAILABLE_OR_INVALID"),
    ],
)
async def test_adapter_retains_dates_and_rejects_bad_transport_receipts(
    monkeypatch, mode, expected
):
    dates = pd.to_datetime(sessions(ASOF, 61))
    frame = pd.DataFrame(
        {"Close": [100.0] * 61, "Adj Close": [100.0 + i for i in range(61)]},
        index=dates,
    )
    if mode == "gap":
        frame = frame.drop(dates[15])
    if mode == "missing":
        frame = frame.drop(columns=["Adj Close"])
    if mode == "duplicate":
        frame.index = pd.DatetimeIndex([*dates[:-1], dates[0]])
    if mode == "future":
        frame.index = pd.DatetimeIndex([*dates[:-1], pd.Timestamp(date(2026, 9, 17))])
    if mode == "non_session":
        frame.index = pd.DatetimeIndex([*dates[:-1], pd.Timestamp(date(2026, 9, 13))])
    if mode == "zero":
        frame.iloc[-1, 0] = 0

    def history(**kwargs):
        assert kwargs["auto_adjust"] is False and kwargs["interval"] == "1d"
        if mode == "exception":
            raise RuntimeError("outer unavailable")
        return frame

    ticker = SimpleNamespace(
        info={
            "currency": "USD",
            "quoteType": "EQUITY",
            "sector": "Technology",
            "beta": 1.0,
        },
        history=history,
    )
    monkeypatch.setattr(provider.yf, "Ticker", lambda symbol: ticker)
    result = await provider.fetch_asset("AAPL", ASOF)
    if expected:
        assert result.errors == [expected]
    else:
        assert not result.errors and result.mark == 100 and result.mark_session == ASOF
        assert len(result.returns) == (58 if mode == "gap" else 60)
        if mode == "gap":
            assert dates[16].date() not in {r.session_date for r in result.returns}
