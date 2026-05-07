"""Tests for translation_service + /api/translate route.

Covers:
- Cache hit short-circuit (no LLM call)
- Cache miss → LLM batch call → results cached
- LLM error → failed slots are None (write-path callers persist None)
- Mixed hit/miss → only misses go to LLM, order preserved
- English locale short-circuit
- Route returns same length & order as input, echoing English for None slots
- Malformed / wrong-count LLM output → all miss slots None
- Separator-protocol parser shape coverage
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies.chat_deps import get_redis
from src.main import app
from src.services import translation_service as svc


class FakeRedis:
    """In-memory stand-in for RedisCache that records calls."""

    def __init__(self, seed: dict[str, Any] | None = None) -> None:
        self.store: dict[str, Any] = dict(seed or {})
        self.set_calls: list[tuple[str, Any, int | None]] = []

    async def get(self, key: str) -> Any | None:
        return self.store.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> bool:
        self.store[key] = value
        self.set_calls.append((key, value, ttl_seconds))
        return True


def _llm_resp(translations: list[str]) -> MagicMock:
    """Build a fake AIMessage-like object with .content = separator-joined body."""
    m = MagicMock()
    m.content = f"\n{svc._SEPARATOR}\n".join(translations)
    return m


@pytest.mark.asyncio
async def test_english_locale_is_passthrough() -> None:
    redis = FakeRedis()
    out = await svc.translate_batch(["hello", "world"], "en", redis)  # type: ignore[arg-type]
    assert out == ["hello", "world"]
    assert redis.set_calls == []


@pytest.mark.asyncio
async def test_empty_input() -> None:
    redis = FakeRedis()
    out = await svc.translate_batch([], "zh-CN", redis)  # type: ignore[arg-type]
    assert out == []


@pytest.mark.asyncio
async def test_full_cache_hit_skips_llm() -> None:
    texts = ["NVDA strong", "Maintain position"]
    seed = {
        svc._cache_key(t, "zh-CN"): zh
        for t, zh in zip(texts, ["NVDA强劲", "维持仓位"], strict=True)
    }
    redis = FakeRedis(seed=seed)

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock()
    with patch.object(svc, "get_llm", return_value=fake_llm):
        out = await svc.translate_batch(texts, "zh-CN", redis)  # type: ignore[arg-type]

    assert out == ["NVDA强劲", "维持仓位"]
    fake_llm.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_full_cache_miss_calls_llm_and_caches() -> None:
    texts = ["BUY signal on AAPL", "SELL TSLA"]
    redis = FakeRedis()

    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=_llm_resp(["AAPL买入信号", "卖出TSLA"]))
    with patch.object(svc, "get_llm", return_value=fake_llm):
        out = await svc.translate_batch(texts, "zh-CN", redis)  # type: ignore[arg-type]

    assert out == ["AAPL买入信号", "卖出TSLA"]
    fake_llm.ainvoke.assert_awaited_once()
    # Both translations should have been cached with the 1-day TTL
    assert len(redis.set_calls) == 2
    for _, _, ttl in redis.set_calls:
        assert ttl == svc.CACHE_TTL_SECONDS


@pytest.mark.asyncio
async def test_partial_cache_hit_only_misses_go_to_llm_and_order_preserved() -> None:
    texts = ["A", "B", "C", "D"]
    # Pre-cache B and D
    seed = {
        svc._cache_key("B", "zh-CN"): "乙",
        svc._cache_key("D", "zh-CN"): "丁",
    }
    redis = FakeRedis(seed=seed)

    fake_llm = MagicMock()
    # LLM only sees the misses, in order: A then C
    fake_llm.ainvoke = AsyncMock(return_value=_llm_resp(["甲", "丙"]))
    with patch.object(svc, "get_llm", return_value=fake_llm):
        out = await svc.translate_batch(texts, "zh-CN", redis)  # type: ignore[arg-type]

    assert out == ["甲", "乙", "丙", "丁"]
    fake_llm.ainvoke.assert_awaited_once()
    # Verify LLM saw the misses in the right shape
    sent_messages = fake_llm.ainvoke.await_args.args[0]
    user_msg_content = sent_messages[1].content
    assert "1. A" in user_msg_content
    assert "2. C" in user_msg_content


@pytest.mark.asyncio
async def test_llm_error_returns_none_for_misses() -> None:
    texts = ["foo", "bar"]
    redis = FakeRedis()
    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(side_effect=RuntimeError("upstream timeout"))
    with patch.object(svc, "get_llm", return_value=fake_llm):
        out = await svc.translate_batch(texts, "zh-CN", redis)  # type: ignore[arg-type]
    assert out == [None, None]
    # Nothing should have been cached on failure
    assert redis.set_calls == []


@pytest.mark.asyncio
async def test_malformed_llm_output_returns_none() -> None:
    texts = ["x", "y"]
    redis = FakeRedis()
    fake_llm = MagicMock()
    bad = MagicMock()
    bad.content = "I refuse to translate. Sorry."  # one piece, expected two
    fake_llm.ainvoke = AsyncMock(return_value=bad)
    with patch.object(svc, "get_llm", return_value=fake_llm):
        out = await svc.translate_batch(texts, "zh-CN", redis)  # type: ignore[arg-type]
    assert out == [None, None]
    assert redis.set_calls == []


@pytest.mark.asyncio
async def test_wrong_count_returns_none() -> None:
    texts = ["a", "b", "c"]
    redis = FakeRedis()
    fake_llm = MagicMock()
    # Only two pieces returned, expected three
    fake_llm.ainvoke = AsyncMock(return_value=_llm_resp(["甲", "乙"]))
    with patch.object(svc, "get_llm", return_value=fake_llm):
        out = await svc.translate_batch(texts, "zh-CN", redis)  # type: ignore[arg-type]
    assert out == [None, None, None]


@pytest.mark.asyncio
async def test_handles_markdown_fenced_output() -> None:
    """Some models wrap output in ``` ... ``` despite instructions."""
    texts = ["hello"]
    redis = FakeRedis()
    fake_llm = MagicMock()
    fake_resp = MagicMock()
    fake_resp.content = "```\n你好\n```"
    fake_llm.ainvoke = AsyncMock(return_value=fake_resp)
    with patch.object(svc, "get_llm", return_value=fake_llm):
        out = await svc.translate_batch(texts, "zh-CN", redis)  # type: ignore[arg-type]
    assert out == ["你好"]


# ---------- _parse_llm_output (separator protocol) ----------


def test_parse_separator_simple() -> None:
    raw = f"A{svc._SEPARATOR}B"
    assert svc._parse_llm_output(raw, expected_count=2) == ["A", "B"]


def test_parse_separator_with_newlines() -> None:
    raw = f"译文A\n含多行\n内容{svc._SEPARATOR}译文B\n第二段"
    out = svc._parse_llm_output(raw, expected_count=2)
    assert out is not None
    assert len(out) == 2
    assert "译文A" in out[0] and "\n" in out[0]
    assert out[1].startswith("译文B") and "第二段" in out[1]


def test_parse_separator_strips_md_fence() -> None:
    raw = f"```\nA{svc._SEPARATOR}B\n```"
    assert svc._parse_llm_output(raw, expected_count=2) == ["A", "B"]


def test_parse_separator_length_mismatch_returns_none() -> None:
    raw = f"A{svc._SEPARATOR}B"
    assert svc._parse_llm_output(raw, expected_count=3) is None


def test_parse_separator_empty_returns_none() -> None:
    assert svc._parse_llm_output("", expected_count=1) is None
    assert svc._parse_llm_output("   \n  ", expected_count=1) is None


# ---------- translate_batch None-element semantics ----------


@pytest.mark.asyncio
async def test_translate_batch_llm_fail_returns_none_elements() -> None:
    redis = FakeRedis()
    with patch.object(svc, "_llm_translate", AsyncMock(return_value=None)):
        out = await svc.translate_batch(["x", "y", "z"], "zh-CN", redis)  # type: ignore[arg-type]
    assert out == [None, None, None]
    assert redis.set_calls == []


@pytest.mark.asyncio
async def test_translate_batch_partial_cache_hit_partial_llm_fail() -> None:
    texts = ["A", "B", "C"]
    seed = {svc._cache_key("A", "zh-CN"): "甲"}  # only A is cached
    redis = FakeRedis(seed=seed)
    with patch.object(svc, "_llm_translate", AsyncMock(return_value=None)):
        out = await svc.translate_batch(texts, "zh-CN", redis)  # type: ignore[arg-type]
    assert out == ["甲", None, None]


@pytest.mark.asyncio
async def test_translate_batch_all_cache_hit_no_llm_call() -> None:
    texts = ["A", "B"]
    seed = {
        svc._cache_key("A", "zh-CN"): "甲",
        svc._cache_key("B", "zh-CN"): "乙",
    }
    redis = FakeRedis(seed=seed)
    mocked = AsyncMock(return_value=None)
    with patch.object(svc, "_llm_translate", mocked):
        out = await svc.translate_batch(texts, "zh-CN", redis)  # type: ignore[arg-type]
    assert out == ["甲", "乙"]
    mocked.assert_not_awaited()


# ---------- persistence_translator None propagation ----------


@pytest.mark.asyncio
async def test_translate_for_persistence_handles_none_elements() -> None:
    from src.services import persistence_translator as pt

    fake = AsyncMock(return_value=[None, "中文"])
    with patch.object(pt, "translate_batch", fake):
        out = await pt.translate_for_persistence(
            {"a": "Hello", "b": "World"},
            redis_cache=FakeRedis(),  # type: ignore[arg-type]
        )
    assert out == {"a_zh": None, "b_zh": "中文"}


# ---------- /api/translate route ----------


@pytest.fixture
def route_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def client(route_redis: FakeRedis):
    app.dependency_overrides[get_redis] = lambda: route_redis
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_route_returns_same_length_and_order(client: TestClient) -> None:
    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=_llm_resp(["甲", "乙"]))
    with patch.object(svc, "get_llm", return_value=fake_llm):
        r = client.post(
            "/api/translate",
            json={"texts": ["A", "B"], "target_lang": "zh-CN"},
        )
    assert r.status_code == 200
    assert r.json() == {"translations": ["甲", "乙"]}


def test_route_rejects_unsupported_lang(client: TestClient) -> None:
    r = client.post(
        "/api/translate",
        json={"texts": ["hi"], "target_lang": "ja-JP"},
    )
    assert r.status_code == 422


def test_route_rejects_oversize_batch(client: TestClient) -> None:
    r = client.post(
        "/api/translate",
        json={"texts": ["x"] * 100, "target_lang": "zh-CN"},
    )
    assert r.status_code == 422


def test_route_handles_empty_array(client: TestClient) -> None:
    r = client.post(
        "/api/translate",
        json={"texts": [], "target_lang": "zh-CN"},
    )
    assert r.status_code == 200
    assert r.json() == {"translations": []}


def test_route_echoes_english_for_none_slots(client: TestClient) -> None:
    """When translate_batch fails (None slots), the HTTP path returns English
    so the frontend has something to render. Persistence callers handle None
    differently (write None to mongo)."""
    fake_llm = MagicMock()
    bad = MagicMock()
    bad.content = "garbage no separator"  # one piece, expected two → None all
    fake_llm.ainvoke = AsyncMock(return_value=bad)
    with patch.object(svc, "get_llm", return_value=fake_llm):
        r = client.post(
            "/api/translate",
            json={"texts": ["foo", "bar"], "target_lang": "zh-CN"},
        )
    assert r.status_code == 200
    assert r.json() == {"translations": ["foo", "bar"]}
