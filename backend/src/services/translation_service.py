"""
Translation service — translate LLM-generated English text to Chinese on demand.

Why this exists:
    All system prompts stay English (preserves financial-domain term precision).
    When the UI is set to Simplified Chinese we translate model output before
    rendering. Cached so the same reasoning paragraph isn't billed twice.

Caching:
    Key: `llm_translation:{target_lang}:{sha1(text)}`
    TTL: 1 day. Long enough that re-rendering the same Decision Tracker page
    over a day is free; short enough that storage doesn't grow forever and
    upstream prompt revisions get re-translated within a sane window.

Batching:
    `translate_batch()` takes N texts, fetches Redis hits, groups the misses
    into one Anthropic call (one round-trip, not N), then writes results
    back to Redis. Order of the input list is preserved in the output.

Failure mode:
    On any LLM/cache error: return the original English. The UI is supposed
    to degrade gracefully, not 500 the page.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import TYPE_CHECKING

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.llm_factory import get_llm

if TYPE_CHECKING:
    from src.database.redis import RedisCache

logger = structlog.get_logger()

CACHE_TTL_SECONDS = 86_400  # 1 day
CACHE_KEY_PREFIX = "llm_translation"
TRANSLATION_ROLE = "verdict"  # routes to claude-opus-4.7-xhigh via llm_factory

_SYSTEM_PROMPT = """You are a professional financial-translation engine.

Translate each numbered English passage into Simplified Chinese (zh-CN). Rules:
1. Preserve ticker symbols, numbers, currency amounts, percentages, and dates verbatim.
2. Use standard mainland-Chinese financial terminology (e.g. 估值 / 财报 / 看涨 / 仓位).
3. Keep the meaning faithful; do NOT add commentary, caveats, or footnotes.
4. Preserve any markdown formatting (** bold **, lists, line breaks).
5. Output ONLY a JSON array of strings, in the same order as the input.
   No prose before or after, no markdown fence, no keys — just a raw JSON array.

Example input:
1. NVDA hit 52-week high on AI demand.
2. Maintain 5% portfolio weight.

Example output:
["NVDA 因 AI 需求创 52 周新高。", "维持 5% 的组合权重。"]
"""


def _cache_key(text: str, target_lang: str) -> str:
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return f"{CACHE_KEY_PREFIX}:{target_lang}:{h}"


def _build_user_prompt(texts: list[str]) -> str:
    lines = [f"{i + 1}. {t}" for i, t in enumerate(texts)]
    return "\n".join(lines)


def _parse_llm_output(raw: str, expected_count: int) -> list[str] | None:
    """Pull the JSON array out of the model's response. Returns None on shape mismatch."""
    s = raw.strip()
    # Strip markdown fence if the model added one despite instructions
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        arr = json.loads(s)
    except json.JSONDecodeError:
        # Fallback: grab the first top-level [...] in case extra prose snuck in
        m = re.search(r"\[[\s\S]*\]", s)
        if not m:
            return None
        try:
            arr = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(arr, list) or len(arr) != expected_count:
        return None
    if not all(isinstance(x, str) for x in arr):
        return None
    return arr


async def _llm_translate(texts: list[str]) -> list[str] | None:
    """Single Anthropic round-trip translating every text. None on failure."""
    if not texts:
        return []
    try:
        llm = get_llm(TRANSLATION_ROLE, temperature=0.0, max_tokens=4096)
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=_build_user_prompt(texts)),
        ]
        # ChatAnthropic.ainvoke returns AIMessage; .content is the str body.
        resp = await llm.ainvoke(messages)
        raw = resp.content if isinstance(resp.content, str) else str(resp.content)
        out = _parse_llm_output(raw, expected_count=len(texts))
        if out is None:
            logger.warning(
                "translation_parse_failed",
                expected=len(texts),
                raw_preview=raw[:200],
            )
        return out
    except Exception as e:
        logger.warning("translation_llm_call_failed", error=str(e), count=len(texts))
        return None


async def translate_batch(
    texts: list[str],
    target_lang: str,
    redis_cache: "RedisCache",
) -> list[str]:
    """Translate `texts` to `target_lang`. Returns same length, same order.

    On cache miss, batches all misses into one LLM call.
    On any error, the failed entries fall back to their English original."""
    if not texts:
        return []
    if target_lang == "en" or target_lang.startswith("en-"):
        # No-op for English — the caller should normally short-circuit before
        # us, but defend anyway.
        return list(texts)

    # Pull all cache hits in parallel
    keys = [_cache_key(t, target_lang) for t in texts]
    cached_results: list[str | None] = await asyncio.gather(
        *(redis_cache.get(k) for k in keys), return_exceptions=False
    )

    miss_indices: list[int] = []
    miss_texts: list[str] = []
    out: list[str] = [""] * len(texts)
    for i, (orig, cached) in enumerate(zip(texts, cached_results)):
        if isinstance(cached, str):
            out[i] = cached
        else:
            miss_indices.append(i)
            miss_texts.append(orig)

    if not miss_texts:
        return out

    translated = await _llm_translate(miss_texts)
    if translated is None:
        # LLM failed — fall back to originals for the misses, no caching.
        for idx, orig in zip(miss_indices, miss_texts):
            out[idx] = orig
        return out

    # Stash misses in cache and place into the output slots
    set_tasks = []
    for idx, orig, zh in zip(miss_indices, miss_texts, translated):
        out[idx] = zh
        set_tasks.append(
            redis_cache.set(_cache_key(orig, target_lang), zh, ttl_seconds=CACHE_TTL_SECONDS)
        )
    # Don't fail the request if a cache write fails
    await asyncio.gather(*set_tasks, return_exceptions=True)

    logger.info(
        "translation_batch",
        total=len(texts),
        cache_hits=len(texts) - len(miss_texts),
        cache_misses=len(miss_texts),
        target_lang=target_lang,
    )
    return out
