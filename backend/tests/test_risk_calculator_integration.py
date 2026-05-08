"""W2.12 integration — risk_calculator over a realistic 4-position fixture
mocking yfinance fetchers (so the test stays offline / hermetic) but
exercising the full async path including correlation matrix + portfolio σ.

Hand-computed expectations are anchored in the unit tests
(test_risk_calculator); this file additionally verifies that the
W2.6 prompt-render path works on the same fixture.
"""

from __future__ import annotations

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


# Realistic 4-position fixture (mirrors the user's 2026-05-07 portfolio).
HOLDINGS = [
    _h("AAPL", 2, 290.0),
    _h("NVDA", 3, 207.0),
    _h("AVGO", 1, 419.0),
    _h("CRWV", 5, 130.0),
]
CASH = 306.0
META = {
    "AAPL": {"sector": "Technology", "beta": 1.20},
    "NVDA": {"sector": "Technology", "beta": 1.65},
    "AVGO": {"sector": "Technology", "beta": 1.40},
    "CRWV": {"sector": "Technology", "beta": 2.10},
}


async def _meta(sym):
    return META[sym]


def _series(seed: int, n: int = 60) -> list[float]:
    """Deterministic returns series for tests; correlation between two
    series varies with the seed offset."""
    return [0.005 * ((-1) ** i) + 0.001 * (i % seed if seed else 0) for i in range(n)]


async def _returns(sym):
    seeds = {"AAPL": 2, "NVDA": 3, "AVGO": 4, "CRWV": 5}
    return _series(seeds[sym])


@pytest.mark.asyncio
async def test_risk_block_realistic_4_position_portfolio() -> None:
    risk = await compute_portfolio_risk(
        HOLDINGS, cash=CASH, fetch_meta=_meta, fetch_returns=_returns
    )

    # All 4 positions are tagged Technology in the META — single-sector
    # exposure should be the entire invested amount.
    invested = 2 * 290 + 3 * 207 + 1 * 419 + 5 * 130
    total_equity = invested + CASH
    assert risk["total_equity"] == pytest.approx(total_equity, abs=0.5)
    assert "Technology" in risk["sector_exposure"]
    assert risk["sector_exposure"]["Technology"]["dollars"] == pytest.approx(
        invested, abs=0.5
    )
    assert risk["cash_pct"] == pytest.approx(CASH / total_equity, abs=1e-3)

    # Beta-weighted exposure should land between 1.2 and 2.1 (clamped to
    # the largest position's beta when concentration matters); just
    # verify it's in plausible range.
    beta_w = risk["beta_weighted_exposure"]
    assert 1.0 < beta_w < 2.5

    # Correlation matrix + portfolio sigma should be populated.
    assert risk["correlation_matrix"] is not None
    assert set(risk["correlation_matrix"].keys()) == {"AAPL", "NVDA", "AVGO", "CRWV"}
    assert risk["portfolio_sigma_annualised"] is not None
    assert risk["portfolio_sigma_annualised"] > 0


@pytest.mark.asyncio
async def test_render_risk_block_includes_metrics_for_4_positions() -> None:
    risk = await compute_portfolio_risk(
        HOLDINGS, cash=CASH, fetch_meta=_meta, fetch_returns=_returns
    )
    md = render_risk_block_for_prompt(risk)
    # Prompt block should mention each metric the W2.6 docstring promised.
    assert "Portfolio Risk" in md
    assert "Technology" in md
    assert "beta_weighted_exposure" in md
    assert "position_concentration_hhi" in md
    assert "cash_pct" in md
    # And it should mention the largest position by symbol.
    largest = risk["largest_position"]["symbol"]
    assert largest in md
