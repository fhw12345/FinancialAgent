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

from datetime import UTC, datetime, timedelta
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
    collection.aggregate = Mock()
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


# ===== Create Tests =====


class TestCreate:
    """Test chat creation"""

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
    """Test listing chats via the aggregate pipeline.

    `list_by_user` now uses an aggregation that joins messages, sorts by
    effective recency (`last_message_at` else `created_at`), and filters out
    week-old empty shells. These tests assert that contract by mocking
    `collection.aggregate(pipeline)` and verifying the pipeline shape and
    the returned/ordering behavior of the documents it yields.
    """

    @staticmethod
    def _chat_doc(
        chat_id: str,
        *,
        created_at: datetime,
        last_message_at: datetime | None,
        title: str = "Chat",
        is_archived: bool = False,
    ) -> dict:
        """Build a Mongo doc shape matching what the aggregation yields after $project."""
        return {
            "chat_id": chat_id,
            "title": title,
            "is_archived": is_archived,
            "ui_state": {
                "current_symbol": None,
                "current_interval": "1d",
                "current_date_range": {"start": None, "end": None},
                "active_overlays": {},
            },
            "last_message_preview": None,
            "created_at": created_at,
            "updated_at": created_at,
            "last_message_at": last_message_at,
        }

    @staticmethod
    def _mock_aggregate(mock_collection, docs):
        """Wire `collection.aggregate(pipeline)` to async-iterate over `docs`.

        Captures the pipeline argument for later assertions.
        """
        captured: dict = {"pipeline": None}

        async def _aiter():
            for d in docs:
                yield d

        def _aggregate(pipeline):
            captured["pipeline"] = pipeline
            cursor = Mock()
            cursor.__aiter__ = lambda self: _aiter()
            return cursor

        mock_collection.aggregate.side_effect = _aggregate
        return captured

    @pytest.mark.asyncio
    async def test_list_by_user_default_params_sorts_and_excludes_archived(
        self, repository, mock_collection
    ):
        """Default params: builds aggregate with is_archived filter and skip/limit."""
        now = datetime.now(UTC)
        docs = [
            self._chat_doc(
                "chat_recent",
                created_at=now - timedelta(days=5),
                last_message_at=now - timedelta(hours=1),
            ),
            self._chat_doc(
                "chat_older",
                created_at=now - timedelta(days=2),
                last_message_at=None,
            ),
        ]
        captured = self._mock_aggregate(mock_collection, docs)

        result = await repository.list_by_user()

        assert [c.chat_id for c in result] == ["chat_recent", "chat_older"]

        pipeline = captured["pipeline"]
        # First stage filters out archived chats by default
        assert pipeline[0] == {"$match": {"is_archived": False}}

        # Pipeline must contain the message-count $lookup, the $addFields with
        # _effective_recency, the empty-shell $nor exclusion, a sort by
        # _effective_recency desc, and default $skip=0 / $limit=50.
        stage_kinds = [list(stage.keys())[0] for stage in pipeline]
        assert "$lookup" in stage_kinds
        assert "$addFields" in stage_kinds
        assert "$sort" in stage_kinds
        assert "$skip" in stage_kinds
        assert "$limit" in stage_kinds
        assert "$project" in stage_kinds

        sort_stage = next(s["$sort"] for s in pipeline if "$sort" in s)
        assert sort_stage == {"_effective_recency": -1}

        skip_stage = next(s["$skip"] for s in pipeline if "$skip" in s)
        limit_stage = next(s["$limit"] for s in pipeline if "$limit" in s)
        assert skip_stage == 0
        assert limit_stage == 50

    @pytest.mark.asyncio
    async def test_list_by_user_with_pagination(self, repository, mock_collection):
        """Pagination passes skip/limit into the aggregate pipeline."""
        captured = self._mock_aggregate(mock_collection, [])

        await repository.list_by_user(limit=10, skip=20)

        pipeline = captured["pipeline"]
        skip_stage = next(s["$skip"] for s in pipeline if "$skip" in s)
        limit_stage = next(s["$limit"] for s in pipeline if "$limit" in s)
        assert skip_stage == 20
        assert limit_stage == 10

    @pytest.mark.asyncio
    async def test_list_by_user_include_archived_drops_is_archived_match(
        self, repository, mock_collection
    ):
        """include_archived=True omits the leading is_archived $match stage."""
        captured = self._mock_aggregate(mock_collection, [])

        await repository.list_by_user(include_archived=True)

        pipeline = captured["pipeline"]
        # No leading {"$match": {"is_archived": False}} stage in the pipeline.
        for stage in pipeline:
            if "$match" in stage:
                assert stage["$match"] != {"is_archived": False}

    @pytest.mark.asyncio
    async def test_list_by_user_excludes_week_old_empty_shells(
        self, repository, mock_collection
    ):
        """Week-old shell with no messages and no last_message_at is excluded.

        The exclusion happens at the Mongo $nor stage; here we just verify that
        when the (correctly-filtered) aggregate yields no docs, the repo
        returns an empty list. The pipeline shape is asserted in the
        default-params test.
        """
        captured = self._mock_aggregate(mock_collection, [])

        result = await repository.list_by_user()

        assert result == []
        # Sanity: the $nor exclusion stage is present.
        pipeline = captured["pipeline"]
        nor_stages = [
            s["$match"] for s in pipeline if "$match" in s and "$nor" in s["$match"]
        ]
        assert len(nor_stages) == 1
        nor_clause = nor_stages[0]["$nor"][0]
        assert nor_clause["last_message_at"] is None
        assert nor_clause["_message_count"] == 0
        assert "$lt" in nor_clause["created_at"]

    @pytest.mark.asyncio
    async def test_list_by_user_includes_fresh_empty_shell(
        self, repository, mock_collection
    ):
        """Brand-new empty shell (created <7d ago) is still returned."""
        now = datetime.now(UTC)
        docs = [
            self._chat_doc(
                "chat_fresh_empty",
                created_at=now - timedelta(hours=1),
                last_message_at=None,
            ),
        ]
        self._mock_aggregate(mock_collection, docs)

        result = await repository.list_by_user()

        assert len(result) == 1
        assert result[0].chat_id == "chat_fresh_empty"

    @pytest.mark.asyncio
    async def test_list_by_user_orders_by_effective_recency(
        self, repository, mock_collection
    ):
        """A messaged chat with last_message_at=now-2h sorts ahead of a fresh
        empty chat created 1h ago.

        We assume Mongo applies the pipeline's $sort stage; here we just feed
        the docs back in the order the real Mongo would produce them and
        verify the repo preserves that order on its way out.
        """
        now = datetime.now(UTC)
        docs = [
            self._chat_doc(
                "chat_with_msgs",
                created_at=now - timedelta(days=10),
                last_message_at=now - timedelta(hours=2),
            ),
            self._chat_doc(
                "chat_fresh_empty",
                created_at=now - timedelta(hours=1),
                last_message_at=None,
            ),
        ]
        self._mock_aggregate(mock_collection, docs)

        result = await repository.list_by_user()

        assert [c.chat_id for c in result] == ["chat_with_msgs", "chat_fresh_empty"]


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
