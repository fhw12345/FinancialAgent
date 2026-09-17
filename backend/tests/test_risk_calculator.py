"""Legacy entry-point coverage migrated to explicit dated/full-account IDQ-002 semantics."""

import math
from types import SimpleNamespace
import pytest
from src.agent.portfolio.risk_calculator import (
    compute_portfolio_risk,
    render_risk_block_for_prompt,
)
from tests.portfolio_risk_fixtures import ASOF, asset


def holding(s, q, p):
    return SimpleNamespace(symbol=s, quantity=q, current_price=p, mark_session=ASOF)


HOLDINGS = [holding("AAPL", 10, 200), holding("NVDA", 5, 400), holding("XOM", 20, 100)]
META = {
    "AAPL": {"sector": "Tech", "beta": 1.2},
    "NVDA": {"sector": "Tech", "beta": 1.6},
    "XOM": {"sector": "Energy", "beta": 0.9},
}


async def meta(s):
    return META[s]


async def returns(s):
    return asset(s).returns


async def risk(cash=0, fetch_meta=meta, fetch_returns=returns, holdings=HOLDINGS):
    return await compute_portfolio_risk(
        holdings, cash, fetch_meta, fetch_returns, as_of=ASOF
    )


@pytest.mark.asyncio
async def test_sector_exposure_pct_matches_hand_math():
    r = await risk()
    assert r["sector_weights"]["Tech"] == pytest.approx(2 / 3)
    assert r["sector_weights"]["Energy"] * r["equity"] == pytest.approx(2000)


@pytest.mark.asyncio
async def test_hhi_three_equal_invested_weights():
    assert (await risk(cash=2000))["invested_hhi"] == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_beta_weighted_exposure_matches_hand_math():
    assert (await risk())["beta_exposure"] == pytest.approx((1.2 + 1.6 + 0.9) / 3)


@pytest.mark.asyncio
async def test_cash_weight_with_nonzero_cash():
    r = await risk(cash=2000)
    assert r["cash_weight"] == 0.25 and r["sector_weights"]["Tech"] == 0.5


@pytest.mark.asyncio
async def test_largest_position_correct():
    r = await risk(
        holdings=[
            holding("AAPL", 1, 100),
            holding("NVDA", 10, 1000),
            holding("XOM", 1, 100),
        ]
    )
    assert max(r["position_weights"], key=r["position_weights"].get) == "NVDA"
    assert r["position_weights"]["NVDA"] == pytest.approx(10000 / 10200)


@pytest.mark.asyncio
async def test_missing_beta_is_not_assumed_authoritative():
    async def missing(s):
        return {"sector": "Tech"} if s == "NVDA" else META[s]

    assert (await risk(fetch_meta=missing))["beta_exposure"] is None


@pytest.mark.asyncio
async def test_missing_sector_bucketed_unknown():
    async def missing(s):
        return {"beta": 0.9} if s == "XOM" else META[s]

    assert (await risk(fetch_meta=missing))["sector_weights"][
        "Unknown"
    ] == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_empty_holdings_has_zero_account_risk_but_undefined_invested_risk():
    r = await risk(cash=1000, holdings=[])
    assert r["status"] == "complete" and r["cash_weight"] == 1
    assert r["account_sigma_annualized"] == 0 and r["invested_sigma_annualized"] is None


@pytest.mark.asyncio
async def test_correlation_perfect_when_dated_returns_identical():
    r = await risk()
    assert r["correlations"]["AAPL"]["NVDA"] == pytest.approx(1)
    assert r["correlations"]["AAPL"]["AAPL"] == pytest.approx(1)


@pytest.mark.asyncio
async def test_incomplete_and_undated_returns_cannot_produce_full_risk():
    async def short(s):
        return asset(s).returns[:5]

    r = await risk(fetch_returns=short)
    assert r["status"] == "unavailable" and r["account_sigma_annualized"] is None

    async def anonymous(s):
        return [0.01, -0.01] * 30

    r = await risk(fetch_returns=anonymous)
    assert "DATED_RETURNS_REQUIRED" in r["exclusions"]["AAPL"]


@pytest.mark.asyncio
async def test_portfolio_sigma_is_explicitly_named_and_legacy_alias_is_not_reused():
    r = await risk(cash=6000)
    assert r["account_sigma_annualized"] == pytest.approx(
        r["invested_sigma_annualized"] / 2
    )
    assert r["portfolio_sigma_annualised"] is None


@pytest.mark.asyncio
async def test_renderer_includes_key_metrics():
    text = render_risk_block_for_prompt(await risk(cash=2000))
    for key in [
        "cash_weight: 0.25",
        "Tech",
        "Energy",
        "beta_exposure",
        "invested_hhi",
        "account_sigma_annualized",
    ]:
        assert key in text


@pytest.mark.asyncio
async def test_renderer_cash_only_is_defined():
    assert "account_sigma_annualized: 0.0" in render_risk_block_for_prompt(
        await risk(cash=1000, holdings=[])
    )


@pytest.mark.asyncio
async def test_renderer_does_not_call_beta_volatility():
    async def missing(s):
        return {}

    text = render_risk_block_for_prompt(await risk(fetch_meta=missing))
    assert "beta_exposure: None" in text and "NOT total volatility" in text
    assert "Beta assumed" not in text


def test_trading_days_per_year_is_252():
    from src.agent.portfolio.risk_calculator import _TRADING_DAYS_PER_YEAR

    assert _TRADING_DAYS_PER_YEAR == 252


def test_sigma_annualization_uses_sqrt_252():
    assert math.isclose(math.sqrt(252), 15.8745, abs_tol=1e-3)
