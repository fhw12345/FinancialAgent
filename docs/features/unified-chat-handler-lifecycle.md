---
title: Unified Chat Handler Lifecycle
status: shipped
version: backend@0.39.0, frontend@0.27.1
last_updated: 2026-07-20
owner: maintainer
related_paths:
  - backend/src/api/chat/streaming/lifecycle.py
  - backend/src/api/chat/streaming/simple_agent.py
  - backend/src/api/chat/streaming/react_agent.py
  - backend/src/api/chat/streaming/deep_agent.py
  - backend/src/api/chat/streaming/handlers.py
  - frontend/src/components/chat/useAnalysis.ts
  - frontend/e2e/uaw-008-unified-lifecycle.spec.ts
---

# UAW-008: Unified Chat Handler Lifecycle

## 1. Task Summary

Direct, ReAct, and Deep Research currently repeat the same request lifecycle:

```text
create/get chat
  -> attach durable run
  -> persist user message
  -> update initial title
  -> load and compact Mongo history
  -> execute engine
  -> persist terminal assistant message
  -> update run metrics/status
  -> update final title
  -> handle failure/cancellation
```

The repeated code has already diverged in title failure handling, run-state
emission, cancellation cleanup, error persistence, and file size.

## 2. Goal

Introduce one lifecycle owner for behavior shared by every chat engine while
preserving the existing external SSE payloads.

After this task:

- one component owns chat/run initialization;
- one component owns Mongo-authoritative context preparation;
- one component owns assistant terminal-message persistence;
- one component owns completion, failure, clarification, and cancellation
  transitions;
- Direct, ReAct, and Deep handlers contain only engine-specific execution and
  progress behavior;
- UAW-009 can standardize event envelopes without also untangling persistence.

## 3. Scope Boundary

UAW-008 standardizes the **internal lifecycle**, not the public event schema.

Existing frontend events remain unchanged:

```text
chat_created
thinking
response_stream_mode
latency
chunk
tool_*
deep_*
clarification_required
run_state
error
done
```

UAW-009 will add the standard sequenced event envelope.

## 4. Shared Lifecycle API

Add `backend/src/api/chat/streaming/lifecycle.py`.

### 4.1 Stateful lifecycle owner

```python
class ChatStreamLifecycle:
    async def start(self) -> dict[str, Any] | None: ...
    async def prepare_context(
        self,
        *,
        include_symbol_context: bool,
    ) -> PreparedConversationContext | None: ...
    async def complete(
        self,
        completion: ChatCompletion,
    ) -> AsyncGenerator[str, None]: ...
    async def fail(
        self,
        failure: ChatFailure,
    ) -> AsyncGenerator[str, None]: ...
    async def clarify(
        self,
        clarification: ChatClarification,
    ) -> AsyncGenerator[str, None]: ...
    async def cancel(
        self,
        *,
        active_task: asyncio.Task[Any] | None,
        agent_type: str,
        partial_content: str = "",
        extra_raw_data: dict[str, Any] | None = None,
        cancel_reason: str = "client_cancelled",
    ) -> None: ...
```

The lifecycle stores:

```text
request
user_id
chat_id
run_id
route_metadata
request start time
current persisted user message
prepared conversation context
in-flight terminal persistence task
```

### 4.2 Typed internal terminal results

```python
@dataclass(frozen=True)
class ChatCompletion:
    content: str
    execution_mode: ExecutionMode
    agent_type: str
    llm_title: str | None = None
    update_final_title: bool = False
    model: str | None = None
    trace_id: str | None = None
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int | None = None
    raw_data: dict[str, Any] | None = None
    latency_metrics: dict[str, Any] | None = None
    done_data: dict[str, Any] | None = None


@dataclass(frozen=True)
class ChatFailure:
    execution_mode: ExecutionMode
    error_code: str
    error_message: str
    client_message: str


@dataclass(frozen=True)
class ChatClarification:
    execution_mode: ExecutionMode
    agent_type: str
    content: str
    payload: dict[str, Any]
```

Engine handlers construct typed results. The lifecycle converts them into the
existing message metadata, durable run transitions, and legacy SSE strings.

## 5. Lifecycle Responsibilities

### 5.1 Start

`start()`:

1. gets or creates the chat;
2. stores the authoritative `chat_id`;
3. attaches the durable run;
4. returns the existing `chat_created` payload when applicable.

Handlers may emit engine-specific eager `thinking` events immediately after
`start()` so event ordering remains unchanged.

### 5.2 Context preparation

`prepare_context()`:

1. persists the incoming message;
2. returns `None` for non-user/tool-source messages;
3. attempts the initial title update without failing the run;
4. loads persisted messages;
5. optionally adds the Direct/ReAct active-symbol instruction;
6. calls `ConversationContextService.prepare(...)`.

Deep Research uses the same method with `include_symbol_context=False` because
its resolver receives `current_symbol` separately.

### 5.3 Completion

`complete()`:

1. atomically upserts the terminal assistant message using the durable run ID;
2. awaits the shielded terminal write;
3. updates run metrics and transitions to `completed`;
4. yields `run_state=completed` before any post-terminal title I/O;
5. attempts the final title update when requested;
6. yields `stream_complete` and `done`.

If the run transition throws after the message write, the lifecycle compensates
the stable message to `failed`, attempts a failed run transition, and emits one
infrastructure error instead of re-entering handler error logic.

### 5.4 Failure

`fail()`:

1. yields the current error event before durable persistence;
2. transitions the durable run to `failed`;
3. yields the run-state event when persistence succeeds;
4. never converts title or telemetry failures into execution failure.

Transition exceptions are logged and contained so they cannot emit duplicate
errors or retry the same terminal path through the outer handler.

Deep partial-progress assistant messages remain engine-specific data passed
before the shared failure transition.

### 5.5 Clarification

`clarify()`:

1. persists the clarification assistant message;
2. yields `clarification_required`;
3. transitions the run to `waiting_for_input`;
4. yields `run_state` and `done`.

If the transition fails, the message is compensated to `failed`, the actionable
card is removed from live/reloaded UI, and the lifecycle emits an error rather
than `done`.

### 5.6 Cancellation

`cancel()`:

1. cancels and awaits the active engine task;
2. waits for an in-flight terminal write;
3. transitions the durable run to `cancelled`;
4. upserts the cancellation assistant message when a chat exists;
5. preserves partial Direct content and Deep progress metadata.

`GeneratorExit`, browser disconnect, and task cancellation all use this path.

## 6. Handler Responsibilities After Refactor

### Direct

- provider token queue;
- true model-token chunks;
- first-token latency;
- provider token usage extraction.

### ReAct

- tool callback queue;
- agent timeout;
- buffered final answer extraction;
- tool/trace/token result mapping.

### Deep Research

- symbol resolution;
- sub-agent progress queue;
- research timeout;
- partial Deep event collection;
- research-context result mapping.

## 7. File-Size Target

All source files must stay below 500 lines.

Expected result:

```text
lifecycle.py       < 500
simple_agent.py    < 250
react_agent.py     < 400
deep_agent.py      < 475
handlers.py        < 260
```

## 8. Tests

### Lifecycle unit tests

- start creates/attaches one chat and run;
- non-user messages persist once and skip context/engine work;
- Direct/ReAct symbol context remains enabled;
- Deep context remains resolver-driven;
- initial/final title failures are warning-only;
- completion writes one terminal message and one terminal run state;
- failure emits the same error/run-state shape;
- clarification persists `waiting_for_input`;
- cancellation before chat creation still cancels the run;
- cancellation after terminal persistence cannot overwrite completion.

### Handler parity tests

- Direct token order and latency stages unchanged;
- ReAct tool/progress and buffered response events unchanged;
- Deep clarification/progress/research metadata unchanged;
- all three handlers use the shared lifecycle.

### Playwright

Use a deterministic app that routes one Direct request and one Deep
clarification request:

1. Direct completes and restores the same run after reload.
2. Deep clarification persists `waiting_for_input`.
3. Existing event shapes remain consumable by the current frontend.

Screenshot evidence:

```text
docs/features/assets/uaw-008/
  01-direct-lifecycle-restored.png
  02-deep-clarification-lifecycle-restored.png
```

## 9. Acceptance Criteria

- [x] One lifecycle component is used by Direct, ReAct, and Deep.
- [x] Chat creation, run attachment, and user-message persistence are shared.
- [x] Mongo-authoritative context preparation is shared.
- [x] Initial and final title handling is shared and warning-only.
- [x] Completion message/run persistence is shared.
- [x] Failure, clarification, and cancellation transitions are shared.
- [x] Engine handlers retain only engine-specific execution/progress logic.
- [x] Existing SSE payload shapes and frontend behavior remain compatible.
- [x] Every source file is at most 500 lines.
- [x] Direct/ReAct/Deep regression tests pass.
- [x] Playwright proves completion, clarification, and reload behavior.
- [x] Full repository validation passes.

## 10. Non-Goals

UAW-008 does not:

- add sequence numbers or replace current SSE payloads;
- add request idempotency;
- merge the three LLM engine implementations;
- change routing policy;
- change model assignments or prompts;
- add durable Deep graph checkpoints.

## 11. Follow-Up

1. UAW-009 Standard Agent Event Envelope.
2. UAW-010 Request Idempotency.
3. P1 Agent Evaluation.

## 12. Implementation Record

Shipped in implementation commit `80e8d5d`, backend `0.39.0`, and frontend
`0.27.1`.

The final implementation includes typed completion/failure/clarification
contracts, one lifecycle owner across all three handlers, transition-failure
compensation, terminal-event race coverage, and real MongoDB browser evidence.
