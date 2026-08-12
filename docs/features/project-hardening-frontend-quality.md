---
title: Frontend API Boundary and Lint Quality
status: shipped
version: frontend@0.32.3
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

- [x] API/SSE production boundaries contain no explicit `any`.
- [x] Malformed payloads cannot corrupt React state.
- [x] Hook dependency warnings in production source are resolved.
- [x] The bounded timestamp regex has a 100,000-character regression test and no production lint warning.
- [x] Production lint enforces zero warnings; test/E2E debt is capped at 131.
- [x] Required browser scenarios and screenshot pass.
- [x] 248 unit tests, lint, type-check, and production build pass.

## Implementation and Test Record

The production lint baseline fell from 435 repository warnings, including 135
in production source, to zero production warnings. Remaining warnings are
isolated to tests and E2E fixtures and are capped at 131 in CI, preventing any
increase. HTTP errors, SSE envelopes, analysis metadata, chart tooltips,
Portfolio API responses, and dynamic dictionaries now cross `unknown` or typed
validators before reaching state. Accessibility fixes added associated labels,
button-backed modal backdrops, keyboard column resizing, and safe focus
behavior.

Validation completed on 2026-08-06:

- 248 frontend unit/component tests passed;
- production ESLint passed with `--max-warnings 0`;
- full test/E2E lint passed at the ratcheted 131-warning ceiling;
- TypeScript and the Vite production build passed;
- malformed SSE recovery, Insights refresh, version diagnostics, and Markdown
  safety passed in the project-hardening browser suite;
- symbol clarification candidate selection passed;
- cancellation persisted through the dedicated UAW-005 stack;
- the synchronized chart-volume overlay passed.

The malformed fixture was ignored, a later valid response reached its asserted
completed UI, and Playwright then captured
[`assets/ph-006/01-typed-stream-recovery.png`](assets/ph-006/01-typed-stream-recovery.png).
The scenario used deterministic network fixtures. Implementation commit:
`1a35c1b`.

## Risks

Overly strict schemas can reject backward-compatible server fields. Validators
should allow documented additive fields while requiring canonical identity,
sequence, type, and payload invariants.
