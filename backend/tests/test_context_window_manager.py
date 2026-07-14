"""
Unit tests for ContextWindowManager.

Tests context window management including token estimation,
context structure extraction, and summarization.
"""

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from src.models.message import Message
from src.services.context_window_manager import ContextWindowManager

# ===== Fixtures =====


@pytest.fixture
def mock_settings():
    """Mock Settings"""
    settings = Mock()
    settings.llm_context_limit = 100000
    settings.compact_threshold_ratio = 0.5  # 50%
    settings.compact_target_ratio = 0.1  # 10%
    settings.tail_messages_keep = 3
    return settings


@pytest.fixture
def context_manager(mock_settings):
    """Create ContextWindowManager with mock settings"""
    return ContextWindowManager(mock_settings)


@pytest.fixture
def sample_messages():
    """Sample messages for tests"""
    return [
        Message(
            message_id="msg_1",
            chat_id="chat_123",
            role="system",
            content="You are a financial analyst.",
            source="user",
            timestamp=datetime.now(UTC).isoformat(),
        ),
        Message(
            message_id="msg_2",
            chat_id="chat_123",
            role="user",
            content="Analyze AAPL stock",
            source="user",
            timestamp=datetime.now(UTC).isoformat(),
        ),
        Message(
            message_id="msg_3",
            chat_id="chat_123",
            role="assistant",
            content="AAPL shows strong fundamentals with good earnings.",
            source="llm",
            timestamp=datetime.now(UTC).isoformat(),
        ),
        Message(
            message_id="msg_4",
            chat_id="chat_123",
            role="user",
            content="What about technical indicators?",
            source="user",
            timestamp=datetime.now(UTC).isoformat(),
        ),
        Message(
            message_id="msg_5",
            chat_id="chat_123",
            role="assistant",
            content="Technical analysis shows RSI at 65, MACD is bullish.",
            source="llm",
            timestamp=datetime.now(UTC).isoformat(),
        ),
    ]


# ===== estimate_tokens Tests =====


class TestEstimateTokens:
    """Test estimate_tokens method"""

    def test_estimate_tokens_with_tiktoken(self, context_manager):
        """Test token estimation with tiktoken"""
        text = "Hello world, this is a test."
        tokens = context_manager.estimate_tokens(text)
        # Should return a positive integer
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_estimate_tokens_empty_string(self, context_manager):
        """Test token estimation for empty string"""
        tokens = context_manager.estimate_tokens("")
        assert tokens == 0

    def test_estimate_tokens_long_text(self, context_manager):
        """Test token estimation for long text"""
        text = "word " * 1000  # ~5000 characters
        tokens = context_manager.estimate_tokens(text)
        # Should be roughly 1000 tokens (1 per word)
        assert tokens > 500
        assert tokens < 2000

    def test_estimate_tokens_fallback(self, mock_settings):
        """Test fallback token estimation without tiktoken"""
        manager = ContextWindowManager(mock_settings)
        # Force fallback by setting tokenizer to None
        manager.tokenizer = None

        text = "This is a test" * 100  # 1400 characters
        tokens = manager.estimate_tokens(text)

        # Fallback uses chars/4 approximation
        assert tokens == len(text) // 4


# ===== calculate_message_tokens Tests =====


class TestCalculateMessageTokens:
    """Test calculate_message_tokens method"""

    def test_calculate_message_tokens(self, context_manager, sample_messages):
        """Test calculating tokens for a message"""
        message = sample_messages[0]
        tokens = context_manager.calculate_message_tokens(message)
        assert tokens > 0

    def test_calculate_context_tokens(self, context_manager, sample_messages):
        """Test calculating total tokens for message list"""
        total = context_manager.calculate_context_tokens(sample_messages)
        assert total > 0
        # Should be sum of individual tokens
        individual_sum = sum(
            context_manager.calculate_message_tokens(msg) for msg in sample_messages
        )
        assert total == individual_sum


# ===== should_compact Tests =====


class TestShouldCompact:
    """Test should_compact method"""

    def test_should_compact_below_threshold(self, context_manager):
        """Test no compaction when below threshold"""
        assert context_manager.should_compact(25000) is False

    def test_should_compact_above_threshold(self, context_manager):
        """Test compaction when above threshold"""
        # Above 50% threshold
        assert context_manager.should_compact(60000) is True

    def test_should_compact_at_threshold(self, context_manager):
        """Test at exact threshold (should not compact)"""
        assert context_manager.should_compact(50000) is False


# ===== extract_context_structure Tests =====


class TestExtractContextStructure:
    """Test extract_context_structure method"""

    def test_extract_structure_normal(self, context_manager, sample_messages):
        """Test extracting HEAD, BODY, TAIL from messages"""
        head, body, tail = context_manager.extract_context_structure(sample_messages)

        # HEAD should contain system message
        assert len(head) == 1
        assert head[0].role == "system"

        # TAIL should contain last 3 messages (tail_keep=3)
        # Since we have 5 messages and 1 head, tail starts at max(1, 5-3)=2
        assert len(tail) == 3

        # BODY is between head and tail
        assert len(body) == 1

    def test_extract_structure_empty(self, context_manager):
        """Test extracting from empty messages"""
        head, body, tail = context_manager.extract_context_structure([])
        assert head == []
        assert body == []
        assert tail == []

    def test_extract_structure_only_system(self, context_manager):
        """Test with only system messages"""
        messages = [
            Message(
                message_id="msg_1",
                chat_id="chat_123",
                role="system",
                content="System prompt",
                source="user",
                timestamp=datetime.now(UTC).isoformat(),
            )
        ]
        head, body, tail = context_manager.extract_context_structure(messages)

        assert len(head) == 1
        assert len(body) == 0
        assert len(tail) == 0

    def test_extract_structure_no_system(self, context_manager):
        """Test with no system messages"""
        messages = [
            Message(
                message_id="msg_1",
                chat_id="chat_123",
                role="user",
                content="User message",
                source="user",
                timestamp=datetime.now(UTC).isoformat(),
            ),
            Message(
                message_id="msg_2",
                chat_id="chat_123",
                role="assistant",
                content="Assistant reply",
                source="llm",
                timestamp=datetime.now(UTC).isoformat(),
            ),
        ]
        head, body, tail = context_manager.extract_context_structure(messages)

        assert len(head) == 0
        # Both messages in tail (less than tail_keep=3)
        assert len(tail) == 2
        assert len(body) == 0


# ===== _fallback_summary Tests =====


class TestFallbackSummary:
    """Test _fallback_summary method"""

    def test_fallback_summary_basic(self, context_manager, sample_messages):
        """Test basic fallback summary"""
        summary = context_manager._fallback_summary(sample_messages)
        assert "Summary of 5 portfolio analyses" in summary
        assert "simplified summary" in summary

    def test_fallback_summary_with_symbol(self, context_manager, sample_messages):
        """Test fallback summary with symbol context"""
        summary = context_manager._fallback_summary(sample_messages, symbol="AAPL")
        assert "AAPL" in summary

    def test_fallback_summary_with_date_range(self, context_manager, sample_messages):
        """Test fallback summary with date range"""
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 1, 31, tzinfo=UTC)
        summary = context_manager._fallback_summary(
            sample_messages, date_range=(start, end)
        )
        assert "2025-01-01" in summary
        assert "2025-01-31" in summary

    def test_fallback_summary_empty_messages(self, context_manager):
        """Test fallback summary with empty messages"""
        summary = context_manager._fallback_summary([])
        assert "Summary of 0 portfolio analyses" in summary


# ===== reconstruct_context Tests =====


class TestReconstructContext:
    """Test reconstruct_context method"""

    def test_reconstruct_context(self, context_manager, sample_messages):
        """Test reconstructing context with summary"""
        head, body, tail = context_manager.extract_context_structure(sample_messages)
        summary_text = "This is a summary of previous analyses."

        reconstructed = context_manager.reconstruct_context(head, summary_text, tail)

        # Should have head + 1 summary + tail
        assert len(reconstructed) == len(head) + 1 + len(tail)

        # Check summary message
        summary_msg = reconstructed[len(head)]
        assert "summary of previous" in summary_msg.content.lower()
        assert summary_msg.role == "user"
        assert summary_msg.source == "llm"

    def test_reconstruct_context_empty_parts(self, context_manager):
        """Test reconstructing with empty head/tail"""
        reconstructed = context_manager.reconstruct_context([], "Summary text", [])

        # Should have just the summary message
        assert len(reconstructed) == 1
        assert "Summary text" in reconstructed[0].content
