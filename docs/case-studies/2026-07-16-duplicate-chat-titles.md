---
title: Generic Chat Titles Hid Conversation Identity
status: shipped
version: backend@0.32.1
last_updated: 2026-07-16
owner: maintainer
related_paths:
  - backend/src/core/utils/title_utils.py
  - backend/src/services/chat_service.py
  - backend/src/database/repositories/chat_repository.py
  - backend/src/api/chat/streaming/
---

# Generic Chat Titles Hid Conversation Identity

> **TL;DR (EN)**: The sidebar accumulated many `New Chat` and `Chat Analysis`
> entries because v2 never updated titles, error and clarification paths exited
> early, and the heuristic collapsed unmatched Chinese requests into one
> generic fallback. Titles are now generated at request start from the selected
> symbol and the user's topic, and exact duplicates receive numeric suffixes.
>
> **TL;DR (中文)**：左侧列表长期积累大量 `New Chat` 和 `Chat Analysis`，原因是
> v2 没有更新标题、错误和澄清路径提前返回，以及中文问题无法命中英文关键词后统一
> 回退到泛化标题。现在请求开始时就会根据选中股票和用户主题生成标题，完全同名时
> 自动追加编号。

## 1. Context

After repeated manual testing, the sidebar contained titles such as:

```text
Chat Analysis
Chat Analysis
Chat Analysis
New Chat
New Chat
```

The previews clearly referred to different subjects, including SK hynix,
Microsoft, P/E explanation, and unresolved deep research. The title therefore
failed its primary purpose: identifying a conversation before opening it.

## 2. Investigation

The persisted title distribution showed three independent behaviors:

1. ReAct responses without a `[chat_title: ...]` marker used the heuristic.
2. The heuristic returned `Chat Analysis` when no uppercase ticker or English
   action keyword appeared in the original user message.
3. v2, clarification, timeout, and error paths could finish without calling
   title update at all.

The heuristic also built an `assistant_response` string but accidentally
extracted symbols only from `user_message`, so its documented fallback context
was not actually used.

## 3. Root Cause

Title generation was treated as response decoration rather than conversation
identity.

That created two fragile dependencies:

- the model had to emit a special title marker;
- the successful response path had to reach the final title-update call.

Chinese messages such as:

```text
海力士现在股价多少，最近表现怎么样？
```

contained neither an explicit uppercase ticker nor English keywords, even
though the frontend had already supplied `current_symbol=SKHY`.

## 4. Fix

Titles are now assigned after the user message is persisted but before agent
execution starts.

The deterministic generator uses this priority:

```text
explicit ticker
  -> selected UI symbol
  -> symbol grounded in assistant response
  -> cleaned user-topic excerpt
```

It also:

- recognizes Chinese price and deep-research intent;
- preserves specific no-symbol questions instead of generic action labels;
- replaces only known placeholders such as `New Chat` and `Chat Analysis`;
- rejects generic LLM-generated titles;
- checks existing titles and appends `(2)`, `(3)`, and so on.

A one-time local backfill changed 11 generic titles. Existing custom titles
were not modified.

## 5. Lessons

### Identity metadata should not depend on successful completion

A failed or paused workflow still needs a recognizable conversation title.

### Frontend context is domain context

When the user asks about “this company,” the selected symbol must participate
in title generation just as it participates in agent execution.

### Generic fallback labels destroy information

When structured classification fails, a cleaned excerpt of the user's own
words is usually more useful than `Analysis`.

### Duplicate semantics and duplicate labels are different problems

Identical test prompts may legitimately produce the same base title. A stable
numeric suffix preserves the semantic title while keeping list entries
distinguishable.
