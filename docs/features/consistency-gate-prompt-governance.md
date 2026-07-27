---
title: Consistency Gate Prompt Governance
status: shipped
version: backend@0.46.0
last_updated: 2026-07-27
owner: maintainer
related_paths:
  - backend/src/agent/prompt_registry.py
  - backend/src/agent/portfolio/consistency_gate.py
  - backend/src/agent/portfolio/flows.py
---

# P1: Consistency Gate Prompt Governance

## Delivered

- `consistency-gate@2` is a deterministic registry template.
- The existing Pydantic `GateVerdict` structured output remains authoritative.
- Clean research skips the LLM and records no prompt version.
- Degraded research records `consistency-gate@2` on the per-symbol result.
- Gate prompt usage can flow into later Portfolio pipeline metadata.

## Acceptance Criteria

- [x] Registry template is used by the LLM call.
- [x] Structured verdict behavior is unchanged.
- [x] Skipped gates do not claim prompt usage.
- [x] Executed gates expose exact prompt version.
- [x] Existing consistency tests pass.

## Implementation Record

Shipped in implementation commit `1aab971`, backend `0.46.0`.
