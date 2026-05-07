"""
POST /api/translate — translate LLM-generated English text to a target locale.

The frontend calls this on demand whenever the active i18n language is not
English. Translations are cached per text+lang in Redis for 1 day, so
re-rendering the same Decision Tracker page over a day is free.
"""

from __future__ import annotations

from typing import Literal

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.dependencies.chat_deps import get_redis
from src.database.redis import RedisCache
from src.services.translation_service import translate_batch

logger = structlog.get_logger()

router = APIRouter(prefix="/api/translate", tags=["translate"])


# zh-CN is all we ship a localized UI for today; widen the literal when more
# locales arrive so unsupported codes get rejected at the boundary.
TargetLang = Literal["zh-CN"]


class TranslateRequest(BaseModel):
    texts: list[str] = Field(..., max_length=64, description="English source strings")
    target_lang: TargetLang = Field(..., description="Target locale, e.g. 'zh-CN'")


class TranslateResponse(BaseModel):
    translations: list[str] = Field(..., description="Same length & order as `texts`")


@router.post("", response_model=TranslateResponse)
async def translate(
    payload: TranslateRequest,
    redis_cache: RedisCache = Depends(get_redis),
) -> TranslateResponse:
    """Returns translations for each input text. Cached results served instantly,
    misses batched into one LLM round-trip. On any backend error the original
    English string is returned for that slot — never raises 5xx.

    `translate_batch` may emit None for slots where the LLM failed (write-path
    callers persist None to mark the field as un-translated). For the on-demand
    HTTP path the frontend wants a string to render right now, so we echo the
    English original for any None slot.
    """
    raw = await translate_batch(payload.texts, payload.target_lang, redis_cache)
    out = [
        zh if zh is not None else orig
        for orig, zh in zip(payload.texts, raw, strict=True)
    ]
    return TranslateResponse(translations=out)
