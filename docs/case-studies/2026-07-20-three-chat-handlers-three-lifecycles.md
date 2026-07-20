---
title: Three Chat Handlers Had Three Lifecycles
status: shipped
version: backend@0.39.0, frontend@0.27.1
last_updated: 2026-07-20
owner: maintainer
related_paths:
  - backend/src/api/chat/streaming/lifecycle.py
  - backend/src/api/chat/streaming/simple_agent.py
  - backend/src/api/chat/streaming/react_agent.py
  - backend/src/api/chat/streaming/deep_agent.py
  - frontend/src/components/chat/useAnalysis.ts
---

# Three Chat Handlers Had Three Lifecycles

> **TL;DR (EN)**: Direct, ReAct, and Deep Research repeated chat creation,
> context preparation, titles, terminal persistence, and cancellation. Moving
> that code into one helper exposed subtle ordering rules: errors must reach
> the client before a failing transition, completed state must arrive before
> title I/O, and failed clarification must stop being actionable. A stateful
> shared lifecycle now owns those boundaries while engines keep only their
> execution-specific logic.
>
> **TL;DR (中文)**：Direct、ReAct、Deep Research 各自重复 chat 创建、上下文、
> title、终态持久化和取消逻辑。抽取共享代码后才暴露真正的时序约束：transition
> 失败前必须先让客户端看到 error，completed 必须先于 title I/O 发出，失败的
> clarification 也不能继续可操作。现在由一个有状态 lifecycle 统一拥有这些
> 边界，engine 仅保留自身执行逻辑。

## 1. Context

The three chat handlers had grown independently:

- Direct streamed provider tokens;
- ReAct streamed tool progress and buffered its answer;
- Deep streamed research progress and could stop for symbol clarification.

Their engine behavior was legitimately different, but approximately forty
lifecycle operations were duplicated across the files. Deep exceeded the
repository's 500-line source limit.

## 2. Investigation

The first design extracted setup and terminal helpers. Happy-path tests passed,
but fault injection and stream closure exposed hidden contracts:

- returning a list of events delayed the error until Mongo writes completed;
- a transition exception re-entered the outer handler and emitted a second
  error;
- writing a completed message before a failed run transition created
  contradictory terminal records;
- failed clarification still restored an actionable candidate card;
- completed run state was buffered behind final title persistence;
- late transport errors could downgrade an already completed frontend result.

These were not engine problems. They were lifecycle ownership problems.

## 3. Root Cause

The code treated persistence, SSE emission, and transport completion as nearby
steps rather than one ordered state machine.

Extracting duplicated lines without preserving yield points moved observable
events across asynchronous database and title operations. A shared helper was
not enough; the helper had to own state and expose async generators at the
places where event ordering matters.

## 4. Fix

`ChatStreamLifecycle` now owns:

- chat creation and durable run attachment;
- incoming-message persistence;
- Mongo-authoritative context preparation;
- initial and final title handling;
- stable terminal assistant-message upserts;
- completed, failed, waiting, and cancelled transitions;
- completion/clarification compensation when a transition fails.

Typed `ChatCompletion`, `ChatFailure`, and `ChatClarification` values cross the
engine/lifecycle boundary.

Failure and clarification methods are async generators so user-visible events
can be yielded before durable transitions. Completion also yields
`run_state=completed` before final-title I/O.

The frontend treats that completed state as authoritative, ignores later
transport errors/Abort, and removes clarification cards for failed or
cancelled messages.

## 5. Lessons

### Shared code must preserve asynchronous yield points

Two implementations can call the same functions in the same order and still
behave differently if one buffers events until every await finishes.

### Terminal state should outrank post-terminal enrichment

Title generation and telemetry are useful, but they cannot delay the event
that tells the client the run is complete.

### Compensation needs to update user-visible metadata

Changing only the run record is insufficient when reload can also reconstruct
UI from assistant-message metadata.

### Error handling must not re-enter itself

A failure while persisting failure state is infrastructure failure, not a new
engine failure. Log and contain it instead of recursively retrying the outer
path.

### Engine differences do not justify lifecycle duplication

Direct tokens, ReAct tools, and Deep research progress remain separate. Chat
identity, context authority, titles, and terminal state do not.
