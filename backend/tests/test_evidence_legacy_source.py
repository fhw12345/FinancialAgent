"""Regression: service class name is not the provider which supplied a fact."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from src.agent.tools.alpha_vantage.fundamentals import create_fundamental_tools


@pytest.mark.asyncio
async def test_legacy_tool_must_not_relabel_yahoo_payload_as_alpha_vantage():
    service = MagicMock()
    service.get_company_overview = AsyncMock(
        return_value={"Symbol": "AAPL", "_source": "yfinance"}
    )
    formatter = MagicMock()
    formatter.format_company_overview.return_value = "Recorded overview"
    tool = next(
        t
        for t in create_fundamental_tools(service, formatter)
        if t.name == "get_company_overview"
    )
    assert "Source: yfinance" in await tool.ainvoke({"symbol": "AAPL"})
