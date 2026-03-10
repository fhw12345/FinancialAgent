"""Tests for debater sub-agent with independent tools."""

from unittest.mock import MagicMock, patch

from src.agent.subagents.debater import (
    TERMINATION_SIGNAL,
    create_debater_subagent,
)


class TestDebaterSubagent:
    """Test debater uses only independent tools."""

    @patch("src.agent.subagents.debater.create_deep_subagent")
    def test_debater_has_independent_tools_only(self, mock_create: MagicMock) -> None:
        """Debater must NOT use Alpha Vantage tools."""
        # Return a mock DeepSubAgent that exposes tool_names from the call
        mock_subagent = MagicMock()
        mock_create.return_value = mock_subagent

        mock_model = MagicMock()
        mock_context = MagicMock()
        mock_context.to_context_header.return_value = "test context"

        create_debater_subagent(
            model=mock_model,
            context=mock_context,
            exa_api_key="test-key",
        )

        # Verify tools passed to create_deep_subagent
        call_kwargs = mock_create.call_args
        tools = call_kwargs.kwargs.get("tools") or call_kwargs[1].get("tools")
        tool_names = [getattr(t, "name", str(t)) for t in tools]

        assert "fetch_yfinance_news" in tool_names
        assert "search_web_exa" in tool_names
        # Must NOT have Alpha Vantage tools
        assert "get_company_overview" not in tool_names
        assert "get_news_sentiment" not in tool_names
        assert "get_financial_statements" not in tool_names

    @patch("src.agent.subagents.debater.create_deep_subagent")
    def test_debater_without_exa_key(self, mock_create: MagicMock) -> None:
        """Debater works with only yfinance when no exa key provided."""
        mock_create.return_value = MagicMock()

        mock_model = MagicMock()
        mock_context = MagicMock()
        mock_context.to_context_header.return_value = "test context"

        create_debater_subagent(
            model=mock_model,
            context=mock_context,
            exa_api_key="",
        )

        call_kwargs = mock_create.call_args
        tools = call_kwargs.kwargs.get("tools") or call_kwargs[1].get("tools")
        tool_names = [getattr(t, "name", str(t)) for t in tools]

        assert "fetch_yfinance_news" in tool_names
        assert "search_web_exa" not in tool_names

    def test_termination_signal_unchanged(self) -> None:
        assert TERMINATION_SIGNAL == "NO FURTHER CONCERNS"
