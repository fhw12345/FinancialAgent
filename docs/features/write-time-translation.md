---
title: Write-Time Translation
status: shipped
version: backend@0.20.0, frontend@0.14.0
last_updated: 2026-05-16
owner: maintainer
related_paths:
  - backend/src/services/persistence_translator.py
  - backend/src/models/message.py
  - backend/src/database/repositories/message_repository.py
  - backend/src/database/repositories/chat_repository.py
  - backend/scripts/backfill_translations.py
  - frontend/src/hooks/useTranslated.ts
---

# Write-Time Translation

> Shipped in backend v0.20.0 / frontend v0.14.0 (commit 47ee922). This spec
> consolidates the original design document and implementation plan that were
> drafted under `docs/superpowers/` during the design phase. The
> `superpowers/` directory has been retired; this is the canonical reference.

## 1. Problem

LLM-generated user-visible text (chat content, trading reasoning, portfolio
assessment, chat title, …) used to be stored in MongoDB in English only. When
a user opened a document under the `zh-CN` locale, the frontend called
`POST /api/translate` lazily via the `useTranslated` hook, with results cached
in Redis for one day. This caused:

- ~3 s LLM round-trip on first read; ~87 ms network round-trip thereafter
- Redis TTL expiry → re-translation of identical text
- No Chinese version in the database — cannot be queried / exported / backed up
- Multiple `useTranslated` calls in different components → multiple loading
  flickers per page render
- System-prompt changes required manual Redis cache invalidation

## 2. Goals

- Translate every user-visible LLM-generated field to `zh-CN` **before** it is
  written to MongoDB, and store the translation in a sibling `<field>_zh`
  column on the same document.
- Frontend reads `_zh` directly and skips `/api/translate` on the happy path.
- Backfill historical documents.
- Translation failure must not block the English write (graceful degradation).
- Reuse the existing `translation_service.translate_batch()` + Redis cache —
  no changes to the translation core.

## 3. Non-Goals

- No worker / message queue (synchronous inline call is fine).
- No schema-level multi-language map (`<field>_zh` suffix is lighter and
  forward-compatible).
- The existing `/api/translate` endpoint and `useTranslated` lazy path stay as
  a safety net for documents where `_zh` is `null` (translation failure or
  not-yet-backfilled).
- Only `zh-CN`. The schema generalizes to other languages by adding more
  suffixes; that is a future change.

## 4. Acceptance Criteria

- A newly-created chat message has a non-empty, sensible `content_zh` in
  MongoDB.
- Same holds for `chats.title_zh` and `chats.last_message_preview_zh`.
- Frontend in `zh-CN` mode opens both historical (backfilled) and new chats
  without triggering `/api/translate` (verified in browser DevTools).
- LLM failure unit test: when the translation provider raises, the English
  field is still written; `_zh` is `null`; frontend falls back to lazy path.
- `make backfill-translations` brings the count of documents with missing
  `_zh` to zero.
- `make test` is green; ≥ 5 new backend tests + ≥ 1 new frontend test.

## 5. Architecture

```
LLM / Agent flow
      │
      ▼ (generates English)
Repository.create / save
      │
      ├─► persistence_translator.translate_for_persistence({fields})
      │           │
      │           ├─► translation_service.translate_batch([texts], "zh-CN")
      │           │           ├─► Redis cache lookup
      │           │           ├─► Anthropic batch call (cache miss)
      │           │           └─► Redis cache write
      │           │
      │           └─► returns {<field>_zh: zh_text | None}
      │
      ▼ (English + Chinese)
MongoDB insert_one / update_one
```

### 5.1 Translation boundary — `persistence_translator.py`

`backend/src/services/persistence_translator.py` exposes:

```python
async def translate_for_persistence(
    fields: dict[str, str],
    target_lang: str = "zh-CN",
) -> dict[str, str | None]:
    """
    Input:  {"content": "...", "title": "..."}
    Output: {"content_zh": "...", "title_zh": "..."}  (or None on failure)

    - Empty / whitespace-only fields short-circuit to None (no LLM call).
    - All non-empty fields are batched in a single translation_service call.
    - LLM failure / timeout -> all _zh values are None, logged as WARN,
      no exception is raised.
    """
```

Each repository write path calls it **once** (not per field), so each
persistence boundary performs exactly one LLM round-trip.

### 5.2 Data model

Two collections were touched, three new fields total:

| Collection | New field | Type | Notes |
|---|---|---|---|
| `messages` | `content_zh` | `Optional[str]` | Translation of `Message.content`. Covers chat, Phase 1 research output, Phase 2 portfolio reports, disclaimers. |
| `chats` | `title_zh` | `Optional[str]` | Sidebar conversation title. |
| `chats` | `last_message_preview_zh` | `Optional[str]` | Sidebar preview snippet. |

Pydantic models add `Optional[str] = None` fields for forward compatibility.
`None` / missing / empty string are all treated by the frontend as "translation
not ready → fall back to lazy".

> The original design also considered `trading_decisions.reasoning_summary_zh`
> and `portfolio_decisions.portfolio_assessment_zh`, but those payloads are not
> persisted independently — `phase2_decisions.py` composes them into a single
> markdown blob that ends up as a `messages` document, so `content_zh`
> already covers them.

### 5.3 Write-path call sites

| File | Behavior change |
|---|---|
| `backend/src/database/repositories/message_repository.py` (line ~74 in `create()`) | Call `translate_for_persistence({"content": ...})`, merge `content_zh` into the doc dict, then `insert_one`. |
| `backend/src/database/repositories/chat_repository.py` (`create()` line ~12, `update()` line ~74) | Same pattern for `title` and `last_message_preview` (the `update()` branch only translates the keys present in the update dict). |

Each call site adds ~3 lines: translate → merge → insert.

### 5.4 Frontend changes

`frontend/src/hooks/useTranslated.ts` was extended:

```typescript
useTranslated(text: string, opts?: { precomputed?: string | null })
```

- `precomputed` non-empty → return `{ text: precomputed, isLoading: false,
  isTranslated: true }` immediately (no API call).
- `precomputed` null/empty → existing lazy path unchanged.

The `<Translated>` component forwards a `precomputed` prop to the hook. Call
sites under `zh-CN` pass the `_zh` field; under `en` they pass nothing and
render the original text.

### 5.5 Failure handling

- LLM error / timeout: `translate_for_persistence` catches internally, all
  `_zh` values are returned as `None`, a `WARN` is logged.
- The English write is **never** blocked by translation failure.
- Frontend reads `_zh = null` → `useTranslated` runs its existing lazy path,
  hitting Redis or `/api/translate`.
- The lazy path is therefore demoted from "default" to "fallback", but it is
  not removed.

## 6. Backfill

`backend/scripts/backfill_translations.py` walks `messages` / `chats`,
selecting documents where the `_zh` field is missing or null. It batches
N documents per LLM call and writes back via `update_one`. The job is
idempotent (already-translated documents are skipped) and tolerant of partial
failures (failed documents are retried on the next run).

`Makefile` exposes the target `backfill-translations`.

## 7. References

- Original design draft: archived; this document supersedes it.
- Production code paths: see `related_paths` frontmatter.