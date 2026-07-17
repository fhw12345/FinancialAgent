---
title: Agent Task Cancellation
status: shipped
version: backend@0.36.0, frontend@0.26.0
last_updated: 2026-07-17
owner: maintainer
related_paths:
  - backend/src/api/chat/streaming/cancellation.py
  - backend/src/api/chat/streaming/simple_agent.py
  - backend/src/api/chat/streaming/react_agent.py
  - backend/src/api/chat/streaming/deep_agent.py
  - frontend/src/components/chat/useAnalysis.ts
  - frontend/src/components/chat/ChatInput.tsx
  - frontend/e2e/uaw-005-agent-cancellation.spec.ts
---

# UAW-005: Agent Task Cancellation

## Implementation Record

Shipped in commit `5b4ac7a`.

Delivered:

- stable frontend stream mutation state across `chat_created`;
- visible Stop button backed by the existing AbortController;
- explicit AbortError settlement and localized cancelled text;
- cancelled tool and Deep accordion states without error-shaped UI;
- cancellable routing classifier before a StreamingResponse exists;
- Direct provider queue pumping with disconnect polling;
- ReAct and Deep task cancellation with awaited child propagation;
- AnyIO-shielded task cleanup and persistence;
- stable per-request `run_id` and atomic terminal assistant-message upsert;
- partial unique Mongo index restricted to string run IDs, including migration
  from the earlier sparse index;
- final response-chunk disconnect grace before completed status;
- cancelled terminal status that overwrites the same run rather than creating a
  contradictory duplicate;
- real browser proof that agent and child work stop, no late event appears, and
  MongoDB restores the cancelled state.

Validation summary:

```text
UAW-005 backend cancellation suite: 16 passed
Backend full regression suite: 1802 passed, 27 deselected
Backend Ruff: passed
Changed backend modules isolated mypy: passed
Frontend cancellation/deep-state suite: 50 passed
Frontend full tests: 220 passed
Frontend lint/type-check/build: passed
Playwright cancellation scenario: 1 passed
```

### Screenshot Evidence

| Evidence | Scenario | Stack | Commit | Result |
| --- | --- | --- | --- | --- |
| [Stop cancels active work](assets/uaw-005/01-stop-cancels-active-run.png) | Browser Stop cancels the ReAct agent and awaited child with no late event | Real frontend/backend/MongoDB + deterministic slow agent | `5b4ac7a` | PASS |
| [Cancelled state after reload](assets/uaw-005/02-cancelled-status-after-reload.png) | Reload restores the durable cancelled assistant run | Real frontend/backend/MongoDB + deterministic slow agent | `5b4ac7a` | PASS |

## 1. Task Summary

Make the chat **Stop** action cancel active backend work instead of only
closing the browser stream.

Cancellation must:

- abort the browser fetch;
- settle the frontend mutation immediately;
- cancel and await the backend agent task;
- propagate into awaited model, tool, and research child tasks;
- stop future tool/progress events;
- persist a `cancelled` run status;
- restore the cancelled state after browser reload.

This is the fifth correctness task from the
[Unified Agent Workflow Improvement Roadmap](../architecture/unified-agent-workflow-roadmap.md).

## 2. Current Problem

The frontend transport creates an `AbortController` and returns:

```typescript
() => controller.abort()
```

`useAnalysis` ignores that return value. The UI has a translated “Stop” label,
but `ChatInput` always renders a send button.

When a fetch is aborted, `sendMessageStreamPersistent()` suppresses
`AbortError` without calling `onDone` or `onError`. The React Query mutation
therefore remains pending.

The backend has three different execution shapes:

- direct chat iterates the model stream inline;
- ReAct creates `agent_task` and polls a tool event queue;
- Deep creates `agent_task` and polls a hierarchy event queue.

None explicitly handles `asyncio.CancelledError` from the streaming response
generator. ReAct and Deep do not guarantee their task is cancelled and awaited.

## 3. Goal

Introduce one cancellation contract shared by all chat handlers:

```text
browser abort or ASGI disconnect
  -> detect cancellation
  -> cancel active task
  -> await task termination
  -> persist assistant cancellation marker
  -> end stream without error event
```

Persisted assistant metadata:

```json
{
  "run_status": "cancelled",
  "cancelled_at": "2026-07-17T08:00:00Z",
  "raw_data": {
    "route_selected": {},
    "deep_events": []
  }
}
```

Until the shared Run model is introduced, message metadata is the durable
status record.

## 4. Non-Goals

UAW-005 does not:

- introduce the shared Run collection;
- resume cancelled work;
- cancel completed requests retroactively;
- guarantee cancellation inside third-party APIs that ignore coroutine
  cancellation;
- add portfolio batch cancellation;
- change response streaming semantics.

## 5. Backend Contract

Add shared helpers:

```python
class ClientDisconnected(Exception):
    ...

async def raise_if_disconnected(request):
    ...

async def cancel_and_await(task):
    ...

async def persist_cancelled_run(...):
    ...
```

Rules:

- `CancelledError` is never converted into `AGENT_ERROR`.
- cancellation persistence is shielded from the disconnected response task;
- an active task is cancelled once and awaited;
- completed tasks are not cancelled;
- partial direct-model text may be persisted with a cancellation suffix;
- Deep cancellation metadata includes collected progress events and a
  `deep_cancelled` event.

## 6. Handler Behavior

### Direct

Pump provider chunks through a queue so the handler can check client
disconnects even while waiting for the next model token.

### ReAct

Check disconnect state while polling the tool queue. On cancellation:

```text
cancel agent_task
await agent_task
persist cancelled
stop draining tool events
```

### Deep

Poll the hierarchy event queue with a bounded timeout instead of waiting
forever. Cancel the graph task and persist partial events.

## 7. Frontend Behavior

`useAnalysis` retains the active transport abort callback.

It exposes:

```typescript
cancelActiveRequest(): void
```

On cancellation:

- abort the request;
- replace the streaming placeholder with localized cancelled text;
- resolve the mutation as cancelled;
- re-enable the composer;
- mark an active Deep accordion as cancelled.

`ChatInput` renders a Stop button only for cancellable chat streaming. Direct
analysis button mutations remain non-cancellable in UAW-005.

Browser connection closure is detected by the backend even when the Stop
button cannot run, such as refresh or tab close.

## 8. Tests

### Backend Unit/Integration

- cancellation helper cancels and awaits one task;
- direct stream cancellation closes the provider iterator;
- ReAct disconnect cancels `agent_task`;
- Deep disconnect cancels the graph task;
- cancelled status is persisted once;
- cancellation is not stored as an error;
- no tool events are emitted after cancellation.

### Frontend

- AbortError invokes the cancellation callback;
- the mutation settles after cancellation;
- the placeholder becomes cancelled text;
- ChatInput switches between Send and Stop;
- browser connection closure is detected by the backend;
- Deep state transitions from running to cancelled.

## 9. Playwright E2E

Use a deterministic slow ReAct agent that starts one awaited child operation.
The browser and backend cancellation path remain real.

Scenario:

1. Send a tool-capable AAPL request.
2. Wait until the backend agent and child operation are running.
3. Click **Stop**.
4. Assert the composer is enabled and cancelled text is visible.
5. Assert backend status reports:
   - agent cancelled;
   - child cancelled;
   - agent not completed;
   - no late event emitted.
6. Reload the browser.
7. Restore the same chat and assert the cancelled status remains visible.

Screenshot evidence:

```text
docs/features/assets/uaw-005/
  01-stop-cancels-active-run.png
  02-cancelled-status-after-reload.png
```

## 10. Acceptance Criteria

- [x] Stop aborts the browser request.
- [x] The frontend mutation settles and composer re-enables.
- [x] Direct, ReAct, and Deep handlers detect cancellation.
- [x] Active backend tasks are cancelled and awaited.
- [x] Awaited child work receives cancellation.
- [x] No tool/progress events appear after cancellation.
- [x] `run_status=cancelled` is persisted.
- [x] Cancellation is not rendered as an error.
- [x] Deep accordion can render cancelled state.
- [x] Reload restores the cancelled message/state.
- [x] Playwright passes with two screenshots.
- [x] Full repository validation passes.

## 11. Risks

| Risk | Mitigation |
| --- | --- |
| Browser abort races with request completion | Cancel only unfinished tasks and make persistence idempotent per generator |
| Persistence is cancelled with the response task | Shield the cancellation write |
| Detached child task survives | Avoid detached tasks; cancel known child task in deterministic E2E |
| Frontend mutation stays pending | Invoke explicit `onCancelled` transport callback |
| Deep UI remains spinning | Add a persisted and local cancelled action |

## 12. Follow-Up

After UAW-005:

1. UAW-006 Honest Streaming Semantics.
2. Shared Run model.
3. Durable Research Job checkpoints.
