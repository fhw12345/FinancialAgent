"""
Unit tests for ChatService.

Tests chat and message management with mocked repositories:
- Chat creation and retrieval
- Message management
- UI state updates
- Title generation
- Symbol-based chat lookup
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.core.exceptions import NotFoundError, ValidationError
from src.models.chat import Chat, UIState
from src.models.message import Message, MessageMetadata
from src.services.chat_service import ChatService


# ===== Fixtures =====


@pytest.fixture
def mock_chat_repo():
    """Mock ChatRepository"""
    repo = Mock()
    repo.create = AsyncMock()
    repo.get = AsyncMock()
    repo.list_by_user = AsyncMock()
    repo.update = AsyncMock()
    repo.update_ui_state = AsyncMock()
    repo.update_last_message_at = AsyncMock()
    repo.find_by_symbol = AsyncMock()
    repo.delete = AsyncMock()
    return repo


@pytest.fixture
def mock_message_repo():
    """Mock MessageRepository"""
    repo = Mock()
    repo.create = AsyncMock()
    repo.get_by_chat = AsyncMock()
    repo.delete_by_chat = AsyncMock()
    return repo


@pytest.fixture
def mock_settings():
    """Mock Settings"""
    settings = Mock()
    return settings


@pytest.fixture
def chat_service(mock_chat_repo, mock_message_repo, mock_settings):
    """ChatService instance with mocked dependencies"""
    return ChatService(mock_chat_repo, mock_message_repo, mock_settings)


@pytest.fixture
def sample_chat():
    """Sample Chat for tests"""
    return Chat(
        chat_id="chat_123",
        user_id="user_456",
        title="Test Chat",
        ui_state=UIState(current_symbol="AAPL"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_message():
    """Sample Message for tests"""
    return Message(
        message_id="msg_789",
        chat_id="chat_123",
        role="user",
        content="Test message content",
        source="user",
        metadata=MessageMetadata(),
        created_at=datetime.now(timezone.utc),
    )


# ===== create_chat Tests =====


class TestCreateChat:
    """Test chat creation"""

    @pytest.mark.asyncio
    async def test_create_chat_success(
        self, chat_service, mock_chat_repo, sample_chat
    ):
        """Test successful chat creation"""
        mock_chat_repo.create.return_value = sample_chat

        result = await chat_service.create_chat("user_456", "My Chat")

        assert result == sample_chat
        mock_chat_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_chat_default_title(
        self, chat_service, mock_chat_repo, sample_chat
    ):
        """Test chat creation with default title"""
        mock_chat_repo.create.return_value = sample_chat

        await chat_service.create_chat("user_456")

        call_args = mock_chat_repo.create.call_args[0][0]
        assert call_args.title == "New Chat"


# ===== get_chat Tests =====


class TestGetChat:
    """Test chat retrieval with ownership verification"""

    @pytest.mark.asyncio
    async def test_get_chat_success(self, chat_service, mock_chat_repo, sample_chat):
        """Test successful chat retrieval"""
        mock_chat_repo.get.return_value = sample_chat

        result = await chat_service.get_chat("chat_123", "user_456")

        assert result == sample_chat
        mock_chat_repo.get.assert_called_once_with("chat_123")

    @pytest.mark.asyncio
    async def test_get_chat_not_found(self, chat_service, mock_chat_repo):
        """Test chat not found raises NotFoundError"""
        mock_chat_repo.get.return_value = None

        with pytest.raises(NotFoundError):
            await chat_service.get_chat("nonexistent", "user_456")

# ===== list_user_chats Tests =====


class TestListUserChats:
    """Test listing user chats with pagination"""

    @pytest.mark.asyncio
    async def test_list_user_chats_success(
        self, chat_service, mock_chat_repo, sample_chat
    ):
        """Test successful chat listing"""
        mock_chat_repo.list_by_user.return_value = [sample_chat]

        chats, total = await chat_service.list_user_chats("user_456")

        assert len(chats) == 1
        assert chats[0] == sample_chat
        mock_chat_repo.list_by_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_user_chats_invalid_page(self, chat_service):
        """Test invalid page number raises ValidationError"""
        with pytest.raises(ValidationError):
            await chat_service.list_user_chats("user_456", page=0)

    @pytest.mark.asyncio
    async def test_list_user_chats_invalid_page_size(self, chat_service):
        """Test invalid page size raises ValidationError"""
        with pytest.raises(ValidationError):
            await chat_service.list_user_chats("user_456", page_size=101)


# ===== add_message Tests =====


class TestAddMessage:
    """Test adding messages to chat"""

    @pytest.mark.asyncio
    async def test_add_message_success(
        self, chat_service, mock_chat_repo, mock_message_repo, sample_chat, sample_message
    ):
        """Test successful message addition"""
        mock_chat_repo.get.return_value = sample_chat
        mock_message_repo.create.return_value = sample_message

        result = await chat_service.add_message(
            chat_id="chat_123",
            user_id="user_456",
            role="user",
            content="Hello world",
            source="user",
        )

        assert result == sample_message
        mock_message_repo.create.assert_called_once()
        mock_chat_repo.update.assert_called_once()
        mock_chat_repo.update_last_message_at.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_message_with_dict_metadata(
        self, chat_service, mock_chat_repo, mock_message_repo, sample_chat, sample_message
    ):
        """Test adding message with dict metadata containing analysis data"""
        mock_chat_repo.get.return_value = sample_chat
        mock_message_repo.create.return_value = sample_message

        metadata = {"symbol": "AAPL", "timeframe": "1D"}

        await chat_service.add_message(
            chat_id="chat_123",
            user_id="user_456",
            role="assistant",
            content="Analysis",
            source="llm",
            metadata=metadata,
        )

        # Should have been called with MessageMetadata wrapper
        call_args = mock_message_repo.create.call_args[0][0]
        assert call_args.metadata is not None


# ===== get_chat_messages Tests =====


class TestGetChatMessages:
    """Test getting messages from chat"""

    @pytest.mark.asyncio
    async def test_get_chat_messages_success(
        self, chat_service, mock_chat_repo, mock_message_repo, sample_chat, sample_message
    ):
        """Test successful message retrieval"""
        mock_chat_repo.get.return_value = sample_chat
        mock_message_repo.get_by_chat.return_value = [sample_message]

        result = await chat_service.get_chat_messages("chat_123", "user_456")

        assert len(result) == 1
        assert result[0] == sample_message

    @pytest.mark.asyncio
    async def test_get_chat_messages_with_pagination(
        self, chat_service, mock_chat_repo, mock_message_repo, sample_chat
    ):
        """Test message retrieval with pagination"""
        mock_chat_repo.get.return_value = sample_chat
        mock_message_repo.get_by_chat.return_value = []

        await chat_service.get_chat_messages(
            "chat_123", "user_456", limit=50, offset=10
        )

        mock_message_repo.get_by_chat.assert_called_once_with(
            "chat_123", limit=50, offset=10
        )


# ===== update_ui_state Tests =====


class TestUpdateUIState:
    """Test UI state updates"""

    @pytest.mark.asyncio
    async def test_update_ui_state_success(
        self, chat_service, mock_chat_repo, sample_chat
    ):
        """Test successful UI state update"""
        mock_chat_repo.get.return_value = sample_chat
        updated_chat = Chat(**sample_chat.model_dump())
        updated_chat.ui_state = UIState(current_symbol="NVDA", current_interval="1D")
        mock_chat_repo.update_ui_state.return_value = updated_chat

        new_state = UIState(current_symbol="NVDA", current_interval="1D")
        result = await chat_service.update_ui_state("chat_123", "user_456", new_state)

        assert result.ui_state.current_symbol == "NVDA"

    @pytest.mark.asyncio
    async def test_update_ui_state_chat_not_found(
        self, chat_service, mock_chat_repo, sample_chat
    ):
        """Test UI state update when chat is not found during update"""
        mock_chat_repo.get.return_value = sample_chat
        mock_chat_repo.update_ui_state.return_value = None

        with pytest.raises(NotFoundError):
            await chat_service.update_ui_state(
                "chat_123", "user_456", UIState(current_symbol="NVDA")
            )


# ===== update_chat_title Tests =====


class TestUpdateChatTitle:
    """Test chat title updates"""

    @pytest.mark.asyncio
    async def test_update_chat_title_success(
        self, chat_service, mock_chat_repo, sample_chat
    ):
        """Test successful title update"""
        updated_chat = Chat(**sample_chat.model_dump())
        updated_chat.title = "New Title"
        mock_chat_repo.update.return_value = updated_chat

        result = await chat_service.update_chat_title("chat_123", "New Title")

        assert result.title == "New Title"

    @pytest.mark.asyncio
    async def test_update_chat_title_not_found(self, chat_service, mock_chat_repo):
        """Test title update when chat not found"""
        mock_chat_repo.update.return_value = None

        result = await chat_service.update_chat_title("nonexistent", "Title")

        assert result is None


# ===== update_title_if_new Tests =====


class TestUpdateTitleIfNew:
    """Test conditional title update"""

    @pytest.mark.asyncio
    async def test_update_title_with_llm_title(
        self, chat_service, mock_chat_repo, sample_chat
    ):
        """Test title update using LLM-generated title"""
        sample_chat.title = "New Chat"  # Initial title
        mock_chat_repo.get.return_value = sample_chat
        mock_chat_repo.update.return_value = sample_chat

        result = await chat_service.update_title_if_new(
            "chat_123", "AAPL Analysis", "Analyze AAPL"
        )

        assert result == "AAPL Analysis"

    @pytest.mark.asyncio
    async def test_update_title_skipped_when_not_new(
        self, chat_service, mock_chat_repo, sample_chat
    ):
        """Test that title update is skipped when chat already has title"""
        sample_chat.title = "Existing Title"  # Already has a title
        mock_chat_repo.get.return_value = sample_chat

        result = await chat_service.update_title_if_new(
            "chat_123", "New Title", "Some message"
        )

        assert result is None
        mock_chat_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_title_heuristic_fallback(
        self, chat_service, mock_chat_repo, sample_chat
    ):
        """Test title generation fallback to heuristic when LLM title is None"""
        sample_chat.title = "New Chat"
        mock_chat_repo.get.return_value = sample_chat
        mock_chat_repo.update.return_value = sample_chat

        with patch.object(
            chat_service, "_generate_title_heuristic", return_value="Generated Title"
        ):
            result = await chat_service.update_title_if_new(
                "chat_123", None, "Some user message"
            )

            assert result == "Generated Title"


# ===== find_chat_by_symbol Tests =====


class TestFindChatBySymbol:
    """Test symbol-based chat lookup"""

    @pytest.mark.asyncio
    async def test_find_chat_by_symbol_not_found(self, chat_service, mock_chat_repo):
        """Test no chat found for symbol"""
        mock_chat_repo.find_by_symbol.return_value = None

        result = await chat_service.find_chat_by_symbol("user_456", "NVDA")

        assert result is None


# ===== get_or_create_symbol_chat Tests =====


class TestGetOrCreateSymbolChat:
    """Test get or create chat for symbol"""

    @pytest.mark.asyncio
    async def test_get_existing_symbol_chat(
        self, chat_service, mock_chat_repo, sample_chat
    ):
        """Test returning existing chat for symbol"""
        mock_chat_repo.find_by_symbol.return_value = sample_chat

        result = await chat_service.get_or_create_symbol_chat("user_456", "AAPL")

        assert result == sample_chat
        mock_chat_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_new_symbol_chat(
        self, chat_service, mock_chat_repo, sample_chat
    ):
        """Test creating new chat when none exists for symbol"""
        mock_chat_repo.find_by_symbol.return_value = None
        mock_chat_repo.create.return_value = sample_chat
        mock_chat_repo.get.return_value = sample_chat
        mock_chat_repo.update_ui_state.return_value = sample_chat

        result = await chat_service.get_or_create_symbol_chat("user_456", "NVDA")

        assert result is not None
        mock_chat_repo.create.assert_called_once()


# ===== delete_chat Tests =====


class TestDeleteChat:
    """Test chat deletion"""

    @pytest.mark.asyncio
    async def test_delete_chat_success(
        self, chat_service, mock_chat_repo, mock_message_repo, sample_chat
    ):
        """Test successful chat deletion"""
        mock_chat_repo.get.return_value = sample_chat
        mock_message_repo.delete_by_chat.return_value = 5
        mock_chat_repo.delete.return_value = True

        result = await chat_service.delete_chat("chat_123", "user_456")

        assert result is True
        mock_message_repo.delete_by_chat.assert_called_once_with("chat_123")
        mock_chat_repo.delete.assert_called_once_with("chat_123")

    @pytest.mark.asyncio
    async def test_delete_chat_not_found(self, chat_service, mock_chat_repo):
        """Test deleting nonexistent chat raises NotFoundError"""
        mock_chat_repo.get.return_value = None

        with pytest.raises(NotFoundError):
            await chat_service.delete_chat("nonexistent", "user_456")
