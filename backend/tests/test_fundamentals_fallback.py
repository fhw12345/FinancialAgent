"""W1.5-W1.8 unit tests — fundamentals tools fallback paths.

Three paths per tool:
  1. AV returns valid data       -> formatter output (+ W3.3 source footnote)
  2. AV empty / raises -> yf ok  -> markdown w/ banner (+ W3.3 yfinance footnote)
  3. Both empty                  -> unavailable_message string (no footnote;
                                    Wave-1's consistency_gate pattern-matches
                                    that text exactly)

Mock-based: patches the AV service + the _yf_fallback helpers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.tools.alpha_vantage.fundamentals import create_fundamental_tools


def _make_tools(
    av_overview=None,
    av_overview_error=None,
    av_cashflow=None,
    av_cashflow_error=None,
    av_balance=None,
    av_balance_error=None,
    av_insider=None,
    av_insider_error=None,
    av_earnings=None,
    av_earnings_error=None,
):
    service = MagicMock()
    formatter = MagicMock()
    formatter.format_company_overview.return_value = "AV-OK overview"
    formatter.format_cash_flow.return_value = "AV-OK cash_flow"
    formatter.format_balance_sheet.return_value = "AV-OK balance_sheet"
    formatter.format_insider_transactions.return_value = "AV-OK insider"
    formatter.format_earnings.return_value = "AV-OK earnings"

    service.get_company_overview = AsyncMock(
        return_value=av_overview, side_effect=av_overview_error
    )
    service.get_cash_flow = AsyncMock(
        return_value=av_cashflow, side_effect=av_cashflow_error
    )
    service.get_balance_sheet = AsyncMock(
        return_value=av_balance, side_effect=av_balance_error
    )
    service.get_insider_transactions = AsyncMock(
        return_value=av_insider, side_effect=av_insider_error
    )
    service.get_earnings = AsyncMock(
        return_value=av_earnings, side_effect=av_earnings_error
    )
    tools = create_fundamental_tools(service, formatter)
    return {t.name: t for t in tools}


# ---------------------------------------------------------------------------
# get_company_overview
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_av_ok_no_fallback() -> None:
    tools = _make_tools(av_overview={"Symbol": "AAPL", "Name": "Apple"})
    with patch(
        "src.agent.tools.alpha_vantage.fundamentals.fetch_overview_yf"
    ) as yf_mock:
        result = await tools["get_company_overview"].ainvoke({"symbol": "AAPL"})
    assert result.startswith("AV-OK overview")
    assert "Source: alphavantage [AV-OV-AAPL-" in result
    yf_mock.assert_not_called()


@pytest.mark.asyncio
async def test_overview_av_empty_uses_yf() -> None:
    tools = _make_tools(av_overview={})
    with patch(
        "src.agent.tools.alpha_vantage.fundamentals.fetch_overview_yf",
        new=AsyncMock(return_value="YF banner overview"),
    ):
        result = await tools["get_company_overview"].ainvoke({"symbol": "AAPL"})
    assert result.startswith("YF banner overview")
    assert "Source: yfinance [YF-OV-AAPL-" in result


@pytest.mark.asyncio
async def test_overview_av_raises_uses_yf() -> None:
    tools = _make_tools(av_overview_error=RuntimeError("AV rate limited"))
    with patch(
        "src.agent.tools.alpha_vantage.fundamentals.fetch_overview_yf",
        new=AsyncMock(return_value="YF banner overview"),
    ):
        result = await tools["get_company_overview"].ainvoke({"symbol": "AAPL"})
    assert result.startswith("YF banner overview")
    assert "Source: yfinance [YF-OV-AAPL-" in result


@pytest.mark.asyncio
async def test_overview_both_fail_returns_unavailable_message() -> None:
    tools = _make_tools(av_overview={})
    with patch(
        "src.agent.tools.alpha_vantage.fundamentals.fetch_overview_yf",
        new=AsyncMock(return_value=None),
    ):
        result = await tools["get_company_overview"].ainvoke({"symbol": "XYZ"})
    assert "XYZ" in result
    assert "Company overview" in result
    assert "unsubstantiated" in result


# ---------------------------------------------------------------------------
# get_financial_statements (cash_flow + balance_sheet)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cash_flow_av_empty_uses_yf() -> None:
    tools = _make_tools(av_cashflow=None)
    with patch(
        "src.agent.tools.alpha_vantage.fundamentals.fetch_cash_flow_yf",
        new=AsyncMock(return_value="YF cashflow"),
    ):
        result = await tools["get_financial_statements"].ainvoke(
            {"symbol": "AAPL", "statement_type": "cash_flow"}
        )
    assert result.startswith("YF cashflow")
    assert "Source: yfinance [YF-CF-AAPL-" in result


@pytest.mark.asyncio
async def test_cash_flow_both_fail_returns_unavailable() -> None:
    tools = _make_tools(av_cashflow=None)
    with patch(
        "src.agent.tools.alpha_vantage.fundamentals.fetch_cash_flow_yf",
        new=AsyncMock(return_value=None),
    ):
        result = await tools["get_financial_statements"].ainvoke(
            {"symbol": "XYZ", "statement_type": "cash_flow"}
        )
    assert "XYZ" in result
    assert "Cash flow" in result
    assert "unsubstantiated" in result


@pytest.mark.asyncio
async def test_balance_sheet_av_empty_uses_yf() -> None:
    tools = _make_tools(av_balance=None)
    with patch(
        "src.agent.tools.alpha_vantage.fundamentals.fetch_balance_sheet_yf",
        new=AsyncMock(return_value="YF balance"),
    ):
        result = await tools["get_financial_statements"].ainvoke(
            {"symbol": "AAPL", "statement_type": "balance_sheet"}
        )
    assert result.startswith("YF balance")
    assert "Source: yfinance [YF-BS-AAPL-" in result


# ---------------------------------------------------------------------------
# get_insider_activity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insider_av_empty_uses_yf() -> None:
    tools = _make_tools(av_insider={})
    with patch(
        "src.agent.tools.alpha_vantage.fundamentals.fetch_insider_yf",
        new=AsyncMock(return_value="YF insider"),
    ):
        result = await tools["get_insider_activity"].ainvoke({"symbol": "AAPL"})
    assert result.startswith("YF insider")
    assert "Source: yfinance [YF-INS-AAPL-" in result


@pytest.mark.asyncio
async def test_insider_both_fail_returns_unavailable() -> None:
    tools = _make_tools(av_insider={})
    with patch(
        "src.agent.tools.alpha_vantage.fundamentals.fetch_insider_yf",
        new=AsyncMock(return_value=None),
    ):
        result = await tools["get_insider_activity"].ainvoke({"symbol": "XYZ"})
    assert "XYZ" in result
    assert "Insider activity" in result
    assert "unsubstantiated" in result


# ---------------------------------------------------------------------------
# get_company_earnings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_earnings_av_empty_uses_yf() -> None:
    tools = _make_tools(av_earnings=None)
    with patch(
        "src.agent.tools.alpha_vantage.fundamentals.fetch_earnings_yf",
        new=AsyncMock(return_value="YF earnings"),
    ):
        result = await tools["get_company_earnings"].ainvoke({"symbol": "AAPL"})
    assert result.startswith("YF earnings")
    assert "Source: yfinance [YF-EAR-AAPL-" in result


@pytest.mark.asyncio
async def test_earnings_both_fail_returns_unavailable() -> None:
    tools = _make_tools(av_earnings=None)
    with patch(
        "src.agent.tools.alpha_vantage.fundamentals.fetch_earnings_yf",
        new=AsyncMock(return_value=None),
    ):
        result = await tools["get_company_earnings"].ainvoke({"symbol": "XYZ"})
    assert "XYZ" in result
    assert "Earnings" in result
    assert "unsubstantiated" in result
