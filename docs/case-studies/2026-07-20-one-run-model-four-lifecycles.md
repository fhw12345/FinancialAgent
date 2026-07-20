---
title: One Run Model Had to Survive Four Lifecycles
status: shipped
version: backend@0.38.0, frontend@0.27.0
last_updated: 2026-07-20
owner: maintainer
related_paths:
  - backend/src/models/agent_run.py
  - backend/src/database/repositories/agent_run_repository.py
  - backend/src/api/chat/streaming/handlers.py
  - backend/src/api/portfolio_admin.py
  - frontend/src/components/EnhancedChatInterface.tsx
---

# One Run Model Had to Survive Four Lifecycles

> **TL;DR (EN)**: Chat completion lived in assistant-message metadata while
> Portfolio used a separate fixed-key status document. A shared run table was
> not enough: routing disconnects, async-generator closure, stale leases, and
> migration fallback could still leave executions permanently running. The
> final design uses atomic terminal transitions, unique durable IDs, leased
> compatibility keys, and authoritative reload restoration.
>
> **TL;DR (中文)**：聊天终态原本存在 assistant message metadata，Portfolio
> 则使用另一套固定 key 状态文档。仅仅增加共享 run 表仍不够：路由阶段断连、
> async generator 被关闭、租约过期和迁移 fallback 都可能让任务永久停在
> running。最终方案使用原子终态、唯一 durable ID、带租约的兼容 key，以及
> reload 时的权威状态恢复。

## 1. Context

Direct, ReAct, Deep Research, and Portfolio analysis all represented one user
request differently. There was no common record for policy selection, model
routes, token/tool metrics, failure, cancellation, or reload restoration.

The goal was one `agent_runs` collection without breaking existing Portfolio
buttons or old conversations.

## 2. Investigation

The obvious implementation was to create a run before routing and update it in
each existing handler. Real lifecycle boundaries made that incomplete:

- completion and cancellation could race;
- Portfolio fixed IDs could not also be unique historical run IDs;
- a process crash could retain a unique active key forever;
- closing SSE during route prelude never started the selected handler;
- closing a started async generator raises `GeneratorExit`, not
  `CancelledError`;
- cancellation before chat creation had no `chat_id`;
- an old `analysis_runs` record could still block the new leased path;
- an empty authoritative result needed to preserve old message metadata.

Unit mocks initially hid several of these windows because they consumed the
whole stream and always returned a chat ID.

## 3. Root Cause

Execution identity, user-visible message identity, and compatibility lookup
identity had been conflated.

A durable run also needs ownership of every exit path. If routing, streaming,
background execution, migration fallback, or UI restoration can terminate
outside that ownership boundary, `running` is not a trustworthy state.

## 4. Fix

The shared model now:

- assigns every execution a unique `run_id`;
- uses atomic status preconditions so terminal states are immutable;
- records policy, prompt, model-route, token, tool, error, and cancellation
  metadata;
- stores `portfolio_key` separately and claims one active key with a two-hour
  lease;
- expires stale shared and legacy Portfolio records;
- persists cancellation during routing, route prelude, handler closure, and
  pre-chat setup;
- exposes lookup/list APIs ordered deterministically;
- restores the latest run from the API with message-metadata fallback.

Playwright verifies the same run while active, after completion, and after
browser reload against real MongoDB.

## 5. Lessons

### A state machine is only as durable as its least-owned exit path

Normal completion tests do not cover transport closure, generator finalization,
or process-crash recovery.

### Compatibility keys are not durable identities

`holdings` is useful for a button lookup, but it cannot identify every
historical holdings execution. Store both concepts explicitly.

### Uniqueness requires a recovery policy

A unique active claim without expiration converts a crash into permanent
unavailability. Leases make the invariant recoverable.

### Migration fallback must also obey new invariants

Legacy reads can reintroduce stale behavior even after all new writes use the
correct model.

### Restoration needs an authority and a compatibility path

New chats should trust `agent_runs`; old chats still need terminal message
metadata until migration history naturally ages out.
