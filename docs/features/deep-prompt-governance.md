---
title: Deep Prompt Governance
status: shipped
version: backend@0.45.0
last_updated: 2026-07-27
owner: maintainer
related_paths:
  - backend/src/agent/prompt_registry.py
  - backend/src/agent/deep_react_agent.py
  - backend/src/api/chat/streaming/deep_agent.py
---

# P1: Deep Prompt Governance

## Delivered

- `deep-debater@2`, `deep-rebuttal@1`, and `deep-verdict@1` are registry
  templates.
- Original JSON schemas, enums, evidence instructions, and verdict contract
  are preserved.
- Graph state accumulates prompt versions only for nodes that execute.
- Request-local `prompt_used` signals preserve usage across success, failure,
  timeout, and cancellation.
- Prompt metadata persistence cannot prevent task cancellation or failure
  transitions.

## Acceptance Criteria

- [x] Deep templates render from the registry.
- [x] Structured JSON contracts remain equivalent.
- [x] Conditional nodes record only actual prompt usage.
- [x] Concurrent runs do not share prompt state.
- [x] Failure/cancellation preserve used prompt metadata.
- [x] Existing Deep and cancellation tests pass.

## Implementation Record

Shipped in implementation commit `ea0dd16`, backend `0.45.0`.
