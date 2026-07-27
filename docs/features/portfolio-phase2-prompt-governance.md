---
title: Portfolio Phase 2 Prompt Governance
status: shipped
version: backend@0.47.1
last_updated: 2026-07-27
owner: maintainer
related_paths:
  - backend/src/agent/prompt_registry.py
  - backend/src/agent/portfolio_phase2_prompt.py
  - backend/src/agent/portfolio/phase2_decisions.py
---

# P1: Portfolio Phase 2 Prompt Governance

## Delivered

- `portfolio-phase2@4` is a deterministic registry renderer.
- The complete SELL geometry, structured research blocks, citations,
  extended-hours, derivation, examples, and language requirements are
  preserved.
- Phase 2 uses `GovernedPortfolioDecisionList` without modifying the legacy
  oversized model module.
- Prompt version is attached only after the structured LLM call succeeds.
- Persisted Portfolio decision metadata includes the actual prompt version.
- The Phase 2 source file is exactly 500 lines.

## Acceptance Criteria

- [x] Prompt output remains behaviorally equivalent.
- [x] Existing source-inspection tests target the canonical renderer.
- [x] Runtime structured call uses the governed schema.
- [x] Failed/skipped calls do not claim prompt usage.
- [x] Source files satisfy the 500-line limit.
- [x] Existing Phase 2 tests pass.

## Implementation Record

Shipped in implementation commit `3bf826c`, with provenance hardening and
browser evidence in backend `0.47.1`.

Browser evidence:
[Prompt Governance Browser Evidence](prompt-governance-e2e.md).

Provenance hardening and E2E commit: `0c00a48`.
