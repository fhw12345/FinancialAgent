"""Tests for Exa web search tool.

Tests cover:
- create_exa_tools returns correct tool list
- Structured JSON results from search
- Error handling
- Result count limiting
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.agent.tools.exa_tools import create_exa_tools


class TestSearchWebExa:
    """Test search_web_exa tool."""

    def test_create_exa_tools_returns_list(self) -> None:
        tools = create_exa_tools(api_key="test-key")
        assert isinstance(tools, list)
        assert len(tools) == 1
        assert tools[0].name == "search_web_exa"

    @pytest.mark.asyncio
    @patch("src.agent.tools.exa_tools.Exa")
    async def test_search_returns_structured_results(
        self, mock_exa_class: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.results = [
            MagicMock(
                title="Apple CSAM Lawsuit",
                url="https://example.com/1",
                text="West Virginia AG files...",
            ),
            MagicMock(
                title="AAPL Analysis",
                url="https://example.com/2",
                text="Stock outlook...",
            ),
        ]
        mock_client.search_and_contents.return_value = mock_result
        mock_exa_class.return_value = mock_client

        tools = create_exa_tools(api_key="test-key")
        result = await tools[0].ainvoke({"query": "Apple CSAM lawsuit"})
        data = json.loads(result)

        assert data["source"] == "exa_web_search"
        assert len(data["results"]) == 2
        assert data["results"][0]["title"] == "Apple CSAM Lawsuit"

    @pytest.mark.asyncio
    @patch("src.agent.tools.exa_tools.Exa")
    async def test_search_handles_error(self, mock_exa_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client.search_and_contents.side_effect = Exception("API error")
        mock_exa_class.return_value = mock_client

        tools = create_exa_tools(api_key="test-key")
        result = await tools[0].ainvoke({"query": "test query"})
        data = json.loads(result)

        assert data["source"] == "exa_web_search"
        assert "API error" in data["error"]

    @pytest.mark.asyncio
    @patch("src.agent.tools.exa_tools.Exa")
    async def test_search_limits_results(self, mock_exa_class: MagicMock) -> None:
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.results = [
            MagicMock(
                title=f"Result {i}",
                url=f"https://ex.com/{i}",
                text=f"Content {i}",
            )
            for i in range(10)
        ]
        mock_client.search_and_contents.return_value = mock_result
        mock_exa_class.return_value = mock_client

        tools = create_exa_tools(api_key="test-key")
        result = await tools[0].ainvoke({"query": "test"})
        data = json.loads(result)

        assert len(data["results"]) <= 5
