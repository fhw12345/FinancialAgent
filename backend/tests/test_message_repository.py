"""Tests for MessageRepository.create() write-time translation wiring."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.database.repositories.message_repository import MessageRepository
from src.models.message import MessageCreate


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
def mock_collection():
    """Mock MongoDB messages collection."""
    collection = Mock()
    collection.insert_one = AsyncMock()
    collection.find_one = AsyncMock()
    collection.delete_many = AsyncMock()
    return collection


@pytest.fixture
def message_repository(mock_collection, fake_redis):
    return MessageRepository(mock_collection, fake_redis)


@pytest.mark.asyncio
async def test_delete_messages_by_ids(message_repository, mock_collection):
    mock_collection.delete_many.return_value = type(
        "DeleteResult",
        (),
        {"deleted_count": 2},
    )()

    deleted = await message_repository.delete_messages_by_ids(
        chat_id="chat_1",
        message_ids=["msg_1", "msg_2"],
    )

    assert deleted == 2
    mock_collection.delete_many.assert_awaited_once_with(
        {
            "chat_id": "chat_1",
            "message_id": {"$in": ["msg_1", "msg_2"]},
        }
    )


@pytest.mark.asyncio
async def test_create_preserves_explicit_logical_timestamp(
    message_repository,
    mock_collection,
):
    logical_timestamp = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)

    with patch(
        "src.database.repositories.message_repository.translate_for_persistence",
        new=AsyncMock(return_value={"content_zh": None}),
    ):
        await message_repository.create(
            MessageCreate(
                chat_id="chat_1",
                role="assistant",
                content="Summary",
                source="llm",
                timestamp=logical_timestamp,
            )
        )

    inserted = mock_collection.insert_one.await_args.args[0]
    assert inserted["timestamp"] == logical_timestamp


@pytest.mark.asyncio
async def test_create_persists_content_zh_on_translation_success(
    message_repository, mock_collection
):
    """When translation succeeds, the inserted document has content_zh populated."""
    create_payload = MessageCreate(
        chat_id="chat_test_zh",
        role="assistant",
        content="Hello world",
        source="llm",
    )
    with patch(
        "src.database.repositories.message_repository.translate_for_persistence",
        new=AsyncMock(return_value={"content_zh": "你好世界"}),
    ):
        msg = await message_repository.create(create_payload)

    assert msg.content_zh == "你好世界"
    # Verify the document inserted into Mongo carries content_zh too.
    mock_collection.insert_one.assert_awaited_once()
    inserted_doc = mock_collection.insert_one.await_args.args[0]
    assert inserted_doc["content_zh"] == "你好世界"
    assert inserted_doc["content"] == "Hello world"


@pytest.mark.asyncio
async def test_create_stores_english_when_translation_fails(
    message_repository, mock_collection
):
    """Translation failure does NOT block English persistence; content_zh is None."""
    create_payload = MessageCreate(
        chat_id="chat_test_zh_fail",
        role="assistant",
        content="Hello world",
        source="llm",
    )
    with patch(
        "src.database.repositories.message_repository.translate_for_persistence",
        new=AsyncMock(return_value={"content_zh": None}),
    ):
        msg = await message_repository.create(create_payload)

    assert msg.content == "Hello world"
    assert msg.content_zh is None
    mock_collection.insert_one.assert_awaited_once()
    inserted_doc = mock_collection.insert_one.await_args.args[0]
    assert inserted_doc["content"] == "Hello world"
    assert inserted_doc["content_zh"] is None
