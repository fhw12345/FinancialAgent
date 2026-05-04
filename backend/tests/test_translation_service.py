"""Tests for translation_service + /api/translate route.

Covers:
- Cache hit short-circuit (no LLM call)
- Cache miss → LLM batch call → results cached
- LLM error → fall back to original English
- Mixed hit/miss → only misses go to LLM, order preserved
- English locale short-circuit
- Route returns same length & order as input
- Malformed LLM output → fall back to originals
"""

from __future__ import annotations

import json
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
    """Build a fake AIMessage-like object with .content = JSON array."""
    m = MagicMock()
    m.content = json.dumps(translations, ensure_ascii=False)
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
    seed = {svc._cache_key(t, "zh-CN"): zh for t, zh in zip(texts, ["NVDA强劲", "维持仓位"])}
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
async def test_llm_error_falls_back_to_original() -> None:
    texts = ["foo", "bar"]
    redis = FakeRedis()
    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(side_effect=RuntimeError("upstream timeout"))
    with patch.object(svc, "get_llm", return_value=fake_llm):
        out = await svc.translate_batch(texts, "zh-CN", redis)  # type: ignore[arg-type]
    assert out == ["foo", "bar"]
    # Nothing should have been cached on failure
    assert redis.set_calls == []


@pytest.mark.asyncio
async def test_malformed_llm_output_falls_back() -> None:
    texts = ["x", "y"]
    redis = FakeRedis()
    fake_llm = MagicMock()
    bad = MagicMock()
    bad.content = "I refuse to translate. Sorry."
    fake_llm.ainvoke = AsyncMock(return_value=bad)
    with patch.object(svc, "get_llm", return_value=fake_llm):
        out = await svc.translate_batch(texts, "zh-CN", redis)  # type: ignore[arg-type]
    assert out == ["x", "y"]
    assert redis.set_calls == []


@pytest.mark.asyncio
async def test_wrong_count_falls_back() -> None:
    texts = ["a", "b", "c"]
    redis = FakeRedis()
    fake_llm = MagicMock()
    # Only two items returned, expected three
    fake_llm.ainvoke = AsyncMock(return_value=_llm_resp(["甲", "乙"]))
    with patch.object(svc, "get_llm", return_value=fake_llm):
        out = await svc.translate_batch(texts, "zh-CN", redis)  # type: ignore[arg-type]
    assert out == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_handles_markdown_fenced_json() -> None:
    """Some models wrap JSON in ```json ... ``` despite instructions."""
    texts = ["hello"]
    redis = FakeRedis()
    fake_llm = MagicMock()
    fake_resp = MagicMock()
    fake_resp.content = '```json\n["你好"]\n```'
    fake_llm.ainvoke = AsyncMock(return_value=fake_resp)
    with patch.object(svc, "get_llm", return_value=fake_llm):
        out = await svc.translate_batch(texts, "zh-CN", redis)  # type: ignore[arg-type]
    assert out == ["你好"]


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
