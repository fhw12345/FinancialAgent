"""W3.18 — Phase 1 quote tools must surface the extended-hours
companion print so the ReAct agent's research can name overnight moves
(e.g. "AH +0.6% after the earnings beat") and Phase 2 can cite them.

Tests cover both the AV `get_stock_quote` and the Finnhub `finnhub_quote`
tool bodies. We do NOT exercise the LLM here — only the tool output
text. The integration test
test_single_symbol_flow_real.py checks end-to-end token survival.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.data_manager.types import QuoteData


def _quote_with_companion() -> QuoteData:
    return QuoteData(
        symbol="NVDA",
        price=215.20,
        volume=10_000_000,
        latest_trading_day="2026-05-08",
        previous_close=213.10,
        change=2.10,
        change_percent=0.985,
        open=213.50,
        high=216.00,
        low=213.00,
        session="closed",
        source="finnhub",
        asof=datetime(2026, 5, 8, 21, 0, tzinfo=UTC),
        ext_hours_price=215.05,
        ext_hours_session="post",
        ext_hours_change_percent=-0.07,
        ext_hours_asof=datetime(2026, 5, 8, 23, 55, tzinfo=UTC),
    )


def _quote_without_companion() -> QuoteData:
    q = _quote_with_companion()
    q.ext_hours_price = None
    q.ext_hours_session = None
    q.ext_hours_change_percent = None
    q.ext_hours_asof = None
    return q


@pytest.mark.asyncio
async def test_finnhub_quote_renders_after_hours_line() -> None:
    from src.agent.tools.finnhub.quotes import create_finnhub_quote_tool

    dm = MagicMock()
    dm.get_quote = AsyncMock(return_value=_quote_with_companion())
    [tool] = create_finnhub_quote_tool(dm)

    out = await tool.ainvoke({"symbol": "NVDA"})

    assert "After-hours: $215.05" in out
    assert "-0.07%" in out
    assert "vs primary print" in out
    # Source token still pinned (one quote = one citation).
    assert "[FH-Q-NVDA-2026-05-08]" in out


@pytest.mark.asyncio
async def test_finnhub_quote_omits_line_when_no_companion() -> None:
    from src.agent.tools.finnhub.quotes import create_finnhub_quote_tool

    dm = MagicMock()
    dm.get_quote = AsyncMock(return_value=_quote_without_companion())
    [tool] = create_finnhub_quote_tool(dm)

    out = await tool.ainvoke({"symbol": "NVDA"})

    assert "After-hours" not in out
    assert "Pre-market" not in out


@pytest.mark.asyncio
async def test_finnhub_quote_renders_pre_market_label() -> None:
    from src.agent.tools.finnhub.quotes import create_finnhub_quote_tool

    q = _quote_with_companion()
    q.ext_hours_session = "pre"
    q.ext_hours_price = 214.80
    q.ext_hours_change_percent = -0.19

    dm = MagicMock()
    dm.get_quote = AsyncMock(return_value=q)
    [tool] = create_finnhub_quote_tool(dm)

    out = await tool.ainvoke({"symbol": "NVDA"})

    assert "Pre-market: $214.80" in out
    assert "-0.19%" in out


@pytest.mark.asyncio
async def test_av_get_stock_quote_renders_after_hours_line() -> None:
    """AV's `get_stock_quote` tool also routes through DataManager when
    one is wired in, so the same companion line must appear."""
    from src.agent.tools.alpha_vantage.quotes import create_quote_tools

    dm = MagicMock()
    dm.get_quote = AsyncMock(return_value=_quote_with_companion())
    av_service = MagicMock()
    av_service.get_market_status = AsyncMock(
        return_value={
            "current_status": "closed",
            "local_time": "21:00",
            "utc_time": "01:00Z",
            "notes": "",
        }
    )
    tools = create_quote_tools(av_service, data_manager=dm)
    # The factory may return multiple tools — pick the one named like a
    # quote tool to keep this resilient if siblings get added later.
    quote_tool = next(
        (t for t in tools if "quote" in (t.name or "").lower()), tools[0]
    )

    out = await quote_tool.ainvoke({"symbol": "NVDA"})

    assert "After-hours: $215.05" in out
    assert "-0.07%" in out
    # Provenance — AV path picks up the source from QuoteData (finnhub
    # in this fixture), so token prefix is FH-, not AV-.
    assert "[FH-Q-NVDA-2026-05-08]" in out
