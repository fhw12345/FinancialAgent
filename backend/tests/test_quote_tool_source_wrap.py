"""W3.2 unit tests — quote tool emits a Source-style footnote citation.

The Phase1 LangChain tool returns a markdown string that the LLM reads
inline. After W3.2, that string must include a stable provenance line:

    Source: yfinance [YF-Q-AAPL-2026-05-09] asof 2026-05-09T18:35Z

The token in brackets is what the W3.6 Phase2 prompt will require thesis
bullets to cite, and what the W3.7 frontend ReportRenderer will look up
to build the footnote list. These tests pin three things:

  1. The tool emits the footnote line for each provider (yfinance,
     finnhub, alphavantage) with the right prefix.
  2. The footnote ID format is stable: ``{PREFIX}-Q-{SYMBOL}-{YYYY-MM-DD}``.
  3. When DataManager doesn't carry source/asof (legacy cached row),
     the tool falls back gracefully — it MUST NOT emit a malformed
     footnote.

We also test the small ``_quote_source_id`` helper directly so a future
typo in the prefix table fails loud.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.tools.alpha_vantage.quotes import (
    _quote_source_id,
    create_quote_tools,
)


# ---------------------------------------------------------------------------
# _quote_source_id helper — direct unit coverage
# ---------------------------------------------------------------------------


def test_quote_source_id_yfinance_prefix() -> None:
    asof = datetime(2026, 5, 9, 18, 35, tzinfo=UTC)
    assert _quote_source_id("yfinance", "aapl", asof) == "YF-Q-AAPL-2026-05-09"


def test_quote_source_id_finnhub_prefix() -> None:
    asof = datetime(2026, 5, 9, tzinfo=UTC)
    assert _quote_source_id("finnhub", "NVDA", asof) == "FH-Q-NVDA-2026-05-09"


def test_quote_source_id_alphavantage_prefix() -> None:
    asof = datetime(2026, 5, 9, tzinfo=UTC)
    assert _quote_source_id("alphavantage", "MSFT", asof) == "AV-Q-MSFT-2026-05-09"


def test_quote_source_id_unknown_provider_uses_uppercased_name() -> None:
    asof = datetime(2026, 5, 9, tzinfo=UTC)
    # Future provider hasn't been registered yet — fall back to upper-case
    # of the raw source name rather than crashing.
    assert _quote_source_id("polygon", "AAPL", asof) == "POLYGON-Q-AAPL-2026-05-09"


def test_quote_source_id_handles_missing_source_and_asof() -> None:
    # Legacy cached QuoteData (pre-W3.2) has neither field. Tool should
    # still produce SOME id rather than raise.
    sid = _quote_source_id(None, "AAPL", None)
    assert sid.startswith("SRC-Q-AAPL-")
    assert sid.endswith(datetime.now(UTC).strftime("%Y-%m-%d"))


# ---------------------------------------------------------------------------
# get_stock_quote tool — markdown shape with footnote line
# ---------------------------------------------------------------------------


def _make_tools(qd: SimpleNamespace) -> Any:  # noqa: ANN401
    """Build the get_stock_quote tool with a stub DataManager + AV service."""
    av_service = MagicMock()
    av_service.get_market_status = AsyncMock(
        return_value={
            "current_status": "open",
            "local_time": "2026-05-09 14:35:00 EDT",
            "utc_time": "2026-05-09 18:35:00 UTC",
            "notes": "",
        }
    )
    dm = MagicMock()
    dm.get_quote = AsyncMock(return_value=qd)

    tools = create_quote_tools(av_service, data_manager=dm)
    return next(t for t in tools if t.name == "get_stock_quote")


@pytest.mark.asyncio
async def test_tool_emits_yfinance_footnote() -> None:
    asof = datetime(2026, 5, 9, 18, 35, tzinfo=UTC)
    qd = SimpleNamespace(
        symbol="AAPL",
        price=175.32,
        open=174.50,
        high=176.00,
        low=174.20,
        volume=52341000,
        change_percent=1.45,
        latest_trading_day="2026-05-09",
        previous_close=172.87,
        session="regular",
        source="yfinance",
        asof=asof,
    )
    tool = _make_tools(qd)

    out = await tool.ainvoke({"symbol": "AAPL", "region": "United States"})

    assert "[YF-Q-AAPL-2026-05-09]" in out
    assert "Source: yfinance" in out
    # asof is rendered minute-precision UTC so the consistency_gate can
    # parse it back if it ever needs to check staleness inline.
    assert "asof 2026-05-09T18:35Z" in out


@pytest.mark.asyncio
async def test_tool_emits_finnhub_footnote() -> None:
    asof = datetime(2026, 5, 9, 14, 0, tzinfo=UTC)
    qd = SimpleNamespace(
        symbol="NVDA",
        price=950.10,
        open=940.0,
        high=955.0,
        low=938.0,
        volume=0,  # finnhub /quote doesn't include volume
        change_percent=2.0,
        latest_trading_day="2026-05-09",
        previous_close=931.50,
        session="regular",
        source="finnhub",
        asof=asof,
    )
    tool = _make_tools(qd)

    out = await tool.ainvoke({"symbol": "NVDA", "region": "United States"})

    assert "[FH-Q-NVDA-2026-05-09]" in out
    assert "Source: finnhub" in out


@pytest.mark.asyncio
async def test_tool_emits_alphavantage_footnote() -> None:
    asof = datetime(2026, 5, 9, tzinfo=UTC)
    qd = SimpleNamespace(
        symbol="MSFT",
        price=420.0,
        open=418.0,
        high=422.0,
        low=417.0,
        volume=20000000,
        change_percent=-0.5,
        latest_trading_day="2026-05-09",
        previous_close=422.10,
        session="regular",
        source="alphavantage",
        asof=asof,
    )
    tool = _make_tools(qd)

    out = await tool.ainvoke({"symbol": "MSFT", "region": "United States"})

    assert "[AV-Q-MSFT-2026-05-09]" in out
    assert "Source: alphavantage" in out


@pytest.mark.asyncio
async def test_tool_handles_legacy_quote_without_source_metadata() -> None:
    # Cached QuoteData written before W3.2 has no source/asof. The tool
    # should still render the regular markdown without crashing AND without
    # emitting a half-formed "Source: None [...]" line.
    qd = SimpleNamespace(
        symbol="TSLA",
        price=180.0,
        open=178.0,
        high=182.0,
        low=177.0,
        volume=10000000,
        change_percent=1.1,
        latest_trading_day="2026-05-09",
        previous_close=178.0,
        session="regular",
        source=None,
        asof=None,
    )
    tool = _make_tools(qd)

    out = await tool.ainvoke({"symbol": "TSLA", "region": "United States"})

    assert "TSLA: $180.00" in out
    # No malformed footnote line.
    assert "Source: None" not in out
    assert "Source:" not in out
