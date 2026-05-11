"""Persistence-translator boundary.

Wraps `translation_service.translate_batch()` for write-path callers.
Repositories call this just before `insert_one` / `update_one` to populate
`<field>_zh` sibling fields on the document being written.

Failure mode: never raises. On LLM/Redis error every `_zh` value is None
and the caller writes English-only — the frontend then falls back to the
existing on-demand `/api/translate` lazy path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from src.services.translation_service import translate_batch

if TYPE_CHECKING:
    from src.database.redis import RedisCache

logger = structlog.get_logger()

DEFAULT_TARGET_LANG = "zh-CN"

# Minimum number of CJK Unified Ideographs to consider a string "already CJK".
# Tuned to fire on short titles like "# AAPL 苹果公司研究报告" while not
# triggering on incidental Chinese punctuation in an otherwise English string.
_CJK_MIN_CHARS = 3
_CJK_MIN_RATIO = 0.01  # 1% of non-space characters


def _is_already_cjk(text: str) -> bool:
    """Return True if `text` is already Chinese/CJK and must not be re-translated.

    Defense-in-depth guard against the DashScope reverse-translation bug
    that emits English when handed already-Chinese text labelled as
    `source_lang=auto, target_lang=zh-CN`. Counts code points in CJK
    Unified Ideographs (U+4E00..U+9FFF) and Extension A (U+3400..U+4DBF).
    """
    if not text:
        return False
    cjk_count = 0
    non_space_count = 0
    for ch in text:
        if not ch.isspace():
            non_space_count += 1
        codepoint = ord(ch)
        if 0x4E00 <= codepoint <= 0x9FFF or 0x3400 <= codepoint <= 0x4DBF:
            cjk_count += 1
    if cjk_count >= _CJK_MIN_CHARS:
        return True
    if non_space_count > 0 and (cjk_count / non_space_count) >= _CJK_MIN_RATIO:
        return True
    return False


def _is_empty(value: str | None) -> bool:
    return value is None or not value.strip()


async def translate_for_persistence(
    fields: dict[str, str],
    *,
    redis_cache: RedisCache,
    target_lang: str = DEFAULT_TARGET_LANG,
) -> dict[str, str | None]:
    """Translate a dict of field → English text into {field}_zh → translation.

    Empty / whitespace-only fields short-circuit to None without an LLM call.
    Fields already containing CJK text are skipped (no `_zh` sibling is
    written) so DashScope cannot reverse-translate them back to English.
    On any exception during translation, every {field}_zh value is None.
    The caller is expected to merge the result into its document dict.
    """
    if not fields:
        return {}

    keys = list(fields.keys())
    payload_indices: list[int] = []
    payload_texts: list[str] = []
    for i, key in enumerate(keys):
        text = fields[key]
        if _is_empty(text):
            continue
        if _is_already_cjk(text):
            non_space = sum(1 for ch in text if not ch.isspace())
            cjk_count = sum(
                1
                for ch in text
                if 0x4E00 <= ord(ch) <= 0x9FFF or 0x3400 <= ord(ch) <= 0x4DBF
            )
            ratio = (cjk_count / non_space) if non_space else 0.0
            logger.info(
                "translation_persistence_cjk_skip",
                field=key,
                text_len=len(text),
                cjk_ratio=round(ratio, 4),
            )
            continue
        payload_indices.append(i)
        payload_texts.append(text)

    if not payload_texts:
        return {f"{k}_zh": None for k in keys}

    try:
        translations = await translate_batch(payload_texts, target_lang, redis_cache)
    except Exception as exc:
        logger.warning(
            "translation_persistence_failed",
            error=str(exc),
            field_count=len(payload_texts),
        )
        return {f"{k}_zh": None for k in keys}

    out: dict[str, str | None] = {f"{k}_zh": None for k in keys}
    for idx, zh in zip(payload_indices, translations, strict=True):
        out[f"{keys[idx]}_zh"] = zh
    return out
