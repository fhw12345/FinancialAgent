---
title: Request Idempotency
status: shipped
version: backend@0.41.0, frontend@0.28.1
last_updated: 2026-07-21
owner: maintainer
related_paths:
  - backend/src/api/schemas/chat_models.py
  - backend/src/database/repositories/agent_run_repository.py
  - backend/src/services/agent_run_service.py
  - backend/src/api/chat/streaming/handlers.py
  - frontend/src/services/api.ts
---

# UAW-010: Request Idempotency

## Goal

Duplicate clicks and network retries with the same client `request_id` must
reuse one durable run, write one user message, execute one agent job, and keep
one terminal assistant message.

## Contract

- The client sends a stable UUID-like `request_id`.
- `agent_runs.request_id` has a unique partial MongoDB index.
- The first atomic insert owns execution.
- Duplicate active requests return the existing run state without executing.
- Duplicate terminal requests replay the persisted assistant message and run
  state through UAW-009 envelopes.
- Existing callers without `request_id` remain supported during migration.

## Tests

- concurrent claims return one winner;
- duplicate active requests do not route or invoke an agent;
- completed retry replays the same run/message;
- one user and one assistant message remain in MongoDB;
- frontend forwards a stable request ID;
- Playwright proves duplicate POSTs execute the deterministic agent once.

## Acceptance Criteria

- [x] Unique partial request-ID index exists.
- [x] Atomic request claim has one execution winner.
- [x] Duplicate active requests reuse current run state.
- [x] Duplicate terminal requests replay persisted output.
- [x] Duplicate requests create no duplicate messages or agent work.
- [x] Legacy requests without IDs remain compatible.
- [x] Full tests and Playwright pass.

## Implementation Record

Shipped in implementation commit `70e15c3`, backend `0.41.0`, and frontend
`0.28.1`.

Replay deliveries retain the durable `run_id` but receive a distinct
`stream_id`, preventing sequence collisions with the original stream.
