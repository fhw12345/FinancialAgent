---
title: Stop Closed the Stream but Left the Agent Running
status: shipped
version: backend@0.36.0, frontend@0.26.0
last_updated: 2026-07-17
owner: maintainer
related_paths:
  - backend/src/api/chat/streaming/cancellation.py
  - backend/src/api/chat/streaming/react_agent.py
  - backend/src/database/repositories/message_repository.py
  - frontend/src/components/chat/useAnalysis.ts
  - frontend/e2e/uaw-005-agent-cancellation.spec.ts
---

# Stop Closed the Stream but Left the Agent Running

> **TL;DR (EN)**: The frontend transport already had an AbortController, but
> the hook discarded its cancel function and an aborted fetch never settled
> the mutation. The backend did not explicitly cancel or await ReAct/Deep
> tasks. We added durable, idempotent cancelled terminal state and proved that
> both the agent and its awaited child stop with no late events.
>
> **TL;DR (中文)**：前端 transport 已有 AbortController，但 hook 丢弃了取消
> 函数，fetch abort 后 mutation 也不会结束；后端没有显式 cancel/await ReAct
> 和 Deep task。修复后增加幂等 cancelled 终态，并证明 agent 与 awaited child
> 都停止且不会产生 late event。

## 1. Context

The chat UI disabled the composer during an active request, but exposed no
working Stop action.

Closing or aborting the browser stream did not guarantee that the backend model
or tool work stopped.

## 2. Investigation

The frontend service returned:

```typescript
() => controller.abort()
```

`useAnalysis` ignored it. `AbortError` was suppressed without resolving or
rejecting the mutation.

The backend had three different cancellation shapes:

- Direct model streaming ran inline;
- ReAct created `agent_task`;
- Deep created a graph task and event queue.

The first implementation exposed several less obvious races:

- `chatId` was part of the mutation key, so `chat_created` reset the observer
  to idle while the old request still ran;
- hook unmount cleanup fired during chat lifecycle changes and cancelled new
  requests accidentally;
- cancellation after message insert but before chat preview update could
  create both completed and cancelled messages;
- Mongo sparse unique indexes still index explicit `null`;
- Stop after the final chunk could race completed persistence;
- AnyIO cancellation could interrupt cleanup a second time.

## 3. Root Cause

Cancellation was treated as a transport concern, not a terminal run state.

There was no stable run identity shared by normal completion and cancellation,
so the system could not make the transition idempotent.

## 4. Fix

The frontend now:

- retains the abort callback;
- uses a stable mutation key across chat creation;
- renders Stop only for cancellable streams;
- settles the mutation on AbortError;
- marks running tool/Deep UI state cancelled.

The backend now:

- races routing against disconnect before streaming starts;
- polls disconnect state while waiting for model/tool/research work;
- cancels and awaits active tasks inside an AnyIO shield;
- assigns a stable `run_id`;
- atomically upserts one assistant terminal message;
- uses a partial unique index only for string run IDs;
- waits for in-flight completed persistence before writing cancelled;
- checks a short disconnect grace after the final chunk.

The E2E agent starts one five-minute awaited child and emits a visible tool
event. The only successful exit is cancellation.

## 5. Lessons

### Abort is not cancellation until the promise settles

An AbortController without ownership in the calling hook is decorative.

### Mutation identity must outlive chat creation

Including a server-assigned `chatId` in the mutation key reset visible pending
state while the request still ran.

### Terminal state needs one durable identity

Completed, failed, and cancelled must update the same run record. Separate
inserts create contradictory history.

### Sparse does not mean null is absent

MongoDB sparse indexes skip missing fields, not explicit `null`. Optional
unique keys need omitted nulls and a partial index.

### Cancellation cleanup is also asynchronous work

Cancelling an awaited task can cancel its cleanup again. Shield cleanup and
explicitly await it before leaving the request lifecycle.
