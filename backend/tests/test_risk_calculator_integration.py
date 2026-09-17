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


from tests.portfolio_risk_fixtures import ASOF, asset


def _h(symbol: str, qty: int, px: float):
    return SimpleNamespace(
        symbol=symbol,
        quantity=qty,
        current_price=px,
        market_value=qty * px,
        mark_session=ASOF,
    )


# Fixed four-position test fixture; not a live account or efficacy claim.
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
    return asset(sym, values=_series(seeds[sym])).returns


@pytest.mark.asyncio
async def test_risk_block_realistic_4_position_portfolio() -> None:
    risk = await compute_portfolio_risk(
        HOLDINGS, cash=CASH, fetch_meta=_meta, fetch_returns=_returns, as_of=ASOF
    )

    # All 4 positions are tagged Technology in the META — single-sector
    # exposure should be the entire invested amount.
    invested = 2 * 290 + 3 * 207 + 1 * 419 + 5 * 130
    total_equity = invested + CASH
    assert risk["equity"] == pytest.approx(total_equity, abs=0.5)
    assert risk["sector_weights"]["Technology"] == pytest.approx(
        invested / total_equity
    )
    assert risk["cash_weight"] == pytest.approx(CASH / total_equity, abs=1e-3)

    # Beta-weighted exposure should land between 1.2 and 2.1 (clamped to
    # the largest position's beta when concentration matters); just
    # verify it's in plausible range.
    beta_w = risk["beta_exposure"]
    assert 1.0 < beta_w < 2.5

    # Correlation matrix + portfolio sigma should be populated.
    assert set(risk["correlations"]) == {"AAPL", "NVDA", "AVGO", "CRWV"}
    assert risk["account_sigma_annualized"] > 0
    assert risk["invested_sigma_annualized"] > risk["account_sigma_annualized"]


@pytest.mark.asyncio
async def test_render_risk_block_includes_metrics_for_4_positions() -> None:
    risk = await compute_portfolio_risk(
        HOLDINGS, cash=CASH, fetch_meta=_meta, fetch_returns=_returns, as_of=ASOF
    )
    md = render_risk_block_for_prompt(risk)
    # Prompt block should mention each metric the W2.6 docstring promised.
    assert "Portfolio Risk" in md
    assert "Technology" in md
    assert "beta_exposure" in md
    assert "invested_hhi" in md
    assert "cash_weight" in md
    # And it should mention the largest position by symbol.
    largest = max(risk["position_weights"], key=risk["position_weights"].get)
    assert largest in md
