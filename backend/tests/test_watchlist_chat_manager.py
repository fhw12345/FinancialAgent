"""
Unit tests for ChatManager in watchlist service.

Tests symbol-specific chat creation and retrieval.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from src.services.watchlist.chat_manager import ChatManager


# ===== Fixtures =====


@pytest.fixture
def mock_chat_repo():
    """Create mock chat repository."""
    repo = AsyncMock()
    repo.list_by_user = AsyncMock(return_value=[])
    repo.create = AsyncMock()
    return repo


@pytest.fixture
def chat_manager(mock_chat_repo):
    """Create ChatManager with mocked repository."""
    return ChatManager(chat_repo=mock_chat_repo)


# ===== __init__ Tests =====


class TestChatManagerInit:
    """Test ChatManager initialization."""

    def test_init_sets_repo(self, mock_chat_repo):
        """Test initialization sets chat repository."""
        manager = ChatManager(chat_repo=mock_chat_repo)
        assert manager.chat_repo == mock_chat_repo


# ===== get_symbol_chat_id Tests =====


class TestGetSymbolChatId:
    """Test get_symbol_chat_id method."""

    @pytest.mark.asyncio
    async def test_finds_existing_chat(self, chat_manager, mock_chat_repo):
        """Test finding existing chat for symbol."""
        existing_chat = Mock()
        existing_chat.chat_id = "chat_existing_123"
        existing_chat.title = "AAPL Analysis"

        mock_chat_repo.list_by_user.return_value = [existing_chat]

        result = await chat_manager.get_symbol_chat_id("AAPL")

        assert result == "chat_existing_123"
        mock_chat_repo.list_by_user.assert_called_once_with("portfolio_agent")
        mock_chat_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_new_chat_when_no_matching_title(
        self, chat_manager, mock_chat_repo
    ):
        """Test creates new chat when existing chats don't match symbol."""
        other_chat = Mock()
        other_chat.chat_id = "chat_other_789"
        other_chat.title = "MSFT Analysis"

        mock_chat_repo.list_by_user.return_value = [other_chat]

        new_chat = Mock()
        new_chat.chat_id = "chat_new_abc"
        mock_chat_repo.create.return_value = new_chat

        result = await chat_manager.get_symbol_chat_id("GOOGL")

        assert result == "chat_new_abc"
        mock_chat_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_chat_with_none_title(self, chat_manager, mock_chat_repo):
        """Test handles chat with None title gracefully."""
        chat_no_title = Mock()
        chat_no_title.chat_id = "chat_no_title"
        chat_no_title.title = None

        mock_chat_repo.list_by_user.return_value = [chat_no_title]

        new_chat = Mock()
        new_chat.chat_id = "chat_new_xyz"
        mock_chat_repo.create.return_value = new_chat

        result = await chat_manager.get_symbol_chat_id("NVDA")

        assert result == "chat_new_xyz"
        mock_chat_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_finds_chat_among_multiple(self, chat_manager, mock_chat_repo):
        """Test finding correct chat among multiple chats."""
        chat1 = Mock()
        chat1.chat_id = "chat_1"
        chat1.title = "AAPL Analysis"

        chat2 = Mock()
        chat2.chat_id = "chat_2"
        chat2.title = "MSFT Analysis"

        chat3 = Mock()
        chat3.chat_id = "chat_3"
        chat3.title = "GOOGL Analysis"

        mock_chat_repo.list_by_user.return_value = [chat1, chat2, chat3]

        result = await chat_manager.get_symbol_chat_id("MSFT")

        assert result == "chat_2"
        mock_chat_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_symbol_prefix_match(self, chat_manager, mock_chat_repo):
        """Test chat title matches symbol prefix."""
        # "AAPL " should match "AAPL Analysis"
        chat = Mock()
        chat.chat_id = "chat_aapl"
        chat.title = "AAPL Weekly Report"  # Different suffix still matches

        mock_chat_repo.list_by_user.return_value = [chat]

        result = await chat_manager.get_symbol_chat_id("AAPL")

        assert result == "chat_aapl"
