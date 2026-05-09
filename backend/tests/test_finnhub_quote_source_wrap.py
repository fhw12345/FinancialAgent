"""W3.16-A unit tests — finnhub_quote tool emits a Source-style footnote.

Backstory: W3.2 wrapped the Alpha Vantage ``get_stock_quote`` tool with a
``Source: ... [PREFIX-Q-SYMBOL-YYYY-MM-DD] asof ...`` line. The Finnhub-backed
``finnhub_quote`` tool — which the Phase1 ReAct agent also has registered
and is free to call instead — was not wrapped at the time. A real e2e run
on 2026-05-09 produced a 1749-char NVDA report with zero ``Source:`` lines
because Phase1 picked the un-wrapped path. W3.16-A closes that gap so both
quote tools emit identical footnote tokens regardless of which one the
LLM picks.

These tests pin:
  1. ``_quote_source_id`` helper produces the same shape as the AV twin.
  2. The footnote line appears for each provider the QuoteData row
     records (finnhub / yfinance / alphavantage) — important because the
     DataManager fallback chain may swap providers transparently.
  3. Legacy QuoteData rows (no ``source`` / ``asof``) silently skip the
     footnote rather than render ``Source: None [...]``.
  4. ``asof`` missing on a non-legacy row still produces a token that
     uses today's date so chip resolution doesn't crash on the frontend.
  5. Dotted symbols (e.g. BRK.B) round-trip uppercased.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.tools.finnhub.quotes import (
    _quote_source_id,
    create_finnhub_quote_tool,
)


# ---------------------------------------------------------------------------
# _quote_source_id helper
# ---------------------------------------------------------------------------


def test_quote_source_id_finnhub_prefix() -> None:
    asof = datetime(2026, 5, 9, tzinfo=UTC)
    assert _quote_source_id("finnhub", "NVDA", asof) == "FH-Q-NVDA-2026-05-09"


def test_quote_source_id_yfinance_prefix() -> None:
    asof = datetime(2026, 5, 9, 18, 35, tzinfo=UTC)
    assert _quote_source_id("yfinance", "aapl", asof) == "YF-Q-AAPL-2026-05-09"


def test_quote_source_id_alphavantage_prefix() -> None:
    asof = datetime(2026, 5, 9, tzinfo=UTC)
    assert _quote_source_id("alphavantage", "MSFT", asof) == "AV-Q-MSFT-2026-05-09"


def test_quote_source_id_dotted_symbol_uppercased() -> None:
    asof = datetime(2026, 5, 9, tzinfo=UTC)
    assert _quote_source_id("finnhub", "brk.b", asof) == "FH-Q-BRK.B-2026-05-09"


def test_quote_source_id_unknown_provider_uppercases() -> None:
    asof = datetime(2026, 5, 9, tzinfo=UTC)
    assert _quote_source_id("polygon", "AAPL", asof) == "POLYGON-Q-AAPL-2026-05-09"


def test_quote_source_id_missing_asof_uses_today() -> None:
    sid = _quote_source_id("finnhub", "AAPL", None)
    assert sid.startswith("FH-Q-AAPL-")
    assert sid.endswith(datetime.now(UTC).strftime("%Y-%m-%d"))


# ---------------------------------------------------------------------------
# finnhub_quote tool — markdown shape with footnote line
# ---------------------------------------------------------------------------


def _make_quote(
    *,
    source: str | None,
    asof: datetime | None,
    symbol: str = "NVDA",
    price: float = 215.20,
) -> SimpleNamespace:
    """Build a stub QuoteData carrying the W3.2 ``source`` / ``asof`` fields."""
    return SimpleNamespace(
        symbol=symbol,
        price=price,
        change=3.70,
        change_percent=1.75,
        open=212.10,
        high=217.80,
        low=211.05,
        previous_close=211.50,
        latest_trading_day="2026-05-09",
        session="regular",
        source=source,
        asof=asof,
    )


def _make_tool(qd: SimpleNamespace) -> object:
    """Build the finnhub_quote tool wired to a stub DataManager."""
    dm = MagicMock()
    dm.get_quote = AsyncMock(return_value=qd)
    tools = create_finnhub_quote_tool(dm)
    assert len(tools) == 1
    return tools[0]


@pytest.mark.asyncio
async def test_finnhub_quote_emits_finnhub_token() -> None:
    qd = _make_quote(
        source="finnhub", asof=datetime(2026, 5, 9, 14, 30, tzinfo=UTC)
    )
    tool = _make_tool(qd)
    out = await tool.ainvoke({"symbol": "NVDA"})
    assert "Source: finnhub [FH-Q-NVDA-2026-05-09] asof 2026-05-09T14:30Z" in out


@pytest.mark.asyncio
async def test_finnhub_quote_emits_yfinance_token_after_fallback() -> None:
    """When DataManager falls back to yfinance the QuoteData.source flips,
    and the footnote prefix MUST follow — otherwise the W3.7 frontend chip
    will resolve to the wrong provider label."""
    qd = _make_quote(
        source="yfinance", asof=datetime(2026, 5, 9, 18, 35, tzinfo=UTC)
    )
    tool = _make_tool(qd)
    out = await tool.ainvoke({"symbol": "NVDA"})
    assert "Source: yfinance [YF-Q-NVDA-2026-05-09] asof 2026-05-09T18:35Z" in out


@pytest.mark.asyncio
async def test_finnhub_quote_emits_alphavantage_token_after_fallback() -> None:
    qd = _make_quote(
        source="alphavantage", asof=datetime(2026, 5, 9, 20, 0, tzinfo=UTC)
    )
    tool = _make_tool(qd)
    out = await tool.ainvoke({"symbol": "NVDA"})
    assert "Source: alphavantage [AV-Q-NVDA-2026-05-09] asof 2026-05-09T20:00Z" in out


@pytest.mark.asyncio
async def test_finnhub_quote_legacy_row_skips_footnote() -> None:
    """Pre-W3.2 cached QuoteData has no ``source``. Rather than render
    ``Source: None [SRC-Q-...]`` we want the line silently omitted so the
    LLM doesn't see noise. Other body content must still be intact."""
    qd = _make_quote(source=None, asof=None)
    tool = _make_tool(qd)
    out = await tool.ainvoke({"symbol": "NVDA"})
    assert "Source:" not in out
    assert "NVDA: $215.20" in out  # body still rendered


@pytest.mark.asyncio
async def test_finnhub_quote_missing_asof_falls_back_to_today() -> None:
    """``source`` present but ``asof`` missing — the footnote still emits,
    using ``asof unknown`` for the timestamp and today's date in the ID."""
    qd = _make_quote(source="finnhub", asof=None)
    tool = _make_tool(qd)
    out = await tool.ainvoke({"symbol": "NVDA"})
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    assert f"Source: finnhub [FH-Q-NVDA-{today}] asof asof unknown" in out


@pytest.mark.asyncio
async def test_finnhub_quote_dotted_symbol_uppercased_in_id() -> None:
    qd = _make_quote(
        source="finnhub",
        asof=datetime(2026, 5, 9, tzinfo=UTC),
        symbol="BRK.B",
    )
    tool = _make_tool(qd)
    out = await tool.ainvoke({"symbol": "brk.b"})
    assert "[FH-Q-BRK.B-2026-05-09]" in out


@pytest.mark.asyncio
async def test_finnhub_quote_failure_skips_footnote() -> None:
    dm = MagicMock()
    dm.get_quote = AsyncMock(side_effect=RuntimeError("upstream timeout"))
    tools = create_finnhub_quote_tool(dm)
    out = await tools[0].ainvoke({"symbol": "NVDA"})
    assert "Failed to fetch quote for NVDA" in out
    assert "Source:" not in out
