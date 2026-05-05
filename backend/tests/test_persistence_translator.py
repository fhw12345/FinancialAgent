"""Tests for the persistence_translator boundary.

Covers:
- success path: every non-empty field gets a _zh translation
- LLM/service failure: every _zh value is None, no exception bubbles up
- empty / whitespace-only fields short-circuit without calling the LLM
- empty input dict returns empty result, no LLM round-trip
- input dict iteration order is preserved in the output
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from src.services.persistence_translator import translate_for_persistence


class FakeRedis:
    """Minimal stand-in for RedisCache used by translation_service."""

    async def get(self, key: str) -> str | None:
        return None

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        return True


@pytest.mark.asyncio
async def test_success_path_translates_all_fields() -> None:
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
async def test_llm_failure_returns_none_for_all_fields() -> None:
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
async def test_empty_string_field_short_circuits() -> None:
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
    mock_translate.assert_called_once_with(["Hello"], "zh-CN", fake_redis)


@pytest.mark.asyncio
async def test_empty_input_dict_returns_empty() -> None:
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
async def test_dict_iteration_order_preserved() -> None:
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
