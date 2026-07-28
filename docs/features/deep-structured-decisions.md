---
title: Deep Structured Decisions
status: shipped
version: backend@0.48.0, frontend@0.28.1
last_updated: 2026-07-28
owner: maintainer
related_paths:
  - backend/src/agent/debate_types.py
  - backend/src/agent/deep_workflow.py
  - backend/src/agent/deep_agent_adapter.py
  - backend/src/api/chat/streaming/deep_agent.py
  - backend/src/api/chat/streaming/lifecycle.py
  - backend/src/api/chat/streaming/durable_tasks.py
  - backend/src/api/chat/streaming/deep_verdict_persistence.py
  - backend/src/database/repositories/portfolio_order_repository.py
  - backend/src/models/run_identity.py
  - frontend/e2e/prompt-governance.spec.ts
---

# P1: Deep Structured Decisions

Shipped in implementation commit `3631bae`, backend `0.48.0`, with browser
evidence captured by the Prompt Governance Playwright flow.

## Delivered

- Debater concerns and rebuttals accept one strict JSON object validated by
  Pydantic; regex/code-fence extraction is removed.
- Invalid structured debate output raises typed failures instead of silently
  continuing with empty decisions.
- Standalone `NO FURTHER CONCERNS` termination remains supported.
- Verdict uses Pydantic structured output with Markdown report plus action,
  conviction, risk level, key insight, and concern assessments.
- Markdown action must match the structured action before persistence.
- Persisted Deep assistant metadata retains the complete structured verdict.
- Debater skills use the same strict JSON schema and enums.
- Concern IDs are namespaced by debate round, and rebuttals must cover those
  exact IDs once.
- Verdict concern assessments must cover every debated concern exactly once.
- The per-call `enable_debate` setting controls the actual graph topology.
- Verdict signals persist only after the assistant message and durable run
  transition succeed.
- Signal persistence is cancellation-safe, uses real chat/run/message
  provenance, and is idempotent through a deterministic atomic upsert.

## Contracts

### Debate and Rebuttal

- Debater and defender output is one unfenced JSON object.
- Unknown fields, missing fields, duplicate IDs, empty arrays, and invalid enum
  values fail with typed validation errors.
- Every round stores IDs such as `R1-C1` and `R2-C1` so evidence cannot cross
  between rounds.
- Every rebuttal copies the exact displayed concern ID.

### Verdict

- The model returns `report_markdown`, `action`, `conviction`, `risk_level`,
  `key_insight`, and `concern_assessments`.
- Each Action or Recommendation field in Markdown contains exactly one
  unqualified `BUY`, `HOLD`, or `SELL` value.
- Every displayed action must match the structured action.
- Every concern receives exactly one structured assessment.

### Persistence

- Assistant message metadata stores the complete structured verdict.
- The durable run and terminal assistant message commit before a portfolio
  signal is written.
- Client cancellation cannot interrupt an already committed run before the
  signal hook finishes.
- Signal rows carry the real chat ID, deterministic message ID, run ID, and
  analysis ID.

## Acceptance Criteria

- [x] Machine decisions no longer depend on regex JSON extraction.
- [x] Tool-capable debate flow retains termination semantics.
- [x] Invalid outputs fail explicitly.
- [x] Final user response remains Markdown.
- [x] Persisted action and displayed action cannot disagree.
- [x] Structured verdict survives chat persistence and reload API.
- [x] Multi-round concerns and rebuttals cannot collide by ID.
- [x] Verdict assessments cover the exact debated concern set.
- [x] Signal persistence cannot precede durable chat completion.
- [x] Repeated signal persistence uses one atomic deterministic order.
- [x] Full backend/frontend validation and Playwright pass.

## Validation

- Focused backend regression suite: 151 tests passed.
- Full backend suite: 1,896 tests passed.
- Frontend unit suite: 232 tests passed.
- Changed backend source files pass isolated Ruff and mypy checks.
- Full-repository mypy retains pre-existing debt outside this feature.
- Real Chromium Prompt Governance flow passed after the final lifecycle and
  persistence review fixes.

## Evidence

```text
docs/features/assets/prompt-governance/
  01-chat-prompt-versions.png
  02-portfolio-flow-completed.png
```
