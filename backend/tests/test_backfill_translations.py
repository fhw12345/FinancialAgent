"""Tests for backfill_translations script."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from scripts.backfill_translations import backfill_collection


@pytest_asyncio.fixture
async def messages_collection():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient("mongodb://mongodb:27017")
    coll = client["financial_agent_test"]["messages"]
    await coll.delete_many({})
    yield coll
    await coll.delete_many({})
    client.close()


@pytest.fixture
def fake_redis():
    class _Fake:
        async def get(self, k):  # noqa: ARG002
            return None

        async def set(self, k, v, ttl_seconds=None):  # noqa: ARG002
            return None

    return _Fake()


@pytest.mark.asyncio
async def test_dry_run_does_not_write(messages_collection, fake_redis):
    await messages_collection.insert_many(
        [
            {"message_id": "m1", "content": "Hello", "content_zh": None},
            {"message_id": "m2", "content": "World", "content_zh": None},
        ]
    )
    with patch(
        "scripts.backfill_translations.translate_for_persistence",
        new=AsyncMock(return_value={"content_zh": "TRANSLATED"}),
    ):
        stats = await backfill_collection(
            messages_collection,
            text_fields=["content"],
            redis_cache=fake_redis,
            batch_size=10,
            dry_run=True,
        )
    assert stats["would_update"] == 2
    assert stats["updated"] == 0
    raw = await messages_collection.find_one({"message_id": "m1"})
    assert raw["content_zh"] is None


@pytest.mark.asyncio
async def test_skips_documents_with_existing_translation(
    messages_collection, fake_redis
):
    await messages_collection.insert_many(
        [
            {"message_id": "m1", "content": "Hello", "content_zh": "你好"},
            {"message_id": "m2", "content": "World", "content_zh": None},
        ]
    )
    mock_t = AsyncMock(return_value={"content_zh": "世界"})
    with patch(
        "scripts.backfill_translations.translate_for_persistence",
        new=mock_t,
    ):
        stats = await backfill_collection(
            messages_collection,
            text_fields=["content"],
            redis_cache=fake_redis,
            batch_size=10,
        )
    assert stats["updated"] == 1
    args, _ = mock_t.call_args_list[0]
    assert args[0] == {"content": "World"}


@pytest.mark.asyncio
async def test_partial_failure_does_not_stop_batch(messages_collection, fake_redis):
    await messages_collection.insert_many(
        [
            {"message_id": f"m{i}", "content": f"text{i}", "content_zh": None}
            for i in range(3)
        ]
    )
    call_count = {"n": 0}

    async def flaky(_fields, redis_cache, target_lang="zh-CN"):  # noqa: ARG001
        call_count["n"] += 1
        if call_count["n"] == 2:
            return {"content_zh": None}  # translation failure
        return {"content_zh": "ok"}

    with patch(
        "scripts.backfill_translations.translate_for_persistence",
        new=flaky,
    ):
        stats = await backfill_collection(
            messages_collection,
            text_fields=["content"],
            redis_cache=fake_redis,
            batch_size=10,
        )
    assert stats["updated"] == 2
    assert stats["failed"] == 1
