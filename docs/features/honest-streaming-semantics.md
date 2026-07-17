---
title: Honest Streaming Semantics
status: shipped
version: backend@0.37.0, frontend@0.26.1
last_updated: 2026-07-17
owner: maintainer
related_paths:
  - backend/src/api/chat/streaming/helpers.py
  - backend/src/api/chat/streaming/simple_agent.py
  - backend/src/api/chat/streaming/react_agent.py
  - backend/src/api/chat/streaming/deep_agent.py
  - frontend/src/components/EnhancedChatInterface.tsx
  - frontend/e2e/uaw-006-streaming-semantics.spec.ts
---

# UAW-006: Honest Streaming Semantics

## Implementation Record

Shipped in commit `9c6f2b5`.

Delivered:

- explicit `response_stream_mode` event for every chat flow;
- Direct `model_tokens` mode with real provider chunks;
- `first_model_token` latency based only on a real model chunk;
- ReAct/Deep `buffered` mode declared before execution;
- removal of ten-character typewriter splitting and artificial response sleeps;
- one complete final response chunk for ReAct and Deep;
- Deep `first_progress_event` separated from final response delivery;
- `first_response_chunk` for buffered answer delivery;
- frontend mode badge reset for every request, new chat, and chat selection;
- browser proof that Direct first token arrives before the second;
- browser proof that buffered ReAct progress appears before final answer.

Validation summary:

```text
UAW-006 backend semantics suite: 13 passed
Backend full regression suite: 1805 passed, 27 deselected
Backend Ruff: passed
Changed backend modules isolated mypy: passed
Frontend stream-mode tests: 2 passed
Frontend full tests: 221 passed
Frontend lint/type-check/build: passed
Playwright streaming semantics scenario: 1 passed
```

### Screenshot Evidence

| Evidence | Scenario | Stack | Commit | Result |
| --- | --- | --- | --- | --- |
| [Live model token stream](assets/uaw-006/01-live-model-token-stream.png) | Direct first token is visible while the second token is still absent | Real frontend/backend/MongoDB + deterministic token agent | `9c6f2b5` | PASS |
| [Buffered response label](assets/uaw-006/02-buffered-response-labelled.png) | ReAct progress is live while final answer remains buffered | Real frontend/backend/MongoDB + deterministic buffered agent | `9c6f2b5` | PASS |

## 1. Task Summary

Make the chat UI and telemetry distinguish real model-token streaming from a
buffered final response.

Current behavior:

- Direct chat consumes a real provider stream;
- ReAct and Deep complete the full agent/graph, then split the final answer
  into ten-character chunks with artificial sleeps.

The latter is a typewriter animation, not model streaming.

## 2. Goal

Introduce an explicit response mode event:

```json
{
  "type": "response_stream_mode",
  "mode": "model_tokens"
}
```

or:

```json
{
  "type": "response_stream_mode",
  "mode": "buffered"
}
```

Semantics:

- `model_tokens`: chunks originate from the model client's async stream;
- `buffered`: the full synthesis completed before any answer content was sent.

## 3. Required Changes

### Direct

- emit `mode=model_tokens`;
- retain provider `stream_chat()`;
- record `first_model_token`;
- keep `stream_complete`.

### ReAct

- emit `mode=buffered` before agent execution;
- keep tool/progress SSE events live;
- send the final answer as one response chunk;
- record `first_response_chunk`;
- remove typewriter sleeps.

### Deep

- emit `mode=buffered` before graph execution;
- keep sub-agent/debate/progress events live;
- rename `first_event` to `first_progress_event`;
- send the final verdict as one response chunk;
- record `first_response_chunk`;
- remove typewriter sleeps.

## 4. Frontend Transparency

The route status area displays one of:

```text
Live model stream
Buffered response
```

The badge resets for every request and is driven only by the backend event.

Progress events remain independent:

```text
tools/sub-agents can stream live
while final response mode is buffered
```

## 5. Non-Goals

UAW-006 does not:

- rewrite ReAct around LangGraph token streaming;
- stream partial Deep verdicts before the graph finishes;
- expose hidden chain-of-thought;
- merge the Direct and ReAct runtimes;
- change cancellation behavior;
- change provider/model selection.

True ReAct/Deep synthesis streaming remains a later engine-level enhancement.

## 6. Tests

### Backend

- Direct emits `model_tokens` and `first_model_token`;
- ReAct emits `buffered`, one content chunk, and
  `first_response_chunk`;
- Deep emits `buffered`, progress events, one content chunk,
  `first_progress_event`, and `first_response_chunk`;
- no handler emits the old ambiguous `first_chunk`;
- ReAct/Deep contain no artificial response delay.

### Frontend

- API parses `response_stream_mode`;
- each request resets the previous mode;
- model-token and buffered badges render correctly.

## 7. Playwright E2E

Use one deterministic app with two routes.

### Scenario A: Real model stream

1. Direct agent emits `FIRST_TOKEN`.
2. It waits before emitting `SECOND_TOKEN`.
3. Browser shows `Live model stream`.
4. Browser observes the first token while the second is absent.

### Scenario B: Buffered agent response

1. ReAct emits progress and waits before returning.
2. Browser shows `Buffered response` while no answer exists.
3. Final content appears only after the agent finishes.

Screenshot evidence:

```text
docs/features/assets/uaw-006/
  01-live-model-token-stream.png
  02-buffered-response-labelled.png
```

## 8. Acceptance Criteria

- [x] Direct chunks are identified as real model tokens.
- [x] `first_model_token` measures a real provider chunk.
- [x] ReAct final answer is sent as one buffered chunk.
- [x] Deep final answer is sent as one buffered chunk.
- [x] Buffered delivery uses `first_response_chunk`.
- [x] Deep progress uses `first_progress_event`.
- [x] No `first_chunk` telemetry remains.
- [x] Tool and Deep progress events remain live.
- [x] Frontend displays the backend-declared mode.
- [x] Playwright proves partial Direct streaming.
- [x] Playwright proves buffered response labeling.
- [x] Two screenshot artifacts are linked.
- [x] Full repository validation passes.

## 9. Follow-Up

After UAW-006:

1. Shared Run model.
2. Unified event envelope.
3. True streaming synthesis for compatible agent engines.
4. Durable Research Job checkpoints.
