---
title: Evaluation Governance
status: shipped
version: backend@0.50.0, frontend@0.31.0
last_updated: 2026-08-03
owner: maintainer
related_paths:
  - backend/src/evals/
  - backend/scripts/run_agent_eval.py
  - backend/src/api/evaluations.py
  - frontend/src/pages/EvaluationPage.tsx
  - frontend/e2e/evaluation-governance.spec.ts
---

# Evaluation Governance

## Scope

Extend the deterministic Agent Evaluation Framework with:

- a versioned v2 suite containing explicit Prompt Injection symbol-override
  cases;
- executable quality, execution-mode, symbol-safety, injection-safety,
  latency, cost-policy, and no-live-model gates;
- exact prompt-version and model-route snapshots;
- baseline comparison reports with case regression detection;
- a local browser page that runs and renders the same backend suite.

Portfolio outcome calibration and the Decision Tracker evaluation dashboard are
explicitly out of scope for this delivery slice.

## Contracts

- v1 remains loadable with 70 historical cases.
- v2 contains 80 cases, including 10 bilingual Prompt Injection cases that
  attempt to override or invent symbol context.
- deterministic evaluation never constructs a live router model.
- every gate records observed value, operator, threshold, and pass/fail.
- baseline comparison retains metric deltas, prompt/model changes, regressed
  case IDs, and improved case IDs.
- CLI exits non-zero for current gate failures or baseline regressions.

## Risks

- runtime latency measurements must use generous deterministic budgets so
  machine variance does not create flaky gates;
- old JSON reports must remain loadable after schema expansion;
- prompt/model metadata must describe evaluated configuration, not imply that
  live inference occurred;
- a passing aggregate threshold must not hide case-level failures.

## Test Plan

- v1 and v2 suite count/schema tests;
- deterministic no-live-model execution;
- all quality, latency, cost, and security gates;
- synthetic case regression comparison;
- legacy report loading and Markdown/JSON rendering;
- API response and frontend type-check/lint;
- Playwright run from the Evaluation tab with curated screenshot evidence.

## Acceptance Criteria

- [x] v1 remains 70 cases and v2 contains 80 cases.
- [x] Ten bilingual Prompt Injection cases execute without symbol invention
      or override.
- [x] Quality, latency, cost, and safety gates are structured and executable.
- [x] Reports include prompt versions and model routes.
- [x] Baseline comparison detects case and metric regressions.
- [x] Legacy JSON reports remain loadable.
- [x] The local Evaluation page runs suite v2 and renders gate evidence.
- [x] Playwright passes and screenshots are stored under
      `docs/features/assets/evaluation-governance/`.

## Delivery

Shipped in implementation commit `2540bbf`, backend `0.50.0`, and frontend
`0.31.0`. Suite v2 passes all 80 cases with no live model calls.
