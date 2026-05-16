"""Tests for Exa web search tool.

Tests cover:
- create_exa_tools returns correct tool list
"""

from src.agent.tools.exa_tools import create_exa_tools


class TestSearchWebExa:
    """Test search_web_exa tool."""

    def test_create_exa_tools_returns_list(self) -> None:
        tools = create_exa_tools(api_key="test-key")
        assert isinstance(tools, list)
        assert len(tools) == 1
        assert tools[0].name == "search_web_exa"
