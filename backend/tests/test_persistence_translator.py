"""Tests for the persistence_translator boundary.

Covers:
- success path: every non-empty field gets a _zh translation
- LLM/service failure: every _zh value is None, no exception bubbles up
- empty / whitespace-only fields short-circuit without calling the LLM
- empty input dict returns empty result, no LLM round-trip
- input dict iteration order is preserved in the output
- CJK guard: already-Chinese fields are skipped (no _zh sibling, no LLM call)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.services.persistence_translator import (
    _is_already_cjk,
    translate_for_persistence,
)


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


def test_is_already_cjk_detects_chinese_title() -> None:
    """Mixed-script Chinese title with English ticker still trips the guard."""
    assert _is_already_cjk("# AAPL 苹果公司研究报告\n业绩稳健") is True


def test_is_already_cjk_lets_english_through() -> None:
    """Pure English fundamentals report is not flagged as CJK."""
    assert _is_already_cjk("AAPL Inc fundamentals report") is False


def test_is_already_cjk_handles_empty() -> None:
    assert _is_already_cjk("") is False


@pytest.mark.asyncio
async def test_cjk_text_skipped_no_translate_batch_call() -> None:
    """Already-Chinese text must not be re-translated; no _zh sibling written."""
    fake_redis = FakeRedis()
    mock_translate = AsyncMock(return_value=["unused"])
    with patch(
        "src.services.persistence_translator.translate_batch",
        new=mock_translate,
    ):
        out = await translate_for_persistence(
            {"content": "# AAPL 苹果公司研究报告\n业绩稳健"},
            redis_cache=fake_redis,
        )
    assert out == {"content_zh": None}
    mock_translate.assert_not_called()


@pytest.mark.asyncio
async def test_cjk_skip_logs_warning_for_visibility(capsys) -> None:
    """The CJK skip path indicates either legacy data or a new leak in the
    analysis pipeline. After the English-lock patch it must surface as a
    WARNING (not INFO) so docker logs make future regressions obvious.
    """
    fake_redis = FakeRedis()
    with patch(
        "src.services.persistence_translator.translate_batch",
        new=AsyncMock(return_value=["unused"]),
    ):
        await translate_for_persistence(
            {"reasoning": "买入苹果，因为第四季度服务业务增长加速。"},
            redis_cache=fake_redis,
        )
    # structlog renders to stdout in tests; assert both the WARNING level
    # tag and the structured event name appear.
    captured = capsys.readouterr().out
    assert "translation_persistence_cjk_skip" in captured, (
        "CJK skip event must be logged so future analysis-pipeline leaks "
        "are visible in docker logs."
    )
    assert "warning" in captured.lower(), (
        "CJK skip must log at WARNING level (was INFO before 0.29.3)."
    )


@pytest.mark.asyncio
async def test_english_text_translates_normally() -> None:
    """Pure English text passes the guard and gets a _zh sibling."""
    fake_redis = FakeRedis()
    mock_translate = AsyncMock(return_value=["AAPL公司基本面报告"])
    with patch(
        "src.services.persistence_translator.translate_batch",
        new=mock_translate,
    ):
        out = await translate_for_persistence(
            {"content": "AAPL Inc fundamentals report"},
            redis_cache=fake_redis,
        )
    assert out == {"content_zh": "AAPL公司基本面报告"}
    mock_translate.assert_called_once_with(
        ["AAPL Inc fundamentals report"], "zh-CN", fake_redis
    )


@pytest.mark.asyncio
async def test_mixed_payload_only_translates_english_fields() -> None:
    """A batch with both English and Chinese fields only sends English to LLM."""
    fake_redis = FakeRedis()
    mock_translate = AsyncMock(return_value=["英文标题翻译"])
    with patch(
        "src.services.persistence_translator.translate_batch",
        new=mock_translate,
    ):
        out = await translate_for_persistence(
            {
                "english_title": "Apple Q3 earnings beat",
                "chinese_title": "苹果第三季度财报超预期",
            },
            redis_cache=fake_redis,
        )
    assert out == {
        "english_title_zh": "英文标题翻译",
        "chinese_title_zh": None,
    }
    mock_translate.assert_called_once_with(
        ["Apple Q3 earnings beat"], "zh-CN", fake_redis
    )
