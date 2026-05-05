"""
Unit tests for ChatRepository.

Tests chat data access operations including:
- Chat creation with UI state
- Retrieving chats by ID
- Listing user chats with pagination and filtering
- Updating chat metadata (title, archived status, UI state)
- Symbol-per-chat pattern (finding chat by symbol)
- Timestamp tracking (last_message_at, updated_at)
- Chat deletion
- Index creation for optimal performance
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.database.repositories.chat_repository import ChatRepository
from src.models.chat import Chat, ChatCreate, ChatUpdate, UIState

# ===== Fixtures =====


@pytest.fixture
def mock_collection():
    """Mock MongoDB collection"""
    collection = Mock()
    collection.create_index = AsyncMock()
    collection.insert_one = AsyncMock()
    collection.find_one = AsyncMock()
    collection.find = Mock()
    collection.find_one_and_update = AsyncMock()
    collection.update_one = AsyncMock()
    collection.delete_one = AsyncMock()
    return collection


class _FakeRedis:
    """Minimal RedisCache stand-in for unit tests; translator is patched anyway."""

    async def get(self, k):  # noqa: ARG002
        return None

    async def set(self, k, v, ttl_seconds=None):  # noqa: ARG002
        return None


@pytest.fixture
def fake_redis():
    return _FakeRedis()


@pytest.fixture
def repository(mock_collection, fake_redis):
    """Create ChatRepository instance"""
    return ChatRepository(mock_collection, fake_redis)


@pytest.fixture
def chat_repository(mock_collection, fake_redis):
    """Alias used by write-time translation tests."""
    return ChatRepository(mock_collection, fake_redis)


@pytest.fixture
def sample_chat():
    """Sample chat object"""
    return Chat(
        chat_id="chat_abc123",
        user_id="user_xyz789",
        title="AAPL Analysis",
        is_archived=False,
        ui_state=UIState(
            current_symbol="AAPL",
            current_interval="1d",
            current_date_range={"start": None, "end": None},
            active_overlays={"fibonacci": {"enabled": True}},
        ),
        last_message_preview="Based on the Fibonacci levels, AAPL shows...",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        last_message_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_chat_create():
    """Sample chat creation data"""
    return ChatCreate(title="New Technical Analysis", user_id="user_123")


# ===== Index Tests =====


class TestEnsureIndexes:
    """Test index creation"""

    @pytest.mark.asyncio
    async def test_ensure_indexes_creates_all_indexes(
        self, repository, mock_collection
    ):
        """Test that all required indexes are created"""
        # Act
        await repository.ensure_indexes()

        # Assert
        assert mock_collection.create_index.call_count == 2

        # Check specific indexes were created
        calls = mock_collection.create_index.call_args_list
        index_names = [call.kwargs.get("name") for call in calls]

        assert "idx_user_chats" in index_names
        assert "idx_symbol_lookup" in index_names


# ===== Create Tests =====


class TestCreate:
    """Test chat creation"""

    @pytest.mark.asyncio
    async def test_create_chat_success(
        self, repository, mock_collection, sample_chat_create
    ):
        """Test successful chat creation"""
        # Arrange
        mock_collection.insert_one.return_value = Mock(inserted_id="mongo_id")

        # Act
        result = await repository.create(sample_chat_create)

        # Assert
        assert result.title == "New Technical Analysis"
        assert result.user_id == "user_123"
        assert result.chat_id.startswith("chat_")
        assert result.is_archived is False
        assert isinstance(result.ui_state, UIState)
        assert result.last_message_preview is None
        mock_collection.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_chat_generates_valid_chat_id(
        self, repository, mock_collection, sample_chat_create
    ):
        """Test that generated chat_id follows correct format"""
        # Arrange
        mock_collection.insert_one.return_value = Mock(inserted_id="mongo_id")

        # Act
        result = await repository.create(sample_chat_create)

        # Assert
        assert result.chat_id.startswith("chat_")
        assert len(result.chat_id) == 17  # "chat_" + 12 hex chars

    @pytest.mark.asyncio
    async def test_create_chat_with_default_title(self, repository, mock_collection):
        """Test creating chat with default title"""
        # Arrange
        chat_create = ChatCreate(user_id="user_123")  # No title
        mock_collection.insert_one.return_value = Mock(inserted_id="mongo_id")

        # Act
        result = await repository.create(chat_create)

        # Assert
        assert result.title == "New Chat"  # Default from ChatCreate


# ===== Get Tests =====


class TestGet:
    """Test chat retrieval by ID"""

    @pytest.mark.asyncio
    async def test_get_existing_chat(self, repository, mock_collection):
        """Test retrieving existing chat"""
        # Arrange
        now = datetime.now(UTC)
        mock_collection.find_one.return_value = {
            "_id": "mongo_id",
            "chat_id": "chat_abc123",
            "user_id": "user_xyz789",
            "title": "AAPL Analysis",
            "is_archived": False,
            "ui_state": {
                "current_symbol": "AAPL",
                "current_interval": "1d",
                "current_date_range": {"start": None, "end": None},
                "active_overlays": {},
            },
            "last_message_preview": "Preview text",
            "created_at": now,
            "updated_at": now,
            "last_message_at": now,
        }

        # Act
        result = await repository.get("chat_abc123")

        # Assert
        assert result is not None
        assert result.chat_id == "chat_abc123"
        assert result.title == "AAPL Analysis"
        assert result.ui_state.current_symbol == "AAPL"
        mock_collection.find_one.assert_called_once_with({"chat_id": "chat_abc123"})

    @pytest.mark.asyncio
    async def test_get_nonexistent_chat(self, repository, mock_collection):
        """Test retrieving non-existent chat returns None"""
        # Arrange
        mock_collection.find_one.return_value = None

        # Act
        result = await repository.get("nonexistent")

        # Assert
        assert result is None


# ===== List Tests =====


class TestListByUser:
    """Test listing user chats"""

    @pytest.mark.asyncio
    async def test_list_by_user_default_params(self, repository, mock_collection):
        """Test listing chats with default parameters"""
        # Arrange
        now = datetime.now(UTC)

        async def mock_async_iter():
            chats = [
                {
                    "_id": "id1",
                    "chat_id": "chat_1",
                    "user_id": "user_123",
                    "title": "Chat 1",
                    "is_archived": False,
                    "ui_state": {
                        "current_symbol": None,
                        "current_interval": "1d",
                        "current_date_range": {"start": None, "end": None},
                        "active_overlays": {},
                    },
                    "last_message_preview": None,
                    "created_at": now,
                    "updated_at": now,
                    "last_message_at": None,
                },
                {
                    "_id": "id2",
                    "chat_id": "chat_2",
                    "user_id": "user_123",
                    "title": "Chat 2",
                    "is_archived": False,
                    "ui_state": {
                        "current_symbol": "AAPL",
                        "current_interval": "1d",
                        "current_date_range": {"start": None, "end": None},
                        "active_overlays": {},
                    },
                    "last_message_preview": "Message preview",
                    "created_at": now,
                    "updated_at": now,
                    "last_message_at": now,
                },
            ]
            for chat in chats:
                yield chat

        mock_cursor = Mock()
        mock_cursor.sort = Mock(return_value=mock_cursor)
        mock_cursor.skip = Mock(return_value=mock_cursor)
        mock_cursor.limit = Mock(return_value=mock_cursor)
        mock_cursor.__aiter__ = lambda self: mock_async_iter()
        mock_collection.find.return_value = mock_cursor

        # Act
        result = await repository.list_by_user("user_123")

        # Assert
        assert len(result) == 2
        assert result[0].chat_id == "chat_1"
        assert result[1].chat_id == "chat_2"

        # Verify query excludes archived chats by default
        mock_collection.find.assert_called_once_with(
            {"user_id": "user_123", "is_archived": False}
        )
        mock_cursor.sort.assert_called_once_with("updated_at", -1)
        mock_cursor.skip.assert_called_once_with(0)
        mock_cursor.limit.assert_called_once_with(50)

    @pytest.mark.asyncio
    async def test_list_by_user_with_pagination(self, repository, mock_collection):
        """Test listing chats with pagination"""

        # Arrange
        async def mock_async_iter():
            return
            yield  # Make this an async generator

        mock_cursor = Mock()
        mock_cursor.sort = Mock(return_value=mock_cursor)
        mock_cursor.skip = Mock(return_value=mock_cursor)
        mock_cursor.limit = Mock(return_value=mock_cursor)
        mock_cursor.__aiter__ = lambda self: mock_async_iter()
        mock_collection.find.return_value = mock_cursor

        # Act
        await repository.list_by_user("user_123", limit=10, skip=20)

        # Assert
        mock_cursor.skip.assert_called_once_with(20)
        mock_cursor.limit.assert_called_once_with(10)

    @pytest.mark.asyncio
    async def test_list_by_user_include_archived(self, repository, mock_collection):
        """Test listing chats including archived"""

        # Arrange
        async def mock_async_iter():
            return
            yield  # Make this an async generator

        mock_cursor = Mock()
        mock_cursor.sort = Mock(return_value=mock_cursor)
        mock_cursor.skip = Mock(return_value=mock_cursor)
        mock_cursor.limit = Mock(return_value=mock_cursor)
        mock_cursor.__aiter__ = lambda self: mock_async_iter()
        mock_collection.find.return_value = mock_cursor

        # Act
        await repository.list_by_user("user_123", include_archived=True)

        # Assert
        # When include_archived=True, query should not filter by is_archived
        mock_collection.find.assert_called_once_with({"user_id": "user_123"})


# ===== Update Tests =====


class TestUpdate:
    """Test chat metadata updates"""

    @pytest.mark.asyncio
    async def test_update_title_only(self, repository, mock_collection):
        """Test updating only the title"""
        # Arrange
        now = datetime.now(UTC)
        mock_collection.find_one_and_update.return_value = {
            "_id": "mongo_id",
            "chat_id": "chat_123",
            "user_id": "user_456",
            "title": "Updated Title",
            "is_archived": False,
            "ui_state": {
                "current_symbol": None,
                "current_interval": "1d",
                "current_date_range": {"start": None, "end": None},
                "active_overlays": {},
            },
            "last_message_preview": None,
            "created_at": now,
            "updated_at": now,
            "last_message_at": None,
        }

        chat_update = ChatUpdate(title="Updated Title")

        # Act
        result = await repository.update("chat_123", chat_update)

        # Assert
        assert result is not None
        assert result.title == "Updated Title"
        mock_collection.find_one_and_update.assert_called_once()

        # Verify update dict contains title and updated_at
        update_dict = mock_collection.find_one_and_update.call_args[0][1]["$set"]
        assert "title" in update_dict
        assert "updated_at" in update_dict

    @pytest.mark.asyncio
    async def test_update_archive_status(self, repository, mock_collection):
        """Test archiving a chat"""
        # Arrange
        now = datetime.now(UTC)
        mock_collection.find_one_and_update.return_value = {
            "_id": "mongo_id",
            "chat_id": "chat_123",
            "user_id": "user_456",
            "title": "Chat Title",
            "is_archived": True,
            "ui_state": {
                "current_symbol": None,
                "current_interval": "1d",
                "current_date_range": {"start": None, "end": None},
                "active_overlays": {},
            },
            "last_message_preview": None,
            "created_at": now,
            "updated_at": now,
            "last_message_at": None,
        }

        chat_update = ChatUpdate(is_archived=True)

        # Act
        result = await repository.update("chat_123", chat_update)

        # Assert
        assert result is not None
        assert result.is_archived is True

    @pytest.mark.asyncio
    async def test_update_ui_state_via_update(self, repository, mock_collection):
        """Test updating UI state through general update method"""
        # Arrange
        now = datetime.now(UTC)
        new_ui_state = UIState(
            current_symbol="GOOGL",
            current_interval="1h",
            current_date_range={"start": "2025-01-01", "end": "2025-10-01"},
            active_overlays={"stochastic": {"enabled": True}},
        )

        mock_collection.find_one_and_update.return_value = {
            "_id": "mongo_id",
            "chat_id": "chat_123",
            "user_id": "user_456",
            "title": "Chat Title",
            "is_archived": False,
            "ui_state": new_ui_state.model_dump(),
            "last_message_preview": None,
            "created_at": now,
            "updated_at": now,
            "last_message_at": None,
        }

        chat_update = ChatUpdate(ui_state=new_ui_state)

        # Act
        result = await repository.update("chat_123", chat_update)

        # Assert
        assert result is not None
        assert result.ui_state.current_symbol == "GOOGL"
        assert result.ui_state.current_interval == "1h"

    @pytest.mark.asyncio
    async def test_update_nonexistent_chat(self, repository, mock_collection):
        """Test updating non-existent chat returns None"""
        # Arrange
        mock_collection.find_one_and_update.return_value = None
        chat_update = ChatUpdate(title="New Title")

        # Act
        result = await repository.update("nonexistent", chat_update)

        # Assert
        assert result is None


class TestUpdateUIState:
    """Test dedicated UI state update method"""

    @pytest.mark.asyncio
    async def test_update_ui_state_success(self, repository, mock_collection):
        """Test updating UI state"""
        # Arrange
        now = datetime.now(UTC)
        new_ui_state = UIState(
            current_symbol="TSLA",
            current_interval="15m",
            current_date_range={"start": None, "end": None},
            active_overlays={"fibonacci": {"enabled": True, "levels": [0.382, 0.618]}},
        )

        mock_collection.find_one_and_update.return_value = {
            "_id": "mongo_id",
            "chat_id": "chat_123",
            "user_id": "user_456",
            "title": "TSLA Trading",
            "is_archived": False,
            "ui_state": new_ui_state.model_dump(),
            "last_message_preview": None,
            "created_at": now,
            "updated_at": now,
            "last_message_at": None,
        }

        # Act
        result = await repository.update_ui_state("chat_123", new_ui_state)

        # Assert
        assert result is not None
        assert result.ui_state.current_symbol == "TSLA"
        assert result.ui_state.current_interval == "15m"
        assert "fibonacci" in result.ui_state.active_overlays

        # Verify update includes ui_state and updated_at
        update_dict = mock_collection.find_one_and_update.call_args[0][1]["$set"]
        assert "ui_state" in update_dict
        assert "updated_at" in update_dict


class TestUpdateLastMessageAt:
    """Test last message timestamp update"""

    @pytest.mark.asyncio
    async def test_update_last_message_at_success(self, repository, mock_collection):
        """Test updating last message timestamp"""
        # Arrange
        now = datetime.now(UTC)
        mock_collection.find_one_and_update.return_value = {
            "_id": "mongo_id",
            "chat_id": "chat_123",
            "user_id": "user_456",
            "title": "Chat Title",
            "is_archived": False,
            "ui_state": {
                "current_symbol": None,
                "current_interval": "1d",
                "current_date_range": {"start": None, "end": None},
                "active_overlays": {},
            },
            "last_message_preview": None,
            "created_at": now,
            "updated_at": now,
            "last_message_at": now,
        }

        # Act
        result = await repository.update_last_message_at("chat_123")

        # Assert
        assert result is not None
        assert result.last_message_at is not None
        mock_collection.find_one_and_update.assert_called_once()

        # Verify both timestamps are updated
        update_dict = mock_collection.find_one_and_update.call_args[0][1]["$set"]
        assert "last_message_at" in update_dict
        assert "updated_at" in update_dict

    @pytest.mark.asyncio
    async def test_update_last_message_at_nonexistent(
        self, repository, mock_collection
    ):
        """Test updating last message timestamp for non-existent chat"""
        # Arrange
        mock_collection.find_one_and_update.return_value = None

        # Act
        result = await repository.update_last_message_at("nonexistent")

        # Assert
        assert result is None


# ===== Symbol Lookup Tests =====


class TestFindBySymbol:
    """Test symbol-per-chat pattern"""

    @pytest.mark.asyncio
    async def test_find_by_symbol_success(self, repository, mock_collection):
        """Test finding active chat by symbol"""
        # Arrange
        now = datetime.now(UTC)
        mock_collection.find_one.return_value = {
            "_id": "mongo_id",
            "chat_id": "chat_aapl",
            "user_id": "user_123",
            "title": "AAPL Analysis",
            "is_archived": False,
            "ui_state": {
                "current_symbol": "AAPL",
                "current_interval": "1d",
                "current_date_range": {"start": None, "end": None},
                "active_overlays": {},
            },
            "last_message_preview": "Preview",
            "created_at": now,
            "updated_at": now,
            "last_message_at": now,
        }

        # Act
        result = await repository.find_by_symbol("user_123", "AAPL")

        # Assert
        assert result is not None
        assert result.chat_id == "chat_aapl"
        assert result.ui_state.current_symbol == "AAPL"

        # Verify query filters by user, symbol, and archived status
        mock_collection.find_one.assert_called_once_with(
            {
                "user_id": "user_123",
                "ui_state.current_symbol": "AAPL",
                "is_archived": False,
            }
        )

    @pytest.mark.asyncio
    async def test_find_by_symbol_not_found(self, repository, mock_collection):
        """Test finding chat by symbol when none exists"""
        # Arrange
        mock_collection.find_one.return_value = None

        # Act
        result = await repository.find_by_symbol("user_123", "NONEXISTENT")

        # Assert
        assert result is None


# ===== Delete Tests =====


class TestDelete:
    """Test chat deletion"""

    @pytest.mark.asyncio
    async def test_delete_success(self, repository, mock_collection):
        """Test successfully deleting a chat"""
        # Arrange
        mock_result = Mock()
        mock_result.deleted_count = 1
        mock_collection.delete_one.return_value = mock_result

        # Act
        result = await repository.delete("chat_123")

        # Assert
        assert result is True
        mock_collection.delete_one.assert_called_once_with({"chat_id": "chat_123"})

    @pytest.mark.asyncio
    async def test_delete_not_found(self, repository, mock_collection):
        """Test deleting non-existent chat returns False"""
        # Arrange
        mock_result = Mock()
        mock_result.deleted_count = 0
        mock_collection.delete_one.return_value = mock_result

        # Act
        result = await repository.delete("nonexistent")

        # Assert
        assert result is False


# ===== Write-Time Translation Tests =====


def _doc_from_update(chat_id: str, update_dict: dict) -> dict:
    """Build a fake Mongo document reflecting the $set payload sent by update()."""
    now = datetime.now(UTC)
    base = {
        "_id": "mongo_id",
        "chat_id": chat_id,
        "user_id": None,
        "title": "x",
        "title_zh": None,
        "is_archived": False,
        "ui_state": {
            "current_symbol": None,
            "current_interval": "1d",
            "current_date_range": {"start": None, "end": None},
            "active_overlays": {},
        },
        "last_message_preview": None,
        "last_message_preview_zh": None,
        "created_at": now,
        "updated_at": now,
        "last_message_at": None,
    }
    base.update(update_dict)
    return base


@pytest.mark.asyncio
async def test_create_persists_title_zh(chat_repository, mock_collection):
    from unittest.mock import AsyncMock, patch

    from src.models.chat import ChatCreate

    with patch(
        "src.database.repositories.chat_repository.translate_for_persistence",
        new=AsyncMock(return_value={"title_zh": "新会话"}),
    ):
        chat = await chat_repository.create(ChatCreate(title="New Chat"))

    assert chat.title == "New Chat"
    assert chat.title_zh == "新会话"
    mock_collection.insert_one.assert_awaited_once()
    inserted_doc = mock_collection.insert_one.await_args.args[0]
    assert inserted_doc["title"] == "New Chat"
    assert inserted_doc["title_zh"] == "新会话"


@pytest.mark.asyncio
async def test_update_translates_title_and_preview_when_provided(
    chat_repository, mock_collection
):
    from unittest.mock import AsyncMock, patch

    from src.models.chat import ChatCreate, ChatUpdate

    with patch(
        "src.database.repositories.chat_repository.translate_for_persistence",
        new=AsyncMock(return_value={"title_zh": None}),
    ):
        chat = await chat_repository.create(ChatCreate(title="x"))

    # Mongo returns the updated document, mirroring what update() $set
    mock_collection.find_one_and_update.return_value = _doc_from_update(
        chat.chat_id,
        {
            "title": "AAPL Analysis",
            "title_zh": "苹果分析",
            "last_message_preview": "Based on Fibonacci...",
            "last_message_preview_zh": "基于斐波那契…",
        },
    )

    with patch(
        "src.database.repositories.chat_repository.translate_for_persistence",
        new=AsyncMock(
            return_value={
                "title_zh": "苹果分析",
                "last_message_preview_zh": "基于斐波那契…",
            }
        ),
    ) as mock_t:
        updated = await chat_repository.update(
            chat.chat_id,
            ChatUpdate(
                title="AAPL Analysis", last_message_preview="Based on Fibonacci..."
            ),
        )

    assert updated is not None
    assert updated.title_zh == "苹果分析"
    assert updated.last_message_preview_zh == "基于斐波那契…"
    args, _ = mock_t.call_args
    assert args[0] == {
        "title": "AAPL Analysis",
        "last_message_preview": "Based on Fibonacci...",
    }


@pytest.mark.asyncio
async def test_update_skips_translation_when_no_text_fields_change(
    chat_repository, mock_collection
):
    from unittest.mock import AsyncMock, patch

    from src.models.chat import ChatCreate, ChatUpdate

    with patch(
        "src.database.repositories.chat_repository.translate_for_persistence",
        new=AsyncMock(return_value={}),
    ):
        chat = await chat_repository.create(ChatCreate(title="x"))

    mock_collection.find_one_and_update.return_value = _doc_from_update(
        chat.chat_id, {"is_archived": True}
    )

    mock_t = AsyncMock()
    with patch(
        "src.database.repositories.chat_repository.translate_for_persistence",
        new=mock_t,
    ):
        await chat_repository.update(chat.chat_id, ChatUpdate(is_archived=True))

    mock_t.assert_not_called()


@pytest.mark.asyncio
async def test_update_skips_zh_merge_when_translator_returns_all_none(
    chat_repository, mock_collection
):
    """Transient LLM failure must not clobber existing _zh fields with None.

    persistence_translator returns all-None on whole-batch failure. The repo
    must detect this and skip merging _zh into update_dict so a previously-good
    Chinese title survives the failed update.
    """
    from unittest.mock import AsyncMock, patch

    from src.models.chat import ChatCreate, ChatUpdate

    with patch(
        "src.database.repositories.chat_repository.translate_for_persistence",
        new=AsyncMock(return_value={"title_zh": None}),
    ):
        chat = await chat_repository.create(ChatCreate(title="x"))

    captured_update: dict = {}

    async def _capture(filter_, update_, **_kw):
        captured_update.update(update_["$set"])
        return _doc_from_update(chat.chat_id, update_["$set"])

    mock_collection.find_one_and_update.side_effect = _capture

    with patch(
        "src.database.repositories.chat_repository.translate_for_persistence",
        new=AsyncMock(return_value={"title_zh": None}),
    ):
        await chat_repository.update(chat.chat_id, ChatUpdate(title="AAPL Analysis"))

    assert "title" in captured_update
    assert "title_zh" not in captured_update


@pytest.mark.asyncio
async def test_update_writes_only_non_none_zh_fields(chat_repository, mock_collection):
    """Per-key filter: a None entry for one field must not pollute update_dict
    even if a sibling field's translation succeeded."""
    from unittest.mock import AsyncMock, patch

    from src.models.chat import ChatCreate, ChatUpdate

    with patch(
        "src.database.repositories.chat_repository.translate_for_persistence",
        new=AsyncMock(
            return_value={"title_zh": "AAPL 分析", "last_message_preview_zh": None}
        ),
    ):
        chat = await chat_repository.create(ChatCreate(title="x"))

    captured_update: dict = {}

    async def _capture(filter_, update_, **_kw):
        captured_update.update(update_["$set"])
        return _doc_from_update(chat.chat_id, update_["$set"])

    mock_collection.find_one_and_update.side_effect = _capture

    with patch(
        "src.database.repositories.chat_repository.translate_for_persistence",
        new=AsyncMock(
            return_value={"title_zh": "AAPL 分析", "last_message_preview_zh": None}
        ),
    ):
        await chat_repository.update(
            chat.chat_id,
            ChatUpdate(title="AAPL Analysis", last_message_preview="   "),
        )

    assert captured_update["title_zh"] == "AAPL 分析"
    assert "last_message_preview_zh" not in captured_update
