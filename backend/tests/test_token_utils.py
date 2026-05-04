"""
Unit tests for token usage extraction utilities.

Tests token usage extraction from:
- LangChain messages (AIMessage, HumanMessage)
- Multiple metadata formats (usage_metadata, response_metadata)
- Agent invocation results
"""

from unittest.mock import Mock

from src.core.utils.token_utils import (
    extract_token_usage_from_agent_result,
    extract_token_usage_from_messages,
)

# ===== Extract Token Usage from Messages Tests =====


class TestExtractTokenUsageFromMessages:
    """Test extracting token usage from LangChain messages"""

    def test_extract_from_usage_metadata_format(self):
        """usage_metadata is a dict (TypedDict) in real LangChain — not an object."""
        # Arrange
        mock_ai_message = Mock()
        mock_ai_message.__class__.__name__ = "AIMessage"
        mock_ai_message.usage_metadata = {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }
        mock_ai_message.response_metadata = None

        messages = [mock_ai_message]

        # Act
        input_tokens, output_tokens, total_tokens = extract_token_usage_from_messages(
            messages
        )

        # Assert
        assert input_tokens == 100
        assert output_tokens == 50
        assert total_tokens == 150

    def test_extract_from_dashscope_format(self):
        """Test extraction from DashScope/Tongyi token_usage format"""
        # Arrange
        mock_ai_message = Mock()
        mock_ai_message.__class__.__name__ = "AIMessage"
        mock_ai_message.usage_metadata = None
        mock_ai_message.response_metadata = {
            "token_usage": {"input_tokens": 200, "output_tokens": 75}
        }

        messages = [mock_ai_message]

        # Act
        input_tokens, output_tokens, total_tokens = extract_token_usage_from_messages(
            messages
        )

        # Assert
        assert input_tokens == 200
        assert output_tokens == 75
        assert total_tokens == 275

    def test_extract_from_openai_format(self):
        """Test extraction from OpenAI usage format"""
        # Arrange
        mock_ai_message = Mock()
        mock_ai_message.__class__.__name__ = "AIMessage"
        mock_ai_message.usage_metadata = None
        mock_ai_message.response_metadata = {
            "usage": {"prompt_tokens": 150, "completion_tokens": 100}
        }

        messages = [mock_ai_message]

        # Act
        input_tokens, output_tokens, total_tokens = extract_token_usage_from_messages(
            messages
        )

        # Assert
        assert input_tokens == 150
        assert output_tokens == 100
        assert total_tokens == 250

    def test_extract_multiple_ai_messages(self):
        """Test summing token usage across multiple AIMessages"""
        # Arrange
        msg1 = Mock()
        msg1.__class__.__name__ = "AIMessage"
        msg1.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
        msg1.response_metadata = None

        msg2 = Mock()
        msg2.__class__.__name__ = "AIMessage"
        msg2.usage_metadata = {"input_tokens": 150, "output_tokens": 75}
        msg2.response_metadata = None

        messages = [msg1, msg2]

        # Act
        input_tokens, output_tokens, total_tokens = extract_token_usage_from_messages(
            messages
        )

        # Assert
        assert input_tokens == 250  # 100 + 150
        assert output_tokens == 125  # 50 + 75
        assert total_tokens == 375  # 250 + 125

    def test_ignore_human_messages(self):
        """Test that HumanMessage is ignored (only AIMessage counted)"""
        # Arrange
        human_msg = Mock()
        human_msg.__class__.__name__ = "HumanMessage"
        human_msg.usage_metadata = {"input_tokens": 100, "output_tokens": 50}

        ai_msg = Mock()
        ai_msg.__class__.__name__ = "AIMessage"
        ai_msg.usage_metadata = {"input_tokens": 200, "output_tokens": 75}
        ai_msg.response_metadata = None

        messages = [human_msg, ai_msg]

        # Act
        input_tokens, output_tokens, total_tokens = extract_token_usage_from_messages(
            messages
        )

        # Assert - should only count AIMessage
        assert input_tokens == 200
        assert output_tokens == 75
        assert total_tokens == 275

    def test_ignore_system_messages(self):
        """Test that SystemMessage is ignored"""
        # Arrange
        system_msg = Mock()
        system_msg.__class__.__name__ = "SystemMessage"
        system_msg.usage_metadata = {"input_tokens": 50, "output_tokens": 25}

        ai_msg = Mock()
        ai_msg.__class__.__name__ = "AIMessage"
        ai_msg.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
        ai_msg.response_metadata = None

        messages = [system_msg, ai_msg]

        # Act
        input_tokens, output_tokens, total_tokens = extract_token_usage_from_messages(
            messages
        )

        # Assert - should only count AIMessage
        assert input_tokens == 100
        assert output_tokens == 50
        assert total_tokens == 150

    def test_extract_empty_messages_list(self):
        """Test extraction from empty messages list"""
        # Arrange
        messages = []

        # Act
        input_tokens, output_tokens, total_tokens = extract_token_usage_from_messages(
            messages
        )

        # Assert
        assert input_tokens == 0
        assert output_tokens == 0
        assert total_tokens == 0

    def test_extract_no_ai_messages(self):
        """Test extraction when no AIMessages present"""
        # Arrange
        human_msg = Mock()
        human_msg.__class__.__name__ = "HumanMessage"

        system_msg = Mock()
        system_msg.__class__.__name__ = "SystemMessage"

        messages = [human_msg, system_msg]

        # Act
        input_tokens, output_tokens, total_tokens = extract_token_usage_from_messages(
            messages
        )

        # Assert
        assert input_tokens == 0
        assert output_tokens == 0
        assert total_tokens == 0

    def test_extract_ai_message_without_usage_metadata(self):
        """Test AIMessage with no usage metadata returns zeros"""
        # Arrange
        ai_msg = Mock()
        ai_msg.__class__.__name__ = "AIMessage"
        ai_msg.usage_metadata = None
        ai_msg.response_metadata = None

        messages = [ai_msg]

        # Act
        input_tokens, output_tokens, total_tokens = extract_token_usage_from_messages(
            messages
        )

        # Assert
        assert input_tokens == 0
        assert output_tokens == 0
        assert total_tokens == 0

    def test_extract_partial_usage_metadata(self):
        """Test AIMessage with partial usage metadata (missing fields)"""
        # Arrange
        ai_msg = Mock()
        ai_msg.__class__.__name__ = "AIMessage"
        ai_msg.usage_metadata = {"input_tokens": 100}  # output_tokens missing
        ai_msg.response_metadata = None

        messages = [ai_msg]

        # Act
        input_tokens, output_tokens, total_tokens = extract_token_usage_from_messages(
            messages
        )

        # Assert
        assert input_tokens == 100
        assert output_tokens == 0  # Missing field defaults to 0
        assert total_tokens == 100

    def test_extract_fallback_to_response_metadata_when_no_usage_metadata(self):
        """Test fallback from usage_metadata to response_metadata"""
        # Arrange
        ai_msg = Mock()
        ai_msg.__class__.__name__ = "AIMessage"
        ai_msg.usage_metadata = None  # Not available
        ai_msg.response_metadata = {
            "token_usage": {"input_tokens": 150, "output_tokens": 80}
        }

        messages = [ai_msg]

        # Act
        input_tokens, output_tokens, total_tokens = extract_token_usage_from_messages(
            messages
        )

        # Assert
        assert input_tokens == 150
        assert output_tokens == 80
        assert total_tokens == 230

    def test_extract_mixed_metadata_formats(self):
        """Test extraction from messages with mixed metadata formats"""
        # Arrange
        # Message 1: usage_metadata format
        msg1 = Mock()
        msg1.__class__.__name__ = "AIMessage"
        msg1.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
        msg1.response_metadata = None

        # Message 2: DashScope format
        msg2 = Mock()
        msg2.__class__.__name__ = "AIMessage"
        msg2.usage_metadata = None
        msg2.response_metadata = {
            "token_usage": {"input_tokens": 150, "output_tokens": 75}
        }

        # Message 3: OpenAI format
        msg3 = Mock()
        msg3.__class__.__name__ = "AIMessage"
        msg3.usage_metadata = None
        msg3.response_metadata = {
            "usage": {"prompt_tokens": 200, "completion_tokens": 100}
        }

        messages = [msg1, msg2, msg3]

        # Act
        input_tokens, output_tokens, total_tokens = extract_token_usage_from_messages(
            messages
        )

        # Assert
        assert input_tokens == 450  # 100 + 150 + 200
        assert output_tokens == 225  # 50 + 75 + 100
        assert total_tokens == 675


# ===== Extract Token Usage from Agent Result Tests =====


class TestExtractTokenUsageFromAgentResult:
    """Test extracting token usage from agent invocation results"""

    def test_extract_with_all_fields_present(self):
        """Test extraction when all token fields are present"""
        # Arrange
        agent_result = {
            "input_tokens": 200,
            "output_tokens": 100,
            "total_tokens": 300,
            "messages": [],
        }

        # Act
        result = extract_token_usage_from_agent_result(agent_result)

        # Assert
        assert result == {
            "input_tokens": 200,
            "output_tokens": 100,
            "total_tokens": 300,
        }

    def test_extract_with_missing_total_calculates_it(self):
        """Test that missing total_tokens is calculated from input + output"""
        # Arrange
        agent_result = {
            "input_tokens": 150,
            "output_tokens": 75,
            # total_tokens missing
        }

        # Act
        result = extract_token_usage_from_agent_result(agent_result)

        # Assert
        assert result == {
            "input_tokens": 150,
            "output_tokens": 75,
            "total_tokens": 225,  # Calculated: 150 + 75
        }

    def test_extract_with_all_fields_missing(self):
        """Test extraction when all token fields are missing"""
        # Arrange
        agent_result = {
            "messages": [],
            "other_data": "value",
        }

        # Act
        result = extract_token_usage_from_agent_result(agent_result)

        # Assert
        assert result == {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    def test_extract_with_zero_tokens(self):
        """Test extraction with explicit zero token counts"""
        # Arrange
        agent_result = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

        # Act
        result = extract_token_usage_from_agent_result(agent_result)

        # Assert
        assert result == {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    def test_extract_with_only_input_tokens(self):
        """Test extraction with only input_tokens present"""
        # Arrange
        agent_result = {
            "input_tokens": 100,
        }

        # Act
        result = extract_token_usage_from_agent_result(agent_result)

        # Assert
        assert result == {
            "input_tokens": 100,
            "output_tokens": 0,
            "total_tokens": 100,  # Calculated from input only
        }

    def test_extract_with_only_output_tokens(self):
        """Test extraction with only output_tokens present"""
        # Arrange
        agent_result = {
            "output_tokens": 50,
        }

        # Act
        result = extract_token_usage_from_agent_result(agent_result)

        # Assert
        assert result == {
            "input_tokens": 0,
            "output_tokens": 50,
            "total_tokens": 50,  # Calculated from output only
        }

    def test_extract_ignores_other_fields(self):
        """Test that extraction ignores non-token fields"""
        # Arrange
        agent_result = {
            "input_tokens": 100,
            "output_tokens": 50,
            "messages": ["message1", "message2"],
            "status": "success",
            "metadata": {"key": "value"},
        }

        # Act
        result = extract_token_usage_from_agent_result(agent_result)

        # Assert - should only extract token fields
        assert result == {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
        }

    def test_extract_with_provided_total_not_recalculated(self):
        """Test that provided total_tokens is not recalculated"""
        # Arrange - total_tokens doesn't match sum (edge case)
        agent_result = {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 200,  # Intentionally wrong for testing
        }

        # Act
        result = extract_token_usage_from_agent_result(agent_result)

        # Assert - should use provided total, not recalculate
        assert result == {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 200,  # Original value preserved
        }


# ===== Integration Tests =====


class TestTokenUtilsIntegration:
    """Test integration scenarios between functions"""

    def test_messages_and_agent_result_consistency(self):
        """Test that both extraction methods return consistent formats"""
        # Arrange
        mock_ai_message = Mock()
        mock_ai_message.__class__.__name__ = "AIMessage"
        mock_ai_message.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
        mock_ai_message.response_metadata = None

        messages = [mock_ai_message]
        agent_result = {"input_tokens": 100, "output_tokens": 50}

        # Act
        msg_input, msg_output, msg_total = extract_token_usage_from_messages(messages)
        agent_dict = extract_token_usage_from_agent_result(agent_result)

        # Assert - both should return consistent values
        assert msg_input == agent_dict["input_tokens"]
        assert msg_output == agent_dict["output_tokens"]
        assert msg_total == agent_dict["total_tokens"]

    def test_zero_token_messages_matches_empty_agent_result(self):
        """Test that empty messages and empty agent result both return zeros"""
        # Arrange
        messages = []
        agent_result = {}

        # Act
        msg_input, msg_output, msg_total = extract_token_usage_from_messages(messages)
        agent_dict = extract_token_usage_from_agent_result(agent_result)

        # Assert
        assert msg_input == agent_dict["input_tokens"] == 0
        assert msg_output == agent_dict["output_tokens"] == 0
        assert msg_total == agent_dict["total_tokens"] == 0
