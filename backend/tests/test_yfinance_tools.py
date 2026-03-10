"""Tests for yfinance news tool."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.agent.tools.yfinance_tools import create_yfinance_tools


class TestFetchYfinanceNews:
    """Test fetch_yfinance_news tool."""

    def test_create_yfinance_tools_returns_list(self) -> None:
        tools = create_yfinance_tools()
        assert isinstance(tools, list)
        assert len(tools) == 1
        assert tools[0].name == "fetch_yfinance_news"

    @pytest.mark.asyncio
    @patch("src.agent.tools.yfinance_tools.yf")
    async def test_fetch_returns_json_with_news_and_stats(
        self, mock_yf: MagicMock
    ) -> None:
        mock_ticker = MagicMock()
        mock_ticker.news = [
            {
                "title": "Apple Q1 Earnings Beat",
                "publisher": "Reuters",
                "link": "https://example.com/1",
            },
            {
                "title": "AAPL Hits New High",
                "publisher": "Bloomberg",
                "link": "https://example.com/2",
            },
        ]
        mock_ticker.info = {
            "trailingPE": 33.45,
            "forwardPE": 28.1,
            "marketCap": 3500000000000,
            "fiftyTwoWeekHigh": 288.35,
            "fiftyTwoWeekLow": 168.48,
            "currentPrice": 264.58,
            "trailingEps": 7.47,
            "forwardEps": 9.12,
            "revenueGrowth": 0.045,
            "earningsGrowth": 0.229,
        }
        mock_yf.Ticker.return_value = mock_ticker

        tools = create_yfinance_tools()
        result = await tools[0].ainvoke({"symbol": "AAPL"})
        data = json.loads(result)

        assert data["source"] == "yahoo_finance"
        assert len(data["news"]) == 2
        assert data["news"][0]["title"] == "Apple Q1 Earnings Beat"
        assert data["key_stats"]["pe_ratio"] == 33.45
        assert data["key_stats"]["52w_high"] == 288.35

    @pytest.mark.asyncio
    @patch("src.agent.tools.yfinance_tools.yf")
    async def test_fetch_handles_missing_stats_gracefully(
        self, mock_yf: MagicMock
    ) -> None:
        mock_ticker = MagicMock()
        mock_ticker.news = []
        mock_ticker.info = {}
        mock_yf.Ticker.return_value = mock_ticker

        tools = create_yfinance_tools()
        result = await tools[0].ainvoke({"symbol": "UNKNOWN"})
        data = json.loads(result)

        assert data["source"] == "yahoo_finance"
        assert data["news"] == []
        assert data["key_stats"]["pe_ratio"] is None

    @pytest.mark.asyncio
    @patch("src.agent.tools.yfinance_tools.yf")
    async def test_fetch_limits_news_to_10(self, mock_yf: MagicMock) -> None:
        mock_ticker = MagicMock()
        mock_ticker.news = [
            {
                "title": f"News {i}",
                "publisher": "Test",
                "link": f"https://example.com/{i}",
            }
            for i in range(20)
        ]
        mock_ticker.info = {}
        mock_yf.Ticker.return_value = mock_ticker

        tools = create_yfinance_tools()
        result = await tools[0].ainvoke({"symbol": "AAPL"})
        data = json.loads(result)

        assert len(data["news"]) == 10

    @pytest.mark.asyncio
    @patch("src.agent.tools.yfinance_tools.yf")
    async def test_fetch_handles_yfinance_error(self, mock_yf: MagicMock) -> None:
        mock_yf.Ticker.side_effect = Exception("Network error")

        tools = create_yfinance_tools()
        result = await tools[0].ainvoke({"symbol": "AAPL"})
        data = json.loads(result)

        assert data["source"] == "yahoo_finance"
        assert "Network error" in data["error"]
