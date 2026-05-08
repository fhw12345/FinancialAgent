"""W3.3 unit tests — fundamentals tools emit Source-style footnotes.

The AlphaVantage `@tool` wrappers in
``src/agent/tools/alpha_vantage/fundamentals.py`` must each append a
single provenance line at the bottom of their markdown:

    Source: alphavantage [AV-OV-AAPL-2025-09-30] asof 2025-09-30T00:00Z
    Source: yfinance     [YF-CF-MRVL-2026-05-09] asof 2026-05-09T18:35Z
    Source: alphavantage [AV-EAR-MSFT-2026-04-25] asof 2026-04-25T00:00Z

W3.6 Phase2 prompt will require thesis bullets to cite the bracketed
ID; W3.7 frontend resolves the ID into a footnote chip. These tests
pin three things per tool:

  1. Happy AV path emits ``Source: alphavantage [AV-{FIELD}-...]``.
  2. yfinance fallback path emits ``Source: yfinance [YF-{FIELD}-...]``
     (i.e. the wrapper knows which provider it actually used, even
     though the formatter is unchanged).
  3. The asof in the footnote ID matches the truthful date AV gave us
     (``LatestQuarter`` for OV, ``fiscalDateEnding`` for CF/BS,
     ``reportedDate`` for EAR, ``transaction_date`` for INS), not
     ``datetime.now()``.

The unavailable-both-paths return is unchanged and tested in
``test_data_manager_fallback.py``; we don't re-cover it here.
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.tools.alpha_vantage.fundamentals import (
    _fundamentals_source_id,
    _parse_av_date,
    _statement_asof,
    create_fundamental_tools,
)


# ---------------------------------------------------------------------------
# Helpers — direct unit coverage
# ---------------------------------------------------------------------------


def test_fundamentals_source_id_av_overview() -> None:
    from datetime import UTC, datetime

    asof = datetime(2025, 9, 30, tzinfo=UTC)
    sid = _fundamentals_source_id(
        source="alphavantage", symbol="aapl", field_code="OV", asof=asof
    )
    assert sid == "AV-OV-AAPL-2025-09-30"


def test_fundamentals_source_id_yfinance_balance_sheet() -> None:
    from datetime import UTC, datetime

    asof = datetime(2026, 3, 31, tzinfo=UTC)
    sid = _fundamentals_source_id(
        source="yfinance", symbol="NVDA", field_code="BS", asof=asof
    )
    assert sid == "YF-BS-NVDA-2026-03-31"


def test_parse_av_date_iso_string() -> None:
    from datetime import UTC

    parsed = _parse_av_date("2025-09-30")
    assert parsed is not None
    assert parsed.year == 2025 and parsed.month == 9 and parsed.day == 30
    assert parsed.tzinfo == UTC


def test_parse_av_date_handles_missing_and_malformed() -> None:
    assert _parse_av_date(None) is None
    assert _parse_av_date("") is None
    assert _parse_av_date("not-a-date") is None
    assert _parse_av_date(20250930) is None  # numeric, not a string


def test_statement_asof_picks_quarterly_first() -> None:
    data = {
        "annualReports": [{"fiscalDateEnding": "2024-12-31"}],
        "quarterlyReports": [
            {"fiscalDateEnding": "2025-06-30"},
            {"fiscalDateEnding": "2025-03-31"},
        ],
    }
    q = _statement_asof(data, period="quarter")
    assert q is not None and q.day == 30 and q.month == 6
    a = _statement_asof(data, period="year")
    assert a is not None and a.day == 31 and a.month == 12


def test_statement_asof_returns_none_on_empty() -> None:
    assert _statement_asof(None, period="quarter") is None
    assert _statement_asof({}, period="quarter") is None
    assert _statement_asof({"quarterlyReports": []}, period="quarter") is None


# ---------------------------------------------------------------------------
# Tool fixtures
# ---------------------------------------------------------------------------


def _make_tool(name: str, *, service: MagicMock, formatter: MagicMock) -> Any:  # noqa: ANN401
    tools = create_fundamental_tools(service, formatter)
    return next(t for t in tools if t.name == name)


# ---------------------------------------------------------------------------
# get_company_overview
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_av_path_emits_alphavantage_footnote() -> None:
    service = MagicMock()
    service.get_company_overview = AsyncMock(
        return_value={"Symbol": "AAPL", "LatestQuarter": "2025-09-30"}
    )
    formatter = MagicMock()
    formatter.format_company_overview = MagicMock(return_value="OVERVIEW BODY")

    tool = _make_tool("get_company_overview", service=service, formatter=formatter)
    out = await tool.ainvoke({"symbol": "AAPL"})

    assert out.startswith("OVERVIEW BODY")
    assert "Source: alphavantage [AV-OV-AAPL-2025-09-30]" in out
    assert re.search(r"asof 2025-09-30T\d\d:\d\dZ", out)


@pytest.mark.asyncio
async def test_overview_yf_fallback_emits_yfinance_footnote() -> None:
    service = MagicMock()
    # AV returns empty (W1.5 fallback path).
    service.get_company_overview = AsyncMock(return_value={})
    formatter = MagicMock()

    tool = _make_tool("get_company_overview", service=service, formatter=formatter)
    with patch(
        "src.agent.tools.alpha_vantage.fundamentals.fetch_overview_yf",
        new=AsyncMock(return_value="YF OVERVIEW BODY"),
    ):
        out = await tool.ainvoke({"symbol": "NVDA"})

    assert out.startswith("YF OVERVIEW BODY")
    # Source label is yfinance even though the AV branch was attempted.
    assert "Source: yfinance [YF-OV-NVDA-" in out


# ---------------------------------------------------------------------------
# get_financial_statements (cash_flow + balance_sheet)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cash_flow_av_path_uses_fiscal_date_ending() -> None:
    service = MagicMock()
    service.get_cash_flow = AsyncMock(
        return_value={
            "symbol": "MRVL",
            "quarterlyReports": [
                {"fiscalDateEnding": "2026-04-30"},
                {"fiscalDateEnding": "2026-01-31"},
            ],
        }
    )
    formatter = MagicMock()
    formatter.format_cash_flow = MagicMock(return_value="CASH FLOW BODY")

    tool = _make_tool(
        "get_financial_statements", service=service, formatter=formatter
    )
    out = await tool.ainvoke(
        {
            "symbol": "MRVL",
            "statement_type": "cash_flow",
            "count": 3,
            "period": "quarter",
        }
    )

    assert "CASH FLOW BODY" in out
    assert "Source: alphavantage [AV-CF-MRVL-2026-04-30]" in out


@pytest.mark.asyncio
async def test_balance_sheet_yf_fallback_emits_yfinance_footnote() -> None:
    service = MagicMock()
    service.get_balance_sheet = AsyncMock(return_value=None)
    formatter = MagicMock()

    tool = _make_tool(
        "get_financial_statements", service=service, formatter=formatter
    )
    with patch(
        "src.agent.tools.alpha_vantage.fundamentals.fetch_balance_sheet_yf",
        new=AsyncMock(return_value="YF BS BODY"),
    ):
        out = await tool.ainvoke(
            {
                "symbol": "TSLA",
                "statement_type": "balance_sheet",
                "count": 3,
                "period": "quarter",
            }
        )

    assert "YF BS BODY" in out
    assert "Source: yfinance [YF-BS-TSLA-" in out


# ---------------------------------------------------------------------------
# get_company_earnings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_earnings_av_path_uses_reported_date() -> None:
    service = MagicMock()
    service.get_earnings = AsyncMock(
        return_value={
            "symbol": "MSFT",
            "quarterlyEarnings": [
                {"reportedDate": "2026-04-25", "fiscalDateEnding": "2026-03-31"},
            ],
        }
    )
    formatter = MagicMock()
    formatter.format_earnings = MagicMock(return_value="EARNINGS BODY")

    tool = _make_tool("get_company_earnings", service=service, formatter=formatter)
    out = await tool.ainvoke({"symbol": "MSFT"})

    assert "EARNINGS BODY" in out
    # reportedDate wins over fiscalDateEnding.
    assert "Source: alphavantage [AV-EAR-MSFT-2026-04-25]" in out


@pytest.mark.asyncio
async def test_earnings_av_falls_back_to_fiscal_when_reported_missing() -> None:
    service = MagicMock()
    service.get_earnings = AsyncMock(
        return_value={
            "symbol": "GOOG",
            "quarterlyEarnings": [{"fiscalDateEnding": "2026-06-30"}],
        }
    )
    formatter = MagicMock()
    formatter.format_earnings = MagicMock(return_value="EARNINGS BODY")

    tool = _make_tool("get_company_earnings", service=service, formatter=formatter)
    out = await tool.ainvoke({"symbol": "GOOG"})

    assert "Source: alphavantage [AV-EAR-GOOG-2026-06-30]" in out


# ---------------------------------------------------------------------------
# get_insider_activity (W3.5 will deepen this; W3.3 just stamps the source)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insider_av_path_emits_footnote_with_latest_tx_date() -> None:
    service = MagicMock()
    service.get_insider_transactions = AsyncMock(
        return_value={
            "data": [
                {"transaction_date": "2026-05-01", "shares": 1000},
                {"transaction_date": "2026-04-15", "shares": -500},
            ]
        }
    )
    formatter = MagicMock()
    formatter.format_insider_transactions = MagicMock(return_value="INSIDER BODY")

    tool = _make_tool(
        "get_insider_activity", service=service, formatter=formatter
    )
    out = await tool.ainvoke({"symbol": "AAPL", "limit": 50})

    assert "INSIDER BODY" in out
    assert "Source: alphavantage [AV-INS-AAPL-2026-05-01]" in out


@pytest.mark.asyncio
async def test_insider_yf_fallback_emits_yfinance_footnote() -> None:
    service = MagicMock()
    service.get_insider_transactions = AsyncMock(return_value={"data": []})
    formatter = MagicMock()

    tool = _make_tool(
        "get_insider_activity", service=service, formatter=formatter
    )
    with patch(
        "src.agent.tools.alpha_vantage.fundamentals.fetch_insider_yf",
        new=AsyncMock(return_value="YF INSIDER BODY"),
    ):
        out = await tool.ainvoke({"symbol": "NVDA", "limit": 50})

    assert "YF INSIDER BODY" in out
    assert "Source: yfinance [YF-INS-NVDA-" in out
