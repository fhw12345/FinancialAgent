---
title: Standard Agent Event Envelope
status: shipped
version: backend@0.40.0, frontend@0.28.0
last_updated: 2026-07-21
owner: maintainer
related_paths:
  - backend/src/api/schemas/agent_events.py
  - backend/src/api/chat/streaming/handlers.py
  - frontend/src/services/api.ts
  - frontend/src/types/agentEvents.ts
  - frontend/e2e/uaw-009-agent-events.spec.ts
---

# UAW-009: Standard Agent Event Envelope

## 1. Task Summary

The chat endpoint currently exposes multiple unrelated top-level SSE shapes:

```text
route_selected
run_state
thinking
response_stream_mode
latency
chunk
tool_start | tool_end | tool_error
deep_*
clarification_required
error
done
```

Some Deep events have a local `seq`, while ordinary chat, routing, tools, and
terminal events have no shared ordering identity.

## 2. Goal

Every agent-generated SSE event must use one versioned envelope:

```json
{
  "schema_version": "1.0",
  "run_id": "run_123",
  "stream_id": "run_123",
  "sequence": 8,
  "type": "tool_completed",
  "timestamp": "2026-07-21T02:00:00Z",
  "payload": {}
}
```

The envelope provides:

- one durable run identity;
- one per-delivery stream identity for safe replay;
- one monotonically increasing sequence for the complete stream;
- one canonical event type;
- one UTC timestamp;
- one typed payload boundary.

## 3. Scope Boundary

UAW-009 standardizes the external stream contract.

It does not:

- add request IDs or retry semantics;
- persist an immutable event log;
- resume a disconnected stream;
- remove existing frontend callbacks;
- remove internal Deep `seq` fields from persisted historical metadata.

Request idempotency belongs to UAW-010. Durable replay/checkpoint storage
belongs to the Priority 2 Research Job work.

## 4. Backend Design

Add `backend/src/api/schemas/agent_events.py`.

### 4.1 Envelope

```python
class AgentEventEnvelope(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    stream_id: str
    sequence: int = Field(ge=1)
    type: str
    timestamp: datetime
    payload: dict[str, Any]
```

### 4.2 Per-run sequencer

```python
class AgentEventSequencer:
    def __init__(self, run_id: str): ...
    def wrap(self, legacy_event: dict[str, Any]) -> AgentEventEnvelope: ...
    def format_sse(self, legacy_event: dict[str, Any]) -> str: ...
```

One sequencer is created in the outer unified stream wrapper. It owns every
sequence number from routing prelude through terminal completion.

Handler internals may continue producing current legacy dictionaries during
this migration. The API boundary parses each internal SSE data block and wraps
it before sending it to the browser.

No engine, callback, tool, or sub-agent may allocate the envelope sequence.

## 5. Canonical Event Mapping

The original event is retained inside `payload`, including its original
`type`, so the frontend compatibility adapter can continue invoking existing
callbacks.

| Existing event | Envelope type |
|---|---|
| `run_state: running` | `run_started` |
| `route_selected` | `policy_selected` |
| `thinking` | `model_started` |
| `chunk` | `response_chunk` |
| `tool_start`, `deep_tool_start` | `tool_started` |
| `tool_end`, `tool_error`, `deep_tool_end` | `tool_completed` |
| Deep stage start events | `research_stage_started` |
| Deep result/verdict events | `research_stage_completed` |
| `clarification_required` | `clarification_required` |
| `run_state: completed` | `run_completed` |
| `run_state: failed` | `run_failed` |
| `run_state: cancelled` | `run_cancelled` |
| `run_state: waiting_for_input` | `run_waiting_for_input` |
| `done` | `stream_completed` |

Compatibility extensions retain their current name:

```text
chat_created
response_stream_mode
latency
error
tool_info
```

## 6. SSE Boundary

`chat_stream_unified()` keeps Direct, ReAct, and Deep implementations
unchanged internally.

The outer response wrapper:

1. creates `AgentEventSequencer(run_id)`;
2. emits `run_started`;
3. emits `policy_selected`;
4. parses every internal `data: <json>` block;
5. wraps and emits each event with the next sequence;
6. closes the inner iterator using the existing cancellation-safe behavior.

Malformed internal SSE is an implementation error. It is logged and surfaced;
the wrapper must not silently pass an unsequenced event.

## 7. Frontend Compatibility Adapter

Add `frontend/src/types/agentEvents.ts`:

```typescript
interface AgentEventEnvelope {
  schema_version: "1.0";
  run_id: string;
  sequence: number;
  type: AgentEventType;
  timestamp: string;
  payload: Record<string, unknown>;
}
```

Add:

```typescript
normalizeAgentStreamEvent(
  event: AgentEventEnvelope | StreamEvent,
): StreamEvent
```

Behavior:

- envelope input returns the legacy payload shape;
- legacy input remains supported during migration and in unit fixtures;
- envelope events are deduplicated by `stream_id + sequence`;
- duplicate or lower sequence events do not invoke callbacks twice;
- canonical metadata remains available as `agent_event` on the normalized
  event for diagnostics.

The existing UI callbacks remain unchanged:

```text
onRouteSelected
onRunState
onClarificationRequired
onToolStart / onToolEnd / onToolError
onDeepEvent
onChunk
onDone
onError
```

## 8. Ordering Rules

- Sequence starts at `1` for every run.
- Sequence increases by exactly one for every emitted envelope.
- Routing events precede engine events.
- `run_completed`, `run_failed`, or `run_cancelled` precedes
  `stream_completed`.
- The frontend ignores duplicate `(stream_id, sequence)` envelopes.
- Deep payload `seq` remains diagnostic only; envelope `sequence` is
  authoritative for stream ordering.

## 9. Tests

### Backend

- envelope schema rejects empty run IDs and sequence values below one;
- sequencer increments monotonically;
- every legacy event maps to the expected canonical type;
- multiple SSE blocks in one chunk are wrapped independently;
- Direct, ReAct, and Deep endpoint streams contain no unwrapped data events;
- route prelude cancellation still closes or cancels the correct run;
- malformed internal SSE is surfaced.

### Frontend

- envelope events invoke the same callbacks as legacy fixtures;
- canonical metadata remains available for diagnostics;
- duplicate sequences are ignored;
- out-of-order/lower sequences are ignored;
- legacy events remain supported;
- Direct chunks, tools, Deep progress, clarification, errors, and terminal
  events retain current UI behavior.

## 10. Playwright

Use a deterministic real backend/Mongo profile:

1. Direct request emits ordered `run_started`, `policy_selected`,
   `response_chunk`, and `run_completed`.
2. ReAct request emits `tool_started` and `tool_completed`.
3. Deep request emits research-stage envelopes or clarification.
4. Current chat UI remains unchanged.
5. Reload restores terminal message/run state.

Screenshot evidence:

```text
docs/features/assets/uaw-009/
  01-direct-envelope-completed.png
  02-react-tool-envelope.png
  03-deep-envelope-restored.png
```

## 11. Acceptance Criteria

- [x] Every agent endpoint data event uses envelope schema `1.0`.
- [x] One sequencer owns the complete run stream.
- [x] Sequence numbers are contiguous and monotonic.
- [x] Core events use canonical event types.
- [x] Legacy payload shape is retained inside `payload`.
- [x] Frontend supports envelopes and migration-era legacy fixtures.
- [x] Frontend deduplicates repeated/lower sequence envelopes.
- [x] Direct, ReAct, Deep, tool, clarification, failure, and terminal paths are
  covered.
- [x] Existing UI behavior remains compatible.
- [x] Playwright passes with curated screenshot evidence.
- [x] Full repository validation passes.

## 12. Follow-Up

1. UAW-010 Request Idempotency.
2. P1 Agent Evaluation.
3. Durable event replay and research checkpoints.

## 13. Implementation Record

Shipped in implementation commit `5f32e0d`, backend `0.40.0`, and frontend
`0.28.0`.

The implementation wraps the unified endpoint at its outer boundary, including
persistence-only messages, shields envelope-failure persistence before inner
stream cleanup, and preserves existing callbacks through a frontend adapter.
