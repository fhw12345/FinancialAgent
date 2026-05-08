"""W1.4 helper unit tests — yfinance fallback for fundamentals.

These tests hit live yfinance (similar to test_yfinance_adapters_parity).
They're marked @pytest.mark.integration and skipped by default. Run:

    pytest -m integration tests/test_yf_fallback.py
"""

from __future__ import annotations

import pytest

from src.agent.tools._yf_fallback import (
    fetch_balance_sheet_yf,
    fetch_cash_flow_yf,
    fetch_earnings_yf,
    fetch_insider_yf,
    fetch_overview_yf,
    unavailable_message,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_overview_aapl_has_pe_and_marketcap() -> None:
    md = await fetch_overview_yf("AAPL")
    assert md is not None
    assert "yfinance" in md
    assert "P/E" in md
    assert "Market Cap" in md
    # AAPL must have a non-em-dash market cap
    assert "$" in md


@pytest.mark.asyncio
async def test_overview_invalid_ticker_returns_none() -> None:
    md = await fetch_overview_yf("XYZFAKE9999")
    assert md is None


@pytest.mark.asyncio
async def test_cash_flow_aapl_has_operating_cf_row() -> None:
    md = await fetch_cash_flow_yf("AAPL", count=3, period="quarter")
    assert md is not None
    assert "Operating Cash Flow" in md
    assert "Free Cash Flow" in md


@pytest.mark.asyncio
async def test_balance_sheet_aapl_has_assets_row() -> None:
    md = await fetch_balance_sheet_yf("AAPL", count=3, period="quarter")
    assert md is not None
    assert "Total Assets" in md
    assert "Stockholders Equity" in md


@pytest.mark.asyncio
async def test_earnings_aapl_has_eps_history() -> None:
    md = await fetch_earnings_yf("AAPL", limit=4)
    assert md is not None
    assert "EPS Est" in md
    assert "Reported" in md


@pytest.mark.asyncio
async def test_insider_aapl_has_table() -> None:
    md = await fetch_insider_yf("AAPL", limit=10)
    # Insider data may be sparse; allow None but if present must be tabular.
    if md is not None:
        assert "Insider" in md
        assert "Transaction" in md


def test_unavailable_message_includes_symbol_and_field() -> None:
    msg = unavailable_message("CRWV", "Cash flow", av_error="rate limited")
    assert "CRWV" in msg
    assert "Cash flow" in msg
    assert "rate limited" in msg
    assert "unsubstantiated" in msg
