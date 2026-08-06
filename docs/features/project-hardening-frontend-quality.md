---
title: Frontend API Boundary and Lint Quality
status: planning
version: frontend@0.32.1
last_updated: 2026-08-06
owner: maintainer
related_paths:
  - frontend/src/services/
  - frontend/src/types/
  - frontend/src/components/chat/useAnalysis.ts
  - frontend/.eslintrc.cjs
---

# PH-006: Frontend API Boundary and Lint Quality

## Objective

Restore lint signal and prevent unvalidated `any` values from flowing from HTTP
and SSE boundaries into chat, chart, portfolio, and insights state.

## Scope and Contract

Priority boundaries:

1. Axios response/error decoding;
2. SSE JSON and canonical agent event envelopes;
3. analysis metadata and chart overlays;
4. portfolio decisions/orders;
5. hook dependency and stale-closure warnings;
6. unsafe regex and accessibility warnings.

External input is `unknown` until validated by a type guard or Zod schema. The
final CI warning budget must be explicit and non-increasing; target zero for
production source, while test-only warnings may be separately budgeted and
removed in follow-up slices.

## Ownership and Parallel Safety

Agent F owns frontend services, shared types, hooks, ESLint policy, and related
tests. Agent E owns Markdown rendering. Avoid editing `ChatMessages.tsx` except
for type imports agreed with Agent E. PH-009 follows after this work.

## Implementation Plan

1. Export runtime validators for API errors and agent events.
2. Replace service return `any` with decoded domain types.
3. Make unknown event types observable but harmless.
4. Type analysis metadata and overlays as discriminated unions.
5. Resolve hook dependency warnings by fixing lifecycle semantics, not disabling
   the rule.
6. Replace the unsafe regex with a bounded parser or safe expression.
7. Fix accessibility warnings on touched interactive components.
8. Introduce `eslint --max-warnings` at the measured post-cleanup baseline and
   make it ratchet downward to zero.

## Test Plan

### Unit and component

- valid and malformed API payloads;
- unknown, duplicate, and out-of-order SSE events;
- Axios non-JSON and network errors;
- cancellation and clarification transitions;
- hook rerender/stale closure behavior;
- safe time parsing with adversarial long strings.

### Playwright E2E — required

Run visible scenarios for:

1. malformed optional SSE event does not crash an active chat;
2. cancellation reaches a stable cancelled state;
3. clarification candidate selection continues the same run;
4. chart overlay renders from a validated analysis payload.

Capture `docs/features/assets/ph-006/01-typed-stream-recovery.png` after the UI
recovers from an ignored malformed optional event and reaches completion.

## Acceptance Criteria

- [ ] API/SSE production boundaries contain no explicit `any`.
- [ ] Malformed payloads cannot corrupt React state.
- [ ] Hook dependency warnings in production source are resolved.
- [ ] Unsafe regex warning is removed with regression tests.
- [ ] ESLint warning budget is enforced and documented.
- [ ] Required browser scenarios and screenshot pass.
- [ ] Unit tests, lint, type-check, and build pass.

## Risks

Overly strict schemas can reject backward-compatible server fields. Validators
should allow documented additive fields while requiring canonical identity,
sequence, type, and payload invariants.
