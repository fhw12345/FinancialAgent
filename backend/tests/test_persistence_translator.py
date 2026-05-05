"""Tests for persistence_translator boundary."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.services.persistence_translator import translate_for_persistence


class FakeRedis:
    """Minimal stand-in for RedisCache used by translation_service."""
    async def get(self, key):  # noqa: ARG002
        return None

    async def set(self, key, value, ttl_seconds=None):  # noqa: ARG002
        return None


@pytest.mark.asyncio
async def test_success_path_translates_all_fields():
    """All non-empty fields get _zh values when LLM succeeds."""
    fake_redis = FakeRedis()
    with patch(
        "src.services.persistence_translator.translate_batch",
        new=AsyncMock(return_value=["你好", "世界"]),
    ):
        out = await translate_for_persistence(
            {"content": "Hello", "title": "World"},
            redis_cache=fake_redis,
        )
    assert out == {"content_zh": "你好", "title_zh": "世界"}


@pytest.mark.asyncio
async def test_llm_failure_returns_none_for_all_fields():
    """When LLM/service raises, all _zh values are None and no exception bubbles up."""
    fake_redis = FakeRedis()
    with patch(
        "src.services.persistence_translator.translate_batch",
        new=AsyncMock(side_effect=RuntimeError("anthropic 503")),
    ):
        out = await translate_for_persistence(
            {"content": "Hello", "title": "World"},
            redis_cache=fake_redis,
        )
    assert out == {"content_zh": None, "title_zh": None}


@pytest.mark.asyncio
async def test_empty_string_field_short_circuits():
    """Empty / whitespace-only fields return None without LLM call."""
    fake_redis = FakeRedis()
    mock_translate = AsyncMock(return_value=["你好"])
    with patch(
        "src.services.persistence_translator.translate_batch",
        new=mock_translate,
    ):
        out = await translate_for_persistence(
            {"content": "Hello", "title": "", "preview": "   "},
            redis_cache=fake_redis,
        )
    assert out == {"content_zh": "你好", "title_zh": None, "preview_zh": None}
    # Only "Hello" was passed to translate_batch
    args, _ = mock_translate.call_args
    assert args[0] == ["Hello"]


@pytest.mark.asyncio
async def test_empty_input_dict_returns_empty():
    """No fields → no LLM call, empty result."""
    fake_redis = FakeRedis()
    mock_translate = AsyncMock()
    with patch(
        "src.services.persistence_translator.translate_batch",
        new=mock_translate,
    ):
        out = await translate_for_persistence({}, redis_cache=fake_redis)
    assert out == {}
    mock_translate.assert_not_called()


@pytest.mark.asyncio
async def test_dict_iteration_order_preserved():
    """Field-to-translation mapping must match input order even if dict has many keys."""
    fake_redis = FakeRedis()
    with patch(
        "src.services.persistence_translator.translate_batch",
        new=AsyncMock(return_value=["A", "B", "C"]),
    ):
        out = await translate_for_persistence(
            {"f1": "one", "f2": "two", "f3": "three"},
            redis_cache=fake_redis,
        )
    assert out == {"f1_zh": "A", "f2_zh": "B", "f3_zh": "C"}
