---
title: Runtime-Linked Prompt Migrations
status: shipped
version: backend@0.44.0
last_updated: 2026-07-27
owner: maintainer
related_paths:
  - backend/src/agent/prompt_registry.py
  - backend/src/agent/llm_client.py
  - backend/src/agent/symbol_resolver.py
  - backend/src/api/chat/streaming/deep_agent.py
---

# P1: Runtime-Linked Prompt Migrations

## Delivered

- `financial-system@3` is the single template used by Direct and ReAct.
- `symbol-extraction@2` is the template used by structured symbol resolution.
- Registry contents are deterministic and independent of import order.
- Symbol prompt usage travels on each `SymbolResolution`, avoiding singleton
  cross-request state.
- Deep runs merge `symbol-extraction@2` only when its LLM prompt actually ran.
- Evaluation does not claim prompt coverage when its deterministic path did
  not consume the prompt.

## Acceptance Criteria

- [x] Direct and ReAct render the same registered financial prompt.
- [x] Symbol resolver renders the registered extraction prompt.
- [x] Registry snapshot is deterministic.
- [x] Prompt metadata is request-local and concurrency-safe.
- [x] Deep run metadata records actual symbol prompt usage.
- [x] Full backend validation passes.

## Follow-Up

Deep planner/debater/verdict, Portfolio phase 2, and consistency-gate prompts
remain to be migrated.

## Implementation Record

Shipped in implementation commit `45bcc66`, backend `0.44.0`.
