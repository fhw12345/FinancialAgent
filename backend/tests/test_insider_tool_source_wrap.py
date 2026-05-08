"""W3.5 unit tests — finnhub_insider_trades emits Source-style footnote.

Pattern mirrors W3.4 (news): one tool, primary provider attribution
("finnhub" — the primary in DataManager._fetch_insider_trades), asof
pulled from the latest *transaction* date across the returned rows
(not now()), so a stale bucket cited tomorrow still reads as stale in
the footnote.

Footnote shape: ``Source: finnhub [FH-INS-AAPL-2026-05-09] asof <iso>``
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent.tools.finnhub.insider import (
    _insider_latest_asof,
    _insider_source_id,
    _parse_row_date,
    _row_date_str,
    create_finnhub_insider_tool,
)


# ---------------------------------------------------------------------------
# _insider_source_id helper
# ---------------------------------------------------------------------------


def test_insider_source_id_finnhub_prefix() -> None:
    asof = datetime(2026, 5, 9, 18, 35, tzinfo=UTC)
    assert _insider_source_id("finnhub", "aapl", asof) == "FH-INS-AAPL-2026-05-09"


def test_insider_source_id_alphavantage_prefix() -> None:
    asof = datetime(2026, 5, 9, tzinfo=UTC)
    assert _insider_source_id("alphavantage", "MSFT", asof) == "AV-INS-MSFT-2026-05-09"


def test_insider_source_id_yfinance_prefix() -> None:
    asof = datetime(2026, 5, 9, tzinfo=UTC)
    assert _insider_source_id("yfinance", "TSLA", asof) == "YF-INS-TSLA-2026-05-09"


def test_insider_source_id_unknown_provider_uses_uppercased() -> None:
    asof = datetime(2026, 5, 9, tzinfo=UTC)
    assert _insider_source_id("custom", "AAPL", asof) == "CUSTOM-INS-AAPL-2026-05-09"


# ---------------------------------------------------------------------------
# _row_date_str + _parse_row_date helpers
# ---------------------------------------------------------------------------


def test_row_date_str_picks_first_present_key() -> None:
    # Finnhub-shape
    assert _row_date_str({"transactionDate": "2026-05-09", "filingDate": "2026-05-10"}) == "2026-05-09"
    # AV-shape (no transactionDate, falls through to filingDate)
    assert _row_date_str({"filingDate": "2026-05-09"}) == "2026-05-09"
    # yfinance DataFrame.to_dict shape
    assert _row_date_str({"Start Date": "2026-05-09T00:00:00"}) == "2026-05-09T00:00:00"
    # Nothing
    assert _row_date_str({"name": "Doe"}) == ""


def test_parse_row_date_handles_finnhub_iso_and_yf_shapes() -> None:
    assert _parse_row_date("2026-05-09").day == 9
    assert _parse_row_date("2026-05-09T14:30:00").hour == 14
    assert _parse_row_date("2026-05-09T14:30:00Z").hour == 14
    assert _parse_row_date("") is None
    assert _parse_row_date("garbage") is None


# ---------------------------------------------------------------------------
# _insider_latest_asof helper
# ---------------------------------------------------------------------------


def test_insider_latest_asof_picks_newest_row() -> None:
    rows = [
        {"transactionDate": "2026-05-07"},
        {"transactionDate": "2026-05-09"},  # latest
        {"transactionDate": "2026-05-08"},
    ]
    latest = _insider_latest_asof(rows)
    assert latest is not None
    assert latest.day == 9


def test_insider_latest_asof_skips_malformed_rows() -> None:
    rows = [
        {"transactionDate": "2026-05-09"},  # only valid
        {"transactionDate": ""},
        {"transactionDate": "garbage"},
        {},  # missing field
        {"name": "no date"},
    ]
    latest = _insider_latest_asof(rows)
    assert latest is not None
    assert latest.day == 9


def test_insider_latest_asof_returns_none_on_empty_or_all_bad() -> None:
    assert _insider_latest_asof([]) is None
    assert _insider_latest_asof([{"name": "x"}, {"transactionDate": "garbage"}]) is None


# ---------------------------------------------------------------------------
# finnhub_insider_trades tool
# ---------------------------------------------------------------------------


def _make_tool(rows: list[dict[str, Any]] | Exception) -> Any:  # noqa: ANN401
    dm = MagicMock()
    if isinstance(rows, Exception):
        dm.get_insider_trades = AsyncMock(side_effect=rows)
    else:
        dm.get_insider_trades = AsyncMock(return_value=rows)
    return create_finnhub_insider_tool(dm)[0]


@pytest.mark.asyncio
async def test_finnhub_insider_emits_footnote_with_latest_transaction_date() -> None:
    rows = [
        {
            "transactionDate": "2026-05-07",
            "name": "John Doe",
            "share": 1000,
            "transactionCode": "S",
        },
        {
            "transactionDate": "2026-05-09",  # latest
            "name": "Jane Roe",
            "share": 5000,
            "transactionCode": "P",
        },
        {
            "transactionDate": "2026-05-08",
            "name": "Bob",
            "share": 2000,
            "transactionCode": "S",
        },
    ]
    tool = _make_tool(rows)
    out = await tool.ainvoke({"symbol": "AAPL"})

    # Body still renders per-row detail.
    assert "Jane Roe" in out and "5000 shares (P)" in out
    # Footnote: "Source: finnhub [FH-INS-AAPL-2026-05-09] asof 2026-05-09T00:00Z"
    assert "Source: finnhub [FH-INS-AAPL-2026-05-09]" in out
    assert "asof 2026-05-09T00:00Z" in out


@pytest.mark.asyncio
async def test_finnhub_insider_emits_no_footnote_when_no_rows() -> None:
    tool = _make_tool([])
    out = await tool.ainvoke({"symbol": "TSLA"})
    assert "No recent insider transactions" in out
    assert "Source:" not in out


@pytest.mark.asyncio
async def test_finnhub_insider_emits_no_footnote_on_provider_failure() -> None:
    # If DataManager raises, the tool returns an error string — no
    # footnote (the W1.10 consistency_gate would otherwise cite a
    # "source" we never actually fetched from).
    tool = _make_tool(RuntimeError("finnhub down"))
    out = await tool.ainvoke({"symbol": "NVDA"})
    assert "Failed to fetch insider trades" in out
    assert "Source:" not in out


@pytest.mark.asyncio
async def test_finnhub_insider_handles_yfinance_shape_rows() -> None:
    """yfinance via DataFrame.to_dict() yields ``Start Date`` / ``Insider`` /
    ``Shares`` / ``Transaction`` keys — the tool must still find a date."""
    rows = [
        {
            "Start Date": "2026-05-09T00:00:00",
            "Insider": "Tim Cook",
            "Shares": 12345,
            "Transaction": "Sale",
        }
    ]
    tool = _make_tool(rows)
    out = await tool.ainvoke({"symbol": "AAPL"})
    assert "Tim Cook" in out
    assert "Source: finnhub [FH-INS-AAPL-2026-05-09]" in out
