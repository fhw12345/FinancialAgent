"""W2.5 unit tests — risk_calculator math correctness.

Hand-computed reference values for a deterministic 3-position fixture
make the assertions reproducible. The PRD AC requires sector_exposure /
HHI / beta_weighted within 1e-6 of hand math.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from src.agent.portfolio.risk_calculator import (
    compute_portfolio_risk,
    render_risk_block_for_prompt,
)


def _h(symbol: str, qty: int, px: float):
    return SimpleNamespace(
        symbol=symbol,
        quantity=qty,
        current_price=px,
        market_value=qty * px,
    )


# 3-position fixture used by multiple tests.
HOLDINGS = [
    _h("AAPL", 10, 200.0),  # mv 2000, sector Tech, beta 1.2
    _h("NVDA", 5, 400.0),  # mv 2000, sector Tech, beta 1.6
    _h("XOM", 20, 100.0),  # mv 2000, sector Energy, beta 0.9
]
CASH = 0.0  # simplifies the hand math: all weights 1/3
META = {
    "AAPL": {"sector": "Tech", "beta": 1.2},
    "NVDA": {"sector": "Tech", "beta": 1.6},
    "XOM": {"sector": "Energy", "beta": 0.9},
}


async def _meta_fetcher(sym: str):
    return META[sym]


# ---------------------------------------------------------------------------
# Sector exposure / HHI / beta-weighted (no returns fetcher)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sector_exposure_pct_matches_hand_math() -> None:
    risk = await compute_portfolio_risk(HOLDINGS, cash=CASH, fetch_meta=_meta_fetcher)
    # Total equity = 6000; AAPL+NVDA = 4000 (Tech 66.67%); XOM 2000 (Energy 33.33%)
    sec = risk["sector_exposure"]
    assert sec["Tech"]["dollars"] == pytest.approx(4000.0, abs=1e-6)
    assert sec["Tech"]["pct_of_equity"] == pytest.approx(2 / 3, abs=1e-4)
    assert sec["Energy"]["dollars"] == pytest.approx(2000.0, abs=1e-6)
    assert sec["Energy"]["pct_of_equity"] == pytest.approx(1 / 3, abs=1e-4)


@pytest.mark.asyncio
async def test_hhi_three_equal_weights() -> None:
    risk = await compute_portfolio_risk(HOLDINGS, cash=CASH, fetch_meta=_meta_fetcher)
    # Equal 1/3 weights -> HHI = 3 * (1/3)^2 = 1/3
    assert risk["position_concentration_hhi"] == pytest.approx(1 / 3, abs=1e-4)


@pytest.mark.asyncio
async def test_beta_weighted_exposure_matches_hand_math() -> None:
    risk = await compute_portfolio_risk(HOLDINGS, cash=CASH, fetch_meta=_meta_fetcher)
    # 1/3 * 1.2 + 1/3 * 1.6 + 1/3 * 0.9 = (1.2+1.6+0.9)/3 = 1.2333...
    assert risk["beta_weighted_exposure"] == pytest.approx(
        (1.2 + 1.6 + 0.9) / 3, abs=1e-4
    )


@pytest.mark.asyncio
async def test_cash_pct_with_nonzero_cash() -> None:
    risk = await compute_portfolio_risk(HOLDINGS, cash=2000.0, fetch_meta=_meta_fetcher)
    # Total equity = 8000, cash = 2000 -> 25%
    assert risk["cash_pct"] == pytest.approx(0.25, abs=1e-6)
    # Sector pct now scales to total_equity, not invested_value
    assert risk["sector_exposure"]["Tech"]["pct_of_equity"] == pytest.approx(
        4000 / 8000, abs=1e-6
    )


@pytest.mark.asyncio
async def test_largest_position_correct() -> None:
    # Make NVDA dominant
    holdings = [
        _h("AAPL", 1, 100.0),
        _h("NVDA", 10, 1000.0),  # 10000
        _h("XOM", 1, 100.0),
    ]
    risk = await compute_portfolio_risk(holdings, cash=0.0, fetch_meta=_meta_fetcher)
    assert risk["largest_position"]["symbol"] == "NVDA"
    assert risk["largest_position"]["weight"] == pytest.approx(10000 / 10200, abs=1e-4)


# ---------------------------------------------------------------------------
# Missing data handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_beta_assumed_one_and_reported() -> None:
    async def meta(sym: str):
        if sym == "NVDA":
            return {"sector": "Tech"}  # no beta
        return META[sym]

    risk = await compute_portfolio_risk(HOLDINGS, cash=CASH, fetch_meta=meta)
    assert "NVDA" in risk["assumed_beta_for"]
    # AAPL+NVDA = (1.2 + 1.0)/3, XOM = 0.9/3 -> (1.2+1.0+0.9)/3 = 1.0333
    assert risk["beta_weighted_exposure"] == pytest.approx(
        (1.2 + 1.0 + 0.9) / 3, abs=1e-4
    )


@pytest.mark.asyncio
async def test_missing_sector_bucketed_unknown() -> None:
    async def meta(sym: str):
        if sym == "XOM":
            return {"beta": 0.9}  # no sector
        return META[sym]

    risk = await compute_portfolio_risk(HOLDINGS, cash=CASH, fetch_meta=meta)
    assert "Unknown" in risk["sector_exposure"]
    assert risk["sector_exposure"]["Unknown"]["dollars"] == pytest.approx(2000.0)


@pytest.mark.asyncio
async def test_empty_holdings_returns_sentinel() -> None:
    risk = await compute_portfolio_risk([], cash=1000.0, fetch_meta=_meta_fetcher)
    assert risk["error"] == "no_positions"
    assert risk["cash_pct"] == 1.0
    assert risk["correlation_matrix"] is None


# ---------------------------------------------------------------------------
# Correlation + portfolio_sigma
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_correlation_perfect_when_returns_identical() -> None:
    # Two perfectly correlated synthetic series of length 60
    series_a = [0.01 * ((-1) ** i) for i in range(60)]
    series_b = list(series_a)  # identical

    async def returns(sym: str):
        return series_a if sym == "AAPL" else series_b

    holdings = [_h("AAPL", 10, 100.0), _h("NVDA", 10, 100.0)]
    meta = {
        "AAPL": {"sector": "Tech", "beta": 1.0},
        "NVDA": {"sector": "Tech", "beta": 1.0},
    }

    async def m(s: str):
        return meta[s]

    risk = await compute_portfolio_risk(
        holdings, cash=0.0, fetch_meta=m, fetch_returns=returns
    )
    cm = risk["correlation_matrix"]
    assert cm is not None
    assert cm["AAPL"]["NVDA"] == pytest.approx(1.0, abs=1e-4)
    assert cm["NVDA"]["AAPL"] == pytest.approx(1.0, abs=1e-4)
    # Self-correlation always 1
    assert cm["AAPL"]["AAPL"] == pytest.approx(1.0, abs=1e-4)


@pytest.mark.asyncio
async def test_correlation_excluded_when_history_short() -> None:
    async def returns(sym: str):
        return [0.01] * 5  # too short, < 30

    holdings = [_h("AAPL", 1, 100.0)]

    async def m(_s: str):
        return {"sector": "Tech", "beta": 1.0}

    risk = await compute_portfolio_risk(
        holdings, cash=0.0, fetch_meta=m, fetch_returns=returns
    )
    excluded = risk["correlation_excluded"]
    assert any(e["symbol"] == "AAPL" for e in excluded)
    assert risk["correlation_matrix"] is None


@pytest.mark.asyncio
async def test_portfolio_sigma_positive_for_volatile_series() -> None:
    """A series with daily σ ≈ 1% should produce annualised σ ≈ 0.16."""
    series = [0.01 * ((-1) ** i) for i in range(60)]  # ±1% alternating

    async def returns(_s: str):
        return series

    holdings = [_h("AAPL", 1, 100.0)]

    async def m(_s: str):
        return {"sector": "Tech", "beta": 1.0}

    risk = await compute_portfolio_risk(
        holdings, cash=0.0, fetch_meta=m, fetch_returns=returns
    )
    # daily σ = 0.01 * sqrt(60/59) ≈ 0.01008; annualised ≈ 0.01008 * sqrt(252) ≈ 0.16
    sigma = risk["portfolio_sigma_annualised"]
    assert sigma is not None
    assert 0.14 < sigma < 0.18


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_renderer_includes_key_metrics() -> None:
    risk = await compute_portfolio_risk(HOLDINGS, cash=2000.0, fetch_meta=_meta_fetcher)
    md = render_risk_block_for_prompt(risk)
    assert "Portfolio Risk" in md
    assert "cash_pct: 25.00%" in md
    assert "Tech" in md
    assert "Energy" in md
    assert "beta_weighted_exposure" in md
    assert "position_concentration_hhi" in md


def test_renderer_no_positions_returns_empty_marker() -> None:
    md = render_risk_block_for_prompt({"error": "no_positions"})
    assert "No positions" in md


@pytest.mark.asyncio
async def test_renderer_flags_assumed_beta() -> None:
    async def meta(sym: str):
        return {"sector": "Tech"}  # no beta for any symbol

    risk = await compute_portfolio_risk(HOLDINGS, cash=0.0, fetch_meta=meta)
    md = render_risk_block_for_prompt(risk)
    assert "Beta assumed" in md
    assert "AAPL" in md and "NVDA" in md and "XOM" in md


# Sanity: math constants used
def test_trading_days_per_year_is_252() -> None:
    from src.agent.portfolio.risk_calculator import _TRADING_DAYS_PER_YEAR

    assert _TRADING_DAYS_PER_YEAR == 252


def test_sigma_annualization_uses_sqrt_252() -> None:
    # Documents the annualization convention so a future change is loud.
    assert math.isclose(math.sqrt(252), 15.8745, abs_tol=1e-3)
