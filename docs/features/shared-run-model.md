---
title: Shared Durable Run Model
status: shipped
version: backend@0.38.0, frontend@0.27.0
last_updated: 2026-07-20
owner: maintainer
related_paths:
  - backend/src/models/agent_run.py
  - backend/src/database/repositories/agent_run_repository.py
  - backend/src/services/agent_run_service.py
  - backend/src/api/runs.py
  - backend/src/api/chat/streaming/handlers.py
  - backend/src/api/portfolio_admin.py
  - frontend/src/components/EnhancedChatInterface.tsx
  - frontend/e2e/uaw-007-shared-run-model.spec.ts
---

# UAW-007: Shared Durable Run Model

## 1. Task Summary

Create one durable execution record for:

- instant Direct chat;
- tool-capable ReAct chat;
- Deep Research;
- Portfolio holdings, picks, and single-symbol analysis.

Today chat execution status exists only inside terminal assistant message
metadata, while Portfolio uses a separate `analysis_runs` schema with different
statuses and fixed fields.

## 2. Goal

Introduce one MongoDB `agent_runs` collection with a typed contract:

```text
run_id
chat_id
request_id
portfolio_key
execution_mode
requested_policy
selected_policy
policy_version
prompt_versions
model_routes
status
started_at
finished_at
tool_calls
input_tokens
output_tokens
estimated_cost
data_sources
data_freshness
error_code
error_message
cancel_reason
metadata
```

Statuses:

```text
pending
running
waiting_for_input
completed
failed
cancelled
```

Execution modes:

```text
instant
agentic
research
portfolio
```

## 3. State Machine

Allowed transitions:

```text
pending -> running | waiting_for_input | failed | cancelled
running -> waiting_for_input | completed | failed | cancelled
waiting_for_input -> running | completed | failed | cancelled
```

Terminal states are immutable:

```text
completed | failed | cancelled
```

The repository transition uses an atomic status precondition so concurrent
terminal writers cannot overwrite each other.

Every execution receives a unique `run_id`. Reusable Portfolio identifiers
such as `holdings`, `picks`, and `single_AAPL` are stored in
`portfolio_key`, never used as the durable run ID.

## 4. Chat Lifecycle

The unified handler creates one run ID before automatic routing and injects
that same ID into the selected handler:

```text
create pending run
  -> route policy
  -> attach chat_id
  -> transition running with execution_mode/model routes
  -> execute engine
  -> update metrics
  -> terminal transition
  -> terminal assistant message with the same run_id
```

Routing cancellation creates and cancels the same run.
Disconnects while route events or the first handler event are being emitted
also close the selected handler and persist cancellation. Durable cancellation
does not depend on a chat ID already being available.

Clarification transitions the run to `waiting_for_input`.

Terminal assistant metadata retains `run_id` and `run_status` for restoration,
but the `agent_runs` collection becomes authoritative.

## 5. Portfolio Compatibility

Portfolio APIs keep their existing response shape:

```text
pending | running | done | error
```

Internally they use `agent_runs` and map:

```text
completed -> done
failed -> error
```

Fixed Portfolio lookup keys remain:

```text
holdings
picks
single_<TICKER>
```

This preserves current button idempotency while moving persistence to the
shared model.

Each trigger creates a new unique durable run. Idempotency checks for an
existing `pending` or `running` record with the same `portfolio_key`.
`GET /status/{key}` resolves the newest record for that key and maps it back to
the existing `AnalysisRun` response.

Active Portfolio keys use a two-hour lease. Trigger and status requests expire
stale shared claims, and the temporary `analysis_runs` fallback applies the
same lease so a pre-cutover crashed run cannot block future analysis.

Portfolio compatibility fields are stored in run metadata:

```text
message
result_count
sectors
```

## 6. Version Metadata

Initial explicit versions:

```text
policy_version: auto-router-v1
prompt_versions:
  simple_chat: simple-chat-v1
  react_agent: react-agent-v1
  deep_research: deep-research-v1
  portfolio: portfolio-v1
```

`model_routes` stores provider-neutral role-to-model assignments from the
existing LLM factory. Credentials and endpoint URLs are never persisted.

`request_id`, `estimated_cost`, `data_sources`, and `data_freshness` are
nullable/best-effort placeholders in UAW-007. Idempotency and exact billing
remain later tasks.

## 7. API

```text
GET /api/runs/{run_id}
GET /api/runs?chat_id=<id>&limit=20
```

The list endpoint returns newest first and is capped at 100 records.

## 8. Transitional Frontend Events

Until UAW-009 standardizes all event envelopes, add:

```json
{
  "type": "run_state",
  "run_id": "run_123",
  "status": "running",
  "execution_mode": "agentic"
}
```

The UI displays a compact run badge beside route/stream mode.

New chat and chat selection clear stale state. Chat restoration first queries
the authoritative run API, then falls back to terminal assistant metadata for
pre-UAW-007 conversations or an unavailable/empty run result.

## 9. Tests

### Model/Repository

- create pending run;
- atomic allowed transitions;
- reject terminal-state overwrite;
- attach chat ID and execution metadata;
- list by chat newest first;
- index creation.

### Chat Integration

- run exists before routing;
- Direct completes with instant mode/model route/tokens;
- ReAct completes with tool count and token totals;
- Deep clarification becomes waiting_for_input;
- failure records error code/message;
- cancellation transitions to cancelled;
- terminal assistant message and run share one run ID.

### Portfolio Integration

- holdings/picks/single-symbol write `agent_runs`;
- existing status API maps shared statuses;
- retrigger while running returns the existing run.

## 10. Playwright E2E

Use a deterministic Direct stream:

1. Send one request.
2. Assert the Run badge appears as `running`.
3. Query `/api/runs/{run_id}` and assert:
   - `execution_mode=instant`;
   - selected policy/model route are recorded.
4. Complete the response.
5. Assert badge and API become `completed`.
6. Reload and restore the chat.
7. Assert the same run ID and status are restored.

Screenshot evidence:

```text
docs/features/assets/uaw-007/
  01-durable-run-running.png
  02-durable-run-restored.png
```

## 11. Acceptance Criteria

- [x] One shared run model covers chat and Portfolio.
- [x] Chat run is created before routing.
- [x] Execution mode and selected policy are persisted.
- [x] Model routes and prompt/policy versions are persisted.
- [x] Tokens and tool-call count are updated.
- [x] Completion, failure, cancellation, and clarification are durable.
- [x] Terminal transitions are atomic and immutable.
- [x] Portfolio status API remains compatible.
- [x] Run lookup/list APIs work.
- [x] Frontend displays and restores run ID/status.
- [x] No credentials are persisted.
- [x] Playwright passes with two screenshots.
- [x] Full repository validation passes.

## 12. Non-Goals

UAW-007 does not:

- standardize every SSE event envelope;
- implement client request idempotency;
- merge Direct/ReAct handlers;
- add evaluation datasets;
- calculate provider billing with exact price tables;
- add durable Deep graph checkpoints.

## 13. Follow-Up

After UAW-007:

1. UAW-008 Unified Chat Handler Lifecycle.
2. UAW-009 Standard Agent Event Envelope.
3. UAW-010 Request Idempotency.
4. P1 Agent Evaluation.

## 14. Implementation Record

Shipped in implementation commit `dde269b`, backend `0.38.0`, and frontend
`0.27.0`.

The final implementation includes repository and API coverage, cancellation
race coverage, stale shared/legacy Portfolio lease recovery, frontend
restoration tests, and real MongoDB Playwright evidence.
