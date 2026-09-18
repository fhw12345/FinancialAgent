"""Income adapter provenance/fallback, no inferred currency or raw upstream error disclosure."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
import pandas as pd
import pytest
from src.services.market_data import research_income


@pytest.mark.asyncio
async def test_yahoo_income_retains_fractional_values_and_financial_currency(
    monkeypatch,
):
    frame = pd.DataFrame(
        {
            pd.Timestamp("2025-12-31"): {
                "Diluted EPS": 5.25,
                "Diluted Average Shares": 10.5,
                "Interest Expense": 1.25,
            }
        }
    )
    monkeypatch.setattr(
        research_income.yf,
        "Ticker",
        lambda symbol: SimpleNamespace(
            income_stmt=frame, info={"financialCurrency": "USD"}
        ),
    )
    row = await research_income.fetch_income(SimpleNamespace(api_key=None), "AAPL")
    assert row["_source"] == "yfinance" and row["reportedCurrency"] == "USD"
    assert float(row["annualReports"][0]["dilutedEPS"]) == 5.25


@pytest.mark.asyncio
async def test_income_fallback_is_explicit_and_bad_receipts_fail(monkeypatch):
    monkeypatch.setattr(
        research_income.yf,
        "Ticker",
        lambda symbol: SimpleNamespace(income_stmt=pd.DataFrame()),
    )
    with pytest.raises(ValueError):
        await research_income.fetch_income(SimpleNamespace(api_key=None), "AAPL")
    response = SimpleNamespace(status_code=200, json=lambda: {"annualReports": []})
    client = SimpleNamespace(get=AsyncMock(return_value=response))
    service = SimpleNamespace(
        api_key="synthetic", base_url="https://example.invalid", client=client
    )
    assert (await research_income.fetch_income(service, "AAPL"))[
        "_source"
    ] == "alphavantage"
    response.status_code = 500
    with pytest.raises(ValueError, match="unavailable"):
        await research_income.fetch_income(service, "AAPL")
    response.status_code = 200
    response.json = lambda: {"error": "private upstream body"}
    with pytest.raises(ValueError, match="unavailable"):
        await research_income.fetch_income(service, "AAPL")
