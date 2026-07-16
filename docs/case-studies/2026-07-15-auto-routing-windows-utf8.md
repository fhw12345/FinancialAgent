---
title: Automatic Routing Exposed Windows Streaming Bugs
status: shipped
version: backend@0.31.0, frontend@0.24.0
last_updated: 2026-07-15
owner: maintainer
related_paths:
  - backend/src/api/chat/streaming/simple_agent.py
  - backend/src/main.py
  - backend/src/services/persistence_translator.py
  - backend/src/agent/flow_router.py
---

# Automatic Routing Exposed Windows Streaming Bugs

## TL;DR (English)

Automatic routing sent concept questions through the previously underused v2
streaming path. Real Chinese input exposed two independent defects: an async
generator was incorrectly wrapped with `asyncio.wait_for`, and a warning logged
raw CJK text to a cp1252 Windows console. The stream now uses
`asyncio.timeout`, backend stdio is configured as UTF-8, and persistence logs no
longer include user text snippets.

## TL;DR（中文）

自动路由让概念问题真正进入此前较少使用的 v2 流式链路，中文请求因此暴露出两个独立问题：
异步生成器被错误地传给 `asyncio.wait_for`，以及持久化警告把中文原文写入 Windows
cp1252 控制台。现在流式超时改用 `asyncio.timeout`，后端标准输出统一为 UTF-8，
日志也不再记录用户文本片段。

## Failure Chain

1. `agent_version=auto` correctly selected v2 for “什么是市盈率”.
2. `asyncio.wait_for(stream_with_timeout())` received an async generator rather
   than a coroutine and raised before any LLM chunk could stream.
3. After fixing iteration, message persistence logged `text_head` for an
   already-Chinese message.
4. The Windows process used a cp1252-compatible console encoding, so logging
   the CJK snippet raised `UnicodeEncodeError`.

## Fix

- Iterate the model stream inside `asyncio.timeout(120)`.
- Reconfigure backend stdout/stderr as UTF-8 during module startup.
- Log only field name, length, and CJK ratio; never raw user text.
- Add a regression test that consumes the v2 `StreamingResponse` body and
  asserts chunk/done events without `STREAM_ERROR`.

## Lesson

Routing changes alter which dormant paths receive production traffic. Validate
each selected flow end-to-end with representative Unicode input, not only the
router's classification result.
