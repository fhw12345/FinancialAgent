# Write-Time Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move zh-CN translation from lazy frontend render to inline write-time persistence. Translations live in `<field>_zh` sibling fields on existing collections; lazy `/api/translate` retained as fallback.

**Architecture:** New `persistence_translator.py` boundary wraps existing `translation_service.translate_batch()`. Two repositories (`MessageRepository`, `ChatRepository`) call it before `insert_one`/`update_one`. Pydantic models gain `Optional[str]` `_zh` fields. Frontend `useTranslated` hook accepts `precomputed` arg that short-circuits the API call. A backfill script populates legacy docs.

**Tech Stack:** Python 3.12 / FastAPI / motor (async MongoDB) / Pydantic v2 / pytest / structlog · React 18 / TypeScript / TanStack Query / Vitest

**Spec:** [`docs/superpowers/specs/2026-05-05-write-time-translation-design.md`](../specs/2026-05-05-write-time-translation-design.md)

---

## File Structure

**New files (3):**
- `backend/src/services/persistence_translator.py` — translation boundary, ~60 lines
- `backend/scripts/backfill_translations.py` — historical data backfill, ~150 lines
- `backend/tests/test_persistence_translator.py` — unit tests
- `backend/tests/test_backfill_translations.py` — backfill tests
- `frontend/src/hooks/__tests__/useTranslated.test.ts` — adds `precomputed` cases (file already exists per explore — extend it; if missing, create)

**Modified files (6):**
- `backend/src/models/message.py` — add `Message.content_zh: Optional[str]`
- `backend/src/models/chat.py` — add `Chat.title_zh` and `Chat.last_message_preview_zh: Optional[str]`
- `backend/src/database/repositories/message_repository.py:45` — add translation call to `create()`
- `backend/src/database/repositories/chat_repository.py:40,89` — add translation call to `create()` and `update()`
- `frontend/src/hooks/useTranslated.ts` — accept `precomputed` opt
- `frontend/src/components/Translated.tsx` — pass `precomputed` prop through
- `frontend/src/components/ChatMessages.tsx` (and DecisionTracker, sidebar chat list) — pass `message.content_zh` / `chat.title_zh` / `chat.last_message_preview_zh`
- `Makefile` — `backfill-translations` target

**No-touch (existing core stays):**
- `backend/src/services/translation_service.py` — reused as-is
- `backend/src/api/translate.py` — fallback endpoint, unchanged

---

## Task 1: Add `_zh` fields to Pydantic models

**Files:**
- Modify: `backend/src/models/message.py:138-186` (Message class)
- Modify: `backend/src/models/chat.py:64-104` (Chat class)
- Test: (no new test — covered by repository tests in later tasks)

- [ ] **Step 1: Add `content_zh` to `Message`**

In `backend/src/models/message.py`, after the `content: str = ...` field (line 150), add:

```python
    content_zh: str | None = Field(
        default=None,
        description="Simplified Chinese translation of content; None when translation failed or not yet computed",
    )
```

- [ ] **Step 2: Add `title_zh` and `last_message_preview_zh` to `Chat`**

In `backend/src/models/chat.py`, inside the `Chat` class (after line 80, near `last_message_preview`), add:

```python
    title_zh: str | None = Field(
        default=None,
        description="Simplified Chinese translation of title",
    )
    last_message_preview_zh: str | None = Field(
        default=None,
        description="Simplified Chinese translation of last_message_preview",
    )
```

- [ ] **Step 3: Verify import works**

Run: `docker compose exec backend python -c "from src.models.message import Message; from src.models.chat import Chat; print(Message.model_fields['content_zh']); print(Chat.model_fields['title_zh'])"`

Expected: prints two `FieldInfo` objects without error.

- [ ] **Step 4: Commit**

```bash
git add backend/src/models/message.py backend/src/models/chat.py
git commit -m "feat(i18n): add _zh sibling fields to Message and Chat models"
```

---

## Task 2: Write `persistence_translator` failing tests

**Files:**
- Create: `backend/tests/test_persistence_translator.py`
- (Implementation file does not yet exist — tests will fail with ImportError, that's the point)

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/test_persistence_translator.py`:

```python
"""Tests for persistence_translator boundary."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.services.persistence_translator import translate_for_persistence


class FakeRedis:
    """Minimal stand-in for RedisCache used by translation_service."""
    async def get(self, key):  # noqa: ARG002
        return None

    async def set(self, key, value, ttl_seconds=None):  # noqa: ARG002
        return None


@pytest.mark.asyncio
async def test_success_path_translates_all_fields():
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
async def test_llm_failure_returns_none_for_all_fields():
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
async def test_empty_string_field_short_circuits():
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
    # Only "Hello" was passed to translate_batch
    args, _ = mock_translate.call_args
    assert args[0] == ["Hello"]


@pytest.mark.asyncio
async def test_empty_input_dict_returns_empty():
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
async def test_dict_iteration_order_preserved():
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
```

- [ ] **Step 2: Run tests to verify they fail with ImportError**

Run: `docker compose exec backend pytest tests/test_persistence_translator.py -v`

Expected: `ModuleNotFoundError: No module named 'src.services.persistence_translator'` (5 errors, 0 passed).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_persistence_translator.py
git commit -m "test(i18n): failing tests for persistence_translator boundary"
```

---

## Task 3: Implement `persistence_translator` to make tests pass

**Files:**
- Create: `backend/src/services/persistence_translator.py`

- [ ] **Step 1: Write minimal implementation**

Create `backend/src/services/persistence_translator.py`:

```python
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
    redis_cache: "RedisCache",
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
            "persistence_translation_failed",
            error=str(exc),
            field_count=len(payload_texts),
        )
        return {f"{k}_zh": None for k in keys}

    out: dict[str, str | None] = {f"{k}_zh": None for k in keys}
    for idx, zh in zip(payload_indices, translations):
        out[f"{keys[idx]}_zh"] = zh
    return out
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_persistence_translator.py -v`

Expected: `5 passed`.

- [ ] **Step 3: Run lint + format**

Run: `docker compose exec backend ruff check src/services/persistence_translator.py tests/test_persistence_translator.py && docker compose exec backend black --check src/services/persistence_translator.py tests/test_persistence_translator.py`

Expected: no errors. If `black` reports changes, run `docker compose exec backend black src/services/persistence_translator.py tests/test_persistence_translator.py` and re-stage.

- [ ] **Step 4: Commit**

```bash
git add backend/src/services/persistence_translator.py
git commit -m "feat(i18n): persistence_translator boundary for write-time translation"
```

---

## Task 4: Wire `MessageRepository.create()` to the translator

**Files:**
- Modify: `backend/src/database/repositories/message_repository.py:45-84` (`create` method)
- Test: `backend/tests/test_message_repository.py` (existing — extend)

- [ ] **Step 1: Write failing repository test**

Find existing `backend/tests/test_message_repository.py`. Append:

```python
@pytest.mark.asyncio
async def test_create_persists_content_zh_on_translation_success(
    message_repository, fake_redis
):
    """When translation succeeds, the inserted document has content_zh populated."""
    from unittest.mock import AsyncMock, patch

    create_payload = MessageCreate(
        chat_id="chat_test_zh",
        role="assistant",
        content="Hello world",
        source="llm",
    )
    with patch(
        "src.database.repositories.message_repository.translate_for_persistence",
        new=AsyncMock(return_value={"content_zh": "你好世界"}),
    ):
        msg = await message_repository.create(create_payload)

    assert msg.content_zh == "你好世界"
    raw = await message_repository.collection.find_one({"message_id": msg.message_id})
    assert raw["content_zh"] == "你好世界"


@pytest.mark.asyncio
async def test_create_stores_english_when_translation_fails(
    message_repository, fake_redis
):
    """Translation failure does NOT block English persistence; content_zh is None."""
    from unittest.mock import AsyncMock, patch

    create_payload = MessageCreate(
        chat_id="chat_test_zh_fail",
        role="assistant",
        content="Hello world",
        source="llm",
    )
    with patch(
        "src.database.repositories.message_repository.translate_for_persistence",
        new=AsyncMock(return_value={"content_zh": None}),
    ):
        msg = await message_repository.create(create_payload)

    assert msg.content == "Hello world"
    assert msg.content_zh is None
```

If `message_repository` and `fake_redis` fixtures don't already exist in this file, add them at the top:

```python
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from src.database.repositories.message_repository import MessageRepository
from src.models.message import MessageCreate


@pytest.fixture
async def message_repository():
    client = AsyncIOMotorClient("mongodb://mongo:27017")
    db = client["financial_agent_test"]
    coll = db["messages"]
    await coll.delete_many({})
    yield MessageRepository(coll)
    await coll.delete_many({})
    client.close()


@pytest.fixture
def fake_redis():
    class _Fake:
        async def get(self, k):  # noqa: ARG002
            return None
        async def set(self, k, v, ttl_seconds=None):  # noqa: ARG002
            return None
    return _Fake()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_message_repository.py -v -k "content_zh or translation"`

Expected: 2 failures referencing missing `translate_for_persistence` import in the repository module.

- [ ] **Step 3: Wire repository to translator**

In `backend/src/database/repositories/message_repository.py`, near the existing imports (after line 11), add:

```python
from src.services.persistence_translator import translate_for_persistence
```

Modify the `create()` method (lines 45-84) — replace the body's persistence section so it reads:

```python
    async def create(self, message_create: MessageCreate) -> Message:
        """Create a new message with zh-CN translation persisted alongside."""
        import uuid

        message_id = f"msg_{uuid.uuid4().hex[:12]}"

        # Translate user-visible English to zh-CN before insert.
        # Failure path: returns {"content_zh": None}; English still persists.
        translations = await translate_for_persistence(
            {"content": message_create.content},
            redis_cache=self._redis,
        )

        message = Message(
            message_id=message_id,
            chat_id=message_create.chat_id,
            role=message_create.role,
            content=message_create.content,
            content_zh=translations.get("content_zh"),
            source=message_create.source,
            timestamp=utcnow(),
            metadata=message_create.metadata,
            tool_call=message_create.tool_call,
        )

        message_dict = message.model_dump()
        await self.collection.insert_one(message_dict)

        logger.info(
            "Message created",
            message_id=message_id,
            chat_id=message_create.chat_id,
            source=message_create.source,
            translated=translations.get("content_zh") is not None,
        )

        return message
```

- [ ] **Step 4: Inject Redis into the repository constructor**

Update the constructor (lines 19-26):

```python
    def __init__(
        self,
        collection: AsyncIOMotorCollection,
        redis_cache: "RedisCache",
    ):
        self.collection = collection
        self._redis = redis_cache
```

Add the import (top of file):

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.database.redis import RedisCache
```

- [ ] **Step 5: Update every call site that constructs `MessageRepository`**

Run: `docker compose exec backend grep -rn "MessageRepository(" src/ tests/ scripts/ --include="*.py"`

For each match where `MessageRepository(...)` is built with a single positional arg, add the redis cache. The DI container is in `backend/src/database/__init__.py` or `backend/src/dependencies.py` — find the existing `redis_cache` instance and pass it:

```python
MessageRepository(messages_coll, redis_cache)
```

Update the test fixture written in Step 1 the same way:

```python
return MessageRepository(coll, fake_redis_instance)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker compose exec backend pytest tests/test_message_repository.py -v`

Expected: all message_repository tests pass (existing + the two new translation tests).

- [ ] **Step 7: Run full backend test suite to catch regressions from constructor change**

Run: `docker compose exec backend pytest -x`

Expected: pass. If failures appear in unrelated files, they are almost certainly call sites of `MessageRepository(...)` missed in Step 5 — fix and re-run.

- [ ] **Step 8: Commit**

```bash
git add backend/src/database/repositories/message_repository.py backend/tests/test_message_repository.py backend/src/dependencies.py
git commit -m "feat(i18n): translate Message.content to zh-CN at write time"
```

(Add any other files Step 5 touched to the `git add`.)

---

## Task 5: Wire `ChatRepository.create()` and `update()` to the translator

**Files:**
- Modify: `backend/src/database/repositories/chat_repository.py:22-58` (constructor + `create`), `:89-111` (`update`)
- Test: `backend/tests/test_chat_repository.py` (existing — extend)

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_chat_repository.py`:

```python
@pytest.mark.asyncio
async def test_create_persists_title_zh(chat_repository):
    from unittest.mock import AsyncMock, patch
    from src.models.chat import ChatCreate

    with patch(
        "src.database.repositories.chat_repository.translate_for_persistence",
        new=AsyncMock(return_value={"title_zh": "新会话"}),
    ):
        chat = await chat_repository.create(ChatCreate(title="New Chat"))

    assert chat.title == "New Chat"
    assert chat.title_zh == "新会话"


@pytest.mark.asyncio
async def test_update_translates_title_and_preview_when_provided(chat_repository):
    from unittest.mock import AsyncMock, patch
    from src.models.chat import ChatCreate, ChatUpdate

    with patch(
        "src.database.repositories.chat_repository.translate_for_persistence",
        new=AsyncMock(return_value={"title_zh": None}),
    ):
        chat = await chat_repository.create(ChatCreate(title="x"))

    with patch(
        "src.database.repositories.chat_repository.translate_for_persistence",
        new=AsyncMock(
            return_value={"title_zh": "苹果分析", "last_message_preview_zh": "基于斐波那契…"}
        ),
    ) as mock_t:
        updated = await chat_repository.update(
            chat.chat_id,
            ChatUpdate(title="AAPL Analysis", last_message_preview="Based on Fibonacci..."),
        )

    assert updated.title_zh == "苹果分析"
    assert updated.last_message_preview_zh == "基于斐波那契…"
    args, _ = mock_t.call_args
    assert args[0] == {
        "title": "AAPL Analysis",
        "last_message_preview": "Based on Fibonacci...",
    }


@pytest.mark.asyncio
async def test_update_skips_translation_when_no_text_fields_change(chat_repository):
    from unittest.mock import AsyncMock, patch
    from src.models.chat import ChatCreate, ChatUpdate

    with patch(
        "src.database.repositories.chat_repository.translate_for_persistence",
        new=AsyncMock(return_value={}),
    ):
        chat = await chat_repository.create(ChatCreate(title="x"))

    mock_t = AsyncMock()
    with patch(
        "src.database.repositories.chat_repository.translate_for_persistence",
        new=mock_t,
    ):
        await chat_repository.update(chat.chat_id, ChatUpdate(is_archived=True))

    mock_t.assert_not_called()
```

Add fixture if missing (similar to Task 4):

```python
@pytest.fixture
async def chat_repository(fake_redis):
    from motor.motor_asyncio import AsyncIOMotorClient
    from src.database.repositories.chat_repository import ChatRepository
    client = AsyncIOMotorClient("mongodb://mongo:27017")
    db = client["financial_agent_test"]
    coll = db["chats"]
    await coll.delete_many({})
    yield ChatRepository(coll, fake_redis)
    await coll.delete_many({})
    client.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec backend pytest tests/test_chat_repository.py -v -k "title_zh or preview"`

Expected: failures (translator not wired yet, constructor signature wrong).

- [ ] **Step 3: Wire ChatRepository**

Edit `backend/src/database/repositories/chat_repository.py`:

Imports (after line 14):

```python
from typing import TYPE_CHECKING

from src.services.persistence_translator import translate_for_persistence

if TYPE_CHECKING:
    from src.database.redis import RedisCache
```

Constructor:

```python
    def __init__(
        self,
        collection: AsyncIOMotorCollection,
        redis_cache: "RedisCache",
    ):
        self.collection = collection
        self._redis = redis_cache
```

Replace `create()` (lines 40-58):

```python
    async def create(self, chat_create: ChatCreate) -> Chat:
        import uuid

        chat_id = f"chat_{uuid.uuid4().hex[:12]}"

        translations = await translate_for_persistence(
            {"title": chat_create.title},
            redis_cache=self._redis,
        )

        chat = Chat(
            chat_id=chat_id,
            title=chat_create.title,
            title_zh=translations.get("title_zh"),
            is_archived=False,
            ui_state=UIState(),
            last_message_preview=None,
            last_message_preview_zh=None,
            created_at=utcnow(),
            updated_at=utcnow(),
            last_message_at=None,
        )

        await self.collection.insert_one(chat.model_dump())
        logger.info("Chat created", chat_id=chat_id)
        return chat
```

Replace `update()` (lines 89-111):

```python
    async def update(self, chat_id: str, chat_update: ChatUpdate) -> Chat | None:
        update_dict: dict[str, Any] = {"updated_at": utcnow()}

        translatable: dict[str, str] = {}
        if chat_update.title is not None:
            update_dict["title"] = chat_update.title
            translatable["title"] = chat_update.title
        if chat_update.last_message_preview is not None:
            update_dict["last_message_preview"] = chat_update.last_message_preview
            translatable["last_message_preview"] = chat_update.last_message_preview
        if chat_update.is_archived is not None:
            update_dict["is_archived"] = chat_update.is_archived
        if chat_update.ui_state is not None:
            update_dict["ui_state"] = chat_update.ui_state.model_dump()

        if translatable:
            translations = await translate_for_persistence(
                translatable, redis_cache=self._redis
            )
            for tk, tv in translations.items():
                update_dict[tk] = tv

        result = await self.collection.find_one_and_update(
            {"chat_id": chat_id},
            {"$set": update_dict},
            return_document=True,
        )

        if not result:
            return None
        result.pop("_id", None)
        logger.info("Chat updated", chat_id=chat_id, fields=list(update_dict.keys()))
        return Chat(**result)
```

- [ ] **Step 4: Update every call site that constructs `ChatRepository`**

Run: `docker compose exec backend grep -rn "ChatRepository(" src/ tests/ scripts/ --include="*.py"`

Add `redis_cache` to every constructor call.

- [ ] **Step 5: Run tests**

Run: `docker compose exec backend pytest tests/test_chat_repository.py -v`

Expected: all pass.

- [ ] **Step 6: Run full backend suite**

Run: `docker compose exec backend pytest -x`

Expected: pass. Fix any constructor-call regressions.

- [ ] **Step 7: Commit**

```bash
git add backend/src/database/repositories/chat_repository.py backend/tests/test_chat_repository.py
# plus whatever DI files Step 4 touched
git commit -m "feat(i18n): translate Chat.title and last_message_preview at write time"
```

---

## Task 6: Backfill script — failing tests

**Files:**
- Create: `backend/tests/test_backfill_translations.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_backfill_translations.py`:

```python
"""Tests for backfill_translations script."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from scripts.backfill_translations import backfill_collection


@pytest.fixture
async def messages_collection():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient("mongodb://mongo:27017")
    coll = client["financial_agent_test"]["messages"]
    await coll.delete_many({})
    yield coll
    await coll.delete_many({})
    client.close()


@pytest.fixture
def fake_redis():
    class _Fake:
        async def get(self, k):  # noqa: ARG002
            return None
        async def set(self, k, v, ttl_seconds=None):  # noqa: ARG002
            return None
    return _Fake()


@pytest.mark.asyncio
async def test_dry_run_does_not_write(messages_collection, fake_redis):
    await messages_collection.insert_many([
        {"message_id": "m1", "content": "Hello", "content_zh": None},
        {"message_id": "m2", "content": "World", "content_zh": None},
    ])
    with patch(
        "scripts.backfill_translations.translate_for_persistence",
        new=AsyncMock(return_value={"content_zh": "TRANSLATED"}),
    ):
        stats = await backfill_collection(
            messages_collection,
            text_fields=["content"],
            redis_cache=fake_redis,
            batch_size=10,
            dry_run=True,
        )
    assert stats["would_update"] == 2
    assert stats["updated"] == 0
    raw = await messages_collection.find_one({"message_id": "m1"})
    assert raw["content_zh"] is None


@pytest.mark.asyncio
async def test_skips_documents_with_existing_translation(messages_collection, fake_redis):
    await messages_collection.insert_many([
        {"message_id": "m1", "content": "Hello", "content_zh": "你好"},
        {"message_id": "m2", "content": "World", "content_zh": None},
    ])
    mock_t = AsyncMock(return_value={"content_zh": "世界"})
    with patch(
        "scripts.backfill_translations.translate_for_persistence",
        new=mock_t,
    ):
        stats = await backfill_collection(
            messages_collection,
            text_fields=["content"],
            redis_cache=fake_redis,
            batch_size=10,
        )
    assert stats["updated"] == 1
    args, _ = mock_t.call_args_list[0]
    assert args[0] == {"content": "World"}


@pytest.mark.asyncio
async def test_partial_failure_does_not_stop_batch(messages_collection, fake_redis):
    await messages_collection.insert_many([
        {"message_id": f"m{i}", "content": f"text{i}", "content_zh": None}
        for i in range(3)
    ])
    call_count = {"n": 0}

    async def flaky(_fields, redis_cache, target_lang="zh-CN"):  # noqa: ARG001
        call_count["n"] += 1
        if call_count["n"] == 2:
            return {"content_zh": None}  # translation failure
        return {"content_zh": "ok"}

    with patch(
        "scripts.backfill_translations.translate_for_persistence",
        new=flaky,
    ):
        stats = await backfill_collection(
            messages_collection,
            text_fields=["content"],
            redis_cache=fake_redis,
            batch_size=10,
        )
    assert stats["updated"] == 2
    assert stats["failed"] == 1
```

- [ ] **Step 2: Run tests to verify ImportError**

Run: `docker compose exec backend pytest tests/test_backfill_translations.py -v`

Expected: `ModuleNotFoundError: No module named 'scripts.backfill_translations'`.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_backfill_translations.py
git commit -m "test(i18n): failing tests for backfill_translations script"
```

---

## Task 7: Implement backfill script

**Files:**
- Create: `backend/scripts/backfill_translations.py`
- Modify: `Makefile`

- [ ] **Step 1: Write the script**

Create `backend/scripts/backfill_translations.py`:

```python
"""Backfill historical MongoDB documents with zh-CN translations.

Scans collections for documents missing `<field>_zh` and populates them
in batches by calling persistence_translator. Idempotent: documents that
already have translations are skipped.

Usage:
    docker compose exec backend python -m scripts.backfill_translations \\
        [--collection messages|chats|all] \\
        [--batch-size 50] \\
        [--limit N] \\
        [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from typing import TYPE_CHECKING

from motor.motor_asyncio import AsyncIOMotorCollection

from src.services.persistence_translator import translate_for_persistence

if TYPE_CHECKING:
    from src.database.redis import RedisCache

logger = logging.getLogger("backfill_translations")


COLLECTION_FIELDS: dict[str, list[str]] = {
    "messages": ["content"],
    "chats": ["title", "last_message_preview"],
}


def _missing_query(text_fields: list[str]) -> dict:
    """Match documents where any text field is non-empty but its _zh sibling is missing."""
    return {
        "$or": [
            {
                "$and": [
                    {field: {"$exists": True, "$ne": None, "$ne": ""}},
                    {
                        "$or": [
                            {f"{field}_zh": {"$exists": False}},
                            {f"{field}_zh": None},
                        ]
                    },
                ]
            }
            for field in text_fields
        ]
    }


async def backfill_collection(
    collection: AsyncIOMotorCollection,
    text_fields: list[str],
    redis_cache: "RedisCache",
    batch_size: int = 50,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Backfill `_zh` fields on a single collection. Returns stats."""
    stats = {"scanned": 0, "updated": 0, "would_update": 0, "failed": 0}

    query = _missing_query(text_fields)
    cursor = collection.find(query)
    if limit:
        cursor = cursor.limit(limit)

    batch: list[dict] = []
    async for doc in cursor:
        stats["scanned"] += 1
        batch.append(doc)
        if len(batch) >= batch_size:
            await _process_batch(
                collection, batch, text_fields, redis_cache, dry_run, stats
            )
            batch = []
    if batch:
        await _process_batch(
            collection, batch, text_fields, redis_cache, dry_run, stats
        )

    logger.info("backfill complete: %s", stats)
    return stats


async def _process_batch(
    collection: AsyncIOMotorCollection,
    batch: list[dict],
    text_fields: list[str],
    redis_cache: "RedisCache",
    dry_run: bool,
    stats: dict[str, int],
) -> None:
    for doc in batch:
        to_translate = {
            f: doc[f] for f in text_fields if doc.get(f) and doc.get(f"{f}_zh") is None
        }
        if not to_translate:
            continue

        translations = await translate_for_persistence(
            to_translate, redis_cache=redis_cache
        )

        any_failed = any(v is None for v in translations.values())
        if any_failed:
            stats["failed"] += 1

        any_succeeded = any(v is not None for v in translations.values())
        if not any_succeeded:
            continue

        if dry_run:
            stats["would_update"] += 1
            continue

        update_doc = {k: v for k, v in translations.items() if v is not None}
        result = await collection.update_one(
            {"_id": doc["_id"]}, {"$set": update_doc}
        )
        if result.modified_count == 1:
            stats["updated"] += 1


async def _main(args: argparse.Namespace) -> None:
    from src.database import get_database
    from src.database.redis import get_redis_cache

    db = await get_database()
    redis_cache = await get_redis_cache()

    targets = (
        list(COLLECTION_FIELDS.keys())
        if args.collection == "all"
        else [args.collection]
    )

    for coll_name in targets:
        coll = db[coll_name]
        fields = COLLECTION_FIELDS[coll_name]
        logger.info(
            "backfilling collection=%s fields=%s batch_size=%d dry_run=%s",
            coll_name,
            fields,
            args.batch_size,
            args.dry_run,
        )
        await backfill_collection(
            coll,
            text_fields=fields,
            redis_cache=redis_cache,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collection",
        choices=["messages", "chats", "all"],
        default="all",
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
```

> **Note:** `from src.database import get_database` and `from src.database.redis import get_redis_cache` reflect this codebase's existing accessor pattern (per the explore report referencing `RedisCache`). If the actual module names differ, adjust to match — the test fixtures bypass `_main` and exercise `backfill_collection` directly.

- [ ] **Step 2: Run tests**

Run: `docker compose exec backend pytest tests/test_backfill_translations.py -v`

Expected: 3 passed.

- [ ] **Step 3: Add Makefile target**

Append to `Makefile`:

```makefile
backfill-translations:
	docker compose exec backend python -m scripts.backfill_translations --collection all
```

- [ ] **Step 4: Smoke-test the dry run on real data**

Run: `docker compose exec backend python -m scripts.backfill_translations --collection messages --limit 5 --dry-run`

Expected: prints `backfill complete: {'scanned': N, 'updated': 0, 'would_update': N, 'failed': 0}` for some N >= 0; no exceptions.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/backfill_translations.py Makefile
git commit -m "feat(i18n): backfill_translations script for legacy documents"
```

---

## Task 8: Frontend — extend `useTranslated` with `precomputed`

**Files:**
- Modify: `frontend/src/hooks/useTranslated.ts`
- Modify (or create): `frontend/src/hooks/__tests__/useTranslated.test.ts`

- [ ] **Step 1: Write failing tests**

Edit/create `frontend/src/hooks/__tests__/useTranslated.test.ts`. Add (or insert near existing tests):

```typescript
import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import i18n from "i18next";
import { useTranslated } from "../useTranslated";
import * as api from "../../services/translateApi";

i18n.init({ lng: "zh-CN", resources: {} });

function wrap({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
    </QueryClientProvider>
  );
}

describe("useTranslated precomputed", () => {
  it("returns precomputed value without calling translateBatch", () => {
    const spy = vi.spyOn(api, "translateBatch");
    const { result } = renderHook(
      () => useTranslated("Hello world", { precomputed: "你好世界" }),
      { wrapper: wrap }
    );
    expect(result.current.text).toBe("你好世界");
    expect(result.current.isTranslated).toBe(true);
    expect(result.current.isLoading).toBe(false);
    expect(spy).not.toHaveBeenCalled();
  });

  it("falls through to lazy path when precomputed is null", () => {
    const spy = vi
      .spyOn(api, "translateBatch")
      .mockResolvedValue(["你好"]);
    const { result } = renderHook(
      () => useTranslated("Hello", { precomputed: null }),
      { wrapper: wrap }
    );
    expect(result.current.isLoading).toBe(true);
    expect(spy).toHaveBeenCalled();
  });

  it("falls through to lazy path when precomputed is empty string", () => {
    const spy = vi
      .spyOn(api, "translateBatch")
      .mockResolvedValue(["你好"]);
    renderHook(() => useTranslated("Hello", { precomputed: "" }), {
      wrapper: wrap,
    });
    expect(spy).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run tests to verify failure**

Run: `docker compose exec frontend npm test -- useTranslated`

Expected: 3 failures (current hook signature doesn't accept `opts`).

- [ ] **Step 3: Extend the hook**

Replace `frontend/src/hooks/useTranslated.ts` body:

```typescript
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { translateBatch, type TargetLang } from "../services/translateApi";

const SUPPORTED_TARGETS: ReadonlySet<string> = new Set(["zh-CN"]);

interface Result {
  text: string;
  isLoading: boolean;
  isTranslated: boolean;
}

interface Options {
  precomputed?: string | null;
}

export function useTranslated(
  text: string | null | undefined,
  opts: Options = {}
): Result {
  const { i18n } = useTranslation();
  const lang = i18n.language || "en";
  const isZh = !lang.startsWith("en") && SUPPORTED_TARGETS.has(lang);

  const hasPrecomputed =
    isZh && typeof opts.precomputed === "string" && opts.precomputed.length > 0;

  const shouldTranslate = !!text && isZh && !hasPrecomputed;

  const query = useQuery({
    queryKey: ["translate", lang, text],
    queryFn: async () => {
      const out = await translateBatch([text as string], lang as TargetLang);
      return out[0] ?? (text as string);
    },
    enabled: shouldTranslate,
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });

  if (!text) return { text: "", isLoading: false, isTranslated: false };
  if (!isZh) return { text, isLoading: false, isTranslated: false };
  if (hasPrecomputed)
    return {
      text: opts.precomputed as string,
      isLoading: false,
      isTranslated: true,
    };
  if (query.isLoading) return { text, isLoading: true, isTranslated: false };
  if (query.isError || !query.data)
    return { text, isLoading: false, isTranslated: false };
  return { text: query.data, isLoading: false, isTranslated: true };
}
```

- [ ] **Step 4: Run tests**

Run: `docker compose exec frontend npm test -- useTranslated`

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useTranslated.ts frontend/src/hooks/__tests__/useTranslated.test.ts
git commit -m "feat(i18n): useTranslated accepts precomputed translation"
```

---

## Task 9: Frontend — pass `_zh` fields through `<Translated>`

**Files:**
- Modify: `frontend/src/components/Translated.tsx`
- Modify: `frontend/src/components/ChatMessages.tsx`
- Modify: `frontend/src/components/DecisionTracker.tsx` (sidebar chat list, history entries)
- Modify: any sidebar component that renders `chat.title` / `chat.last_message_preview` (find via grep)

- [ ] **Step 1: Add `precomputed` prop to `<Translated>`**

In `frontend/src/components/Translated.tsx`, extend the component props:

```typescript
interface TranslatedProps {
  text: string | null | undefined;
  precomputed?: string | null;
  className?: string;
  // ...other existing props
}

export function Translated({ text, precomputed, ...rest }: TranslatedProps) {
  const { text: rendered, isLoading, isTranslated } = useTranslated(text, {
    precomputed,
  });
  // ... existing render logic, unchanged
}
```

- [ ] **Step 2: Update message API type**

Find the TS type that mirrors `Message` (likely `frontend/src/types/message.ts` or `frontend/src/services/chatApi.ts`). Add:

```typescript
export interface Message {
  // existing fields...
  content: string;
  content_zh?: string | null;
}
```

Also `Chat`:

```typescript
export interface Chat {
  // existing fields...
  title: string;
  title_zh?: string | null;
  last_message_preview?: string | null;
  last_message_preview_zh?: string | null;
}
```

- [ ] **Step 3: Update `ChatMessages.tsx` to pass precomputed**

Find the existing `<Translated text={message.content} />` (per explore: ChatMessages.tsx ~line 65-72). Change to:

```tsx
<Translated text={message.content} precomputed={message.content_zh} />
```

- [ ] **Step 4: Update DecisionTracker rows**

Find every `<Translated text={...}>` in `DecisionTracker.tsx`. Where the source text comes from a `Message.content` field, pass `message.content_zh`. (Per explore report, the Decision Tracker reads message.content for AI Reasoning row and Full Research modal.)

- [ ] **Step 5: Update sidebar chat list**

Run: `docker compose exec frontend grep -rn "chat.title\|last_message_preview" src/ --include="*.tsx" --include="*.ts"`

For each `<Translated text={chat.title}>` or analogous render of `chat.last_message_preview`, pass the `_zh` sibling:

```tsx
<Translated text={chat.title} precomputed={chat.title_zh} />
<Translated
  text={chat.last_message_preview}
  precomputed={chat.last_message_preview_zh}
/>
```

If a sidebar component renders `{chat.title}` directly (without `<Translated>`), wrap it in `<Translated>` now. (Don't introduce wrapping where the value is non-LLM — UI labels stay as i18next `t()` keys.)

- [ ] **Step 6: Manual browser test**

Run: `make dev` (if not already running) — wait for backend + frontend healthy.

In a browser at `http://localhost:3000`:
1. Switch UI to 中文
2. Open an existing (un-backfilled) chat — `_zh` is null → expect lazy translation flicker (network tab shows `/api/translate`)
3. Create a new chat / send a message in zh-CN — expect content arrives in Chinese **without** any `/api/translate` request after the message lands
4. Side bar new chat title appears in Chinese once the rename API call returns

If step 3 still hits `/api/translate`, the precomputed path isn't wired correctly — re-check that `message.content_zh` is non-null in the network response payload (DevTools).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/Translated.tsx \
        frontend/src/components/ChatMessages.tsx \
        frontend/src/components/DecisionTracker.tsx \
        frontend/src/types/  frontend/src/services/
# adjust paths to match what you actually edited
git commit -m "feat(i18n): frontend reads precomputed _zh from API responses"
```

---

## Task 10: Run backfill on local dev DB and verify

**Files:** None modified — operational task.

- [ ] **Step 1: Dry run, see how many docs are stale**

Run: `docker compose exec backend python -m scripts.backfill_translations --collection all --dry-run`

Note the `would_update` count for each collection.

- [ ] **Step 2: Real backfill**

Run: `docker compose exec backend python -m scripts.backfill_translations --collection all`

Expected: `updated == would_update` from Step 1; `failed` should be small (< 5%).

- [ ] **Step 3: Verify no docs left untranslated**

Run:

```bash
docker compose exec mongo mongosh --quiet --eval '
  use financial_agent;
  print("messages without content_zh:",
        db.messages.countDocuments({content: {$ne: ""}, content_zh: null}));
  print("chats without title_zh:",
        db.chats.countDocuments({title: {$ne: ""}, title_zh: null}));
'
```

Expected: both counts are 0 (or only failed docs from Step 2's `failed` counter).

- [ ] **Step 4: Reload frontend and verify zero `/api/translate` traffic**

In zh-CN browser session, open DevTools → Network → filter "translate". Open existing chats. **Expected: zero `/api/translate` calls.**

- [ ] **Step 5: No commit**

This is an operational step. No artifacts to commit.

---

## Task 11: Final verification + version bump

**Files:**
- Modify: `backend/version.py` (or wherever bump-version writes)
- Modify: `frontend/package.json`
- Modify: `docs/project/versions/backend/CHANGELOG.md`
- Modify: `docs/project/versions/frontend/CHANGELOG.md`

- [ ] **Step 1: Full test sweep**

Run in parallel:

```bash
docker compose exec backend pytest
docker compose exec frontend npm test
```

Expected: both green.

- [ ] **Step 2: Lint + format**

Run:

```bash
docker compose exec backend ruff check src/ tests/ scripts/
docker compose exec backend black --check src/ tests/ scripts/
docker compose exec backend mypy src/services/persistence_translator.py src/database/repositories/message_repository.py src/database/repositories/chat_repository.py
docker compose exec frontend npm run lint
```

Expected: all pass.

- [ ] **Step 3: Bump versions**

```bash
./scripts/bump-version.sh backend minor
./scripts/bump-version.sh frontend minor
```

- [ ] **Step 4: Update changelogs**

Append to `docs/project/versions/backend/CHANGELOG.md`:

```markdown
## [v0.20.0] - 2026-05-05
### Added
- Write-time zh-CN translation: Message.content, Chat.title, Chat.last_message_preview
  now translated and persisted at write time. Lazy /api/translate retained as fallback.
- backfill_translations script for legacy documents.
```

Append to `docs/project/versions/frontend/CHANGELOG.md`:

```markdown
## [v0.13.0] - 2026-05-05
### Changed
- useTranslated accepts a precomputed translation; skips API call when DB-stored
  zh translation is present. Fixes 3s first-render flicker for zh-CN users.
```

- [ ] **Step 5: Final commit**

```bash
git add backend/version.py frontend/package.json docs/project/versions/
git commit -m "chore(release): write-time translation (backend v0.20.0 / frontend v0.13.0)"
```

- [ ] **Step 6: Verify clean working tree**

Run: `git status`

Expected: `nothing to commit, working tree clean`.

---

## Self-Review Checklist (already applied)

- ✅ **Spec coverage** — every section of the spec maps to a task: §5.2 → Tasks 2-3, §5.3 → Task 1, §5.4 → Tasks 4-5, §5.5 → Tasks 8-9, §5.6 → covered by translator's failure path (Task 3) + frontend fallback (Task 8 step 3 fallthrough), §6 backfill → Tasks 6-7+10, §7 testing → woven through, §9 validation → Task 10-11
- ✅ **Type consistency** — `translate_for_persistence(fields, redis_cache, target_lang)` signature is identical across Tasks 2, 3, 4, 5, 7. `useTranslated(text, opts?)` signature consistent in Tasks 8 + 9.
- ✅ **No placeholders** — every code step shows the actual code.
- ✅ **Spec adjustment** — collection table reduced from 4 to 2 (messages + chats) after discovering Phase 2 reasoning is embedded in markdown messages, not separately persisted. Spec doc updated inline.
