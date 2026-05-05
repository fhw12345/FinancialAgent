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
