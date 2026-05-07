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

# Sentinel separating translated passages in the model's raw response.
# Replaces the previous JSON-array protocol — JSON parsing was choking on
# bare newlines inside translated markdown blocks (Invalid control character),
# silently dropping translations and persisting English originals.
_SEPARATOR = "<<<TRANSLATION_SEPARATOR>>>"

_SYSTEM_PROMPT = """You are a professional financial-translation engine.

Translate each numbered English passage into Simplified Chinese (zh-CN). Rules:
1. Translate EVERY sentence — including disclaimers, data-source notes, error
   messages, and meta-commentary like "Alpha Vantage rate-limited" or "based
   on available data". No English sentence should remain in the output.
2. Preserve ticker symbols (AAPL, NVDA, CRWV…), numbers, currency amounts,
   percentages, dates, and ISO timestamps verbatim.
3. Use standard mainland-Chinese financial terminology (e.g. 估值 / 财报 /
   看涨 / 仓位 / 持有 / 卖出 / 买入).
4. Keep the meaning faithful; do NOT add commentary, caveats, or footnotes
   beyond what the source contains.
5. Preserve all markdown formatting verbatim: headers (#, ##, ###), bold
   (**), italics, bullet points, numbered lists, tables (| col | col |),
   code fences, and line breaks. Do not collapse, reformat, or merge them.
6. Output ONLY the translated passages, separated by the literal token
   `<<<TRANSLATION_SEPARATOR>>>` on its own line, in the same order as the
   input. No JSON, no numbering, no markdown fence, no prose. Do NOT use the
   separator token anywhere inside a translation; it is reserved.

Example input:
1. NVDA hit 52-week high on AI demand. Source: company filings.
2. Maintain 5% portfolio weight.

Example output:
NVDA 因 AI 需求创 52 周新高。资料来源:公司文件。
<<<TRANSLATION_SEPARATOR>>>
维持 5% 的组合权重。
"""


def _cache_key(text: str, target_lang: str) -> str:
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return f"{CACHE_KEY_PREFIX}:{target_lang}:{h}"


def _build_user_prompt(texts: list[str]) -> str:
    lines = [f"{i + 1}. {t}" for i, t in enumerate(texts)]
    return "\n".join(lines)


def _parse_llm_output(raw: str, expected_count: int) -> list[str] | None:
    """Split the model's raw response on the separator sentinel.

    Returns None on any shape mismatch (empty input or wrong piece count).
    Length-mismatch is logged here so the caller doesn't double-log.
    """
    s = raw.strip()
    if not s:
        logger.warning(
            "translation_parse_failed", error_type="empty", expected=expected_count
        )
        return None
    # Strip markdown fence if the model added one despite instructions.
    if s.startswith("```"):
        s = re.sub(r"^```\w*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
        s = s.strip()
    parts = [p.strip() for p in s.split(_SEPARATOR)]
    if len(parts) != expected_count:
        logger.warning(
            "translation_parse_failed",
            error_type="length_mismatch",
            expected=expected_count,
            got=len(parts),
            raw_preview=raw[:2000],
        )
        return None
    return parts


async def _llm_translate(texts: list[str]) -> list[str] | None:
    """Single LLM round-trip translating every text. None on failure."""
    if not texts:
        return []
    try:
        # max_tokens=16384: full_research can be 5-10KB of markdown; Chinese
        # output is ~1.5x token-dense than English, so 4096 was being silently
        # truncated for long bodies. Reasoning translations cost a few hundred
        # tokens — the higher cap costs nothing for the small case.
        llm = get_llm(TRANSLATION_ROLE, temperature=0.0, max_tokens=16384)
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=_build_user_prompt(texts)),
        ]
        # ChatAnthropic.ainvoke returns AIMessage; .content is the str body.
        resp = await llm.ainvoke(messages)
        raw = resp.content if isinstance(resp.content, str) else str(resp.content)
        # _parse_llm_output logs its own failure cause; no double-log here.
        return _parse_llm_output(raw, expected_count=len(texts))
    except Exception as e:
        logger.warning(
            "translation_llm_call_failed",
            error=repr(e),
            error_type=type(e).__name__,
            count=len(texts),
        )
        return None


async def translate_batch(
    texts: list[str],
    target_lang: str,
    redis_cache: RedisCache,
) -> list[str | None]:
    """Translate `texts` to `target_lang`. Returns same length, same order.

    On cache miss, batches all misses into one LLM call.
    On any LLM/parse failure, the failed slots are None — callers decide how
    to surface that (write None to mongo, echo English to the HTTP client,
    etc.). Previously we silently echoed the English original, which let the
    persistence layer write English into `<field>_zh` and fooled the frontend
    into thinking a translation existed.
    """
    if not texts:
        return []
    if target_lang == "en" or target_lang.startswith("en-"):
        # No-op for English — the caller should normally short-circuit before
        # us, but defend anyway. list[str] is a subtype of list[str | None].
        return list(texts)

    # Pull all cache hits in parallel
    keys = [_cache_key(t, target_lang) for t in texts]
    cached_results: list[str | None] = await asyncio.gather(
        *(redis_cache.get(k) for k in keys), return_exceptions=False
    )

    miss_indices: list[int] = []
    miss_texts: list[str] = []
    out: list[str | None] = [None] * len(texts)
    for i, (orig, cached) in enumerate(zip(texts, cached_results, strict=True)):
        if isinstance(cached, str):
            out[i] = cached
        else:
            miss_indices.append(i)
            miss_texts.append(orig)

    if not miss_texts:
        return out

    translated = await _llm_translate(miss_texts)
    if translated is None:
        # LLM/parse failed — leave miss slots as None. Don't cache.
        return out

    # Stash misses in cache and place into the output slots
    set_tasks = []
    for idx, orig, zh in zip(miss_indices, miss_texts, translated, strict=True):
        out[idx] = zh
        set_tasks.append(
            redis_cache.set(
                _cache_key(orig, target_lang), zh, ttl_seconds=CACHE_TTL_SECONDS
            )
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
