---
title: CI Agent Quality and Browser Gates
status: in-progress
version: backend@0.51.1, frontend@0.32.1
last_updated: 2026-08-06
owner: maintainer
related_paths:
  - .github/workflows/pr-checks.yml
  - Makefile
  - backend/scripts/run_agent_eval.py
  - frontend/playwright.config.ts
---

# PH-004: CI Agent Quality and Browser Gates

## Objective

Make pull-request status reflect the repository's documented definition of
done by enforcing type safety, deterministic agent evaluation, security checks,
and a bounded deterministic Playwright suite.

## Gate Contract

Every PR must block on:

- backend unit tests, Ruff, Black, and mypy;
- frontend unit tests, ESLint warning budget, type-check, and build;
- deterministic agent evaluation;
- deterministic Playwright smoke covering routing, streaming, idempotency,
  prompt governance, and one frontend-to-backend path;
- file-length, secret, and security checks appropriate to changed files.

Live-provider and restart-heavy suites run nightly or manually with explicit
budgets; they do not make ordinary PRs nondeterministic.

## Ownership and Dependencies

Agent D owns workflows, Make targets, and CI test selection. It may prepare the
workflow in parallel, but merge after PH-002, PH-003, PH-005, PH-006, and PH-007
make the new gates green. Do not weaken thresholds to force a merge.

## Implementation Plan

1. Split fast deterministic PR jobs from nightly/manual jobs.
2. Use dependency caches without bypassing committed lock metadata.
3. Add mypy and frontend warning budget.
4. Run `run_agent_eval.py` and upload JSON/Markdown reports on failure.
5. Define a tagged Playwright PR smoke project.
6. Upload raw Playwright traces only as CI artifacts, not repository files.
7. Run gitleaks, Bandit, file-length, and version validation in CI.
8. Add concurrency cancellation for superseded PR runs.
9. Document local commands exactly matching CI.

## Test Plan

### Workflow validation

- YAML syntax and action versions validate;
- intentionally failing mypy/eval/E2E fixtures prove each job blocks;
- restored code proves each job returns green;
- report artifacts are available on failure.

### Playwright E2E — required

The CI smoke must execute visible browser scenarios for:

1. automatic route selection;
2. genuine or explicitly labelled buffered streaming;
3. duplicate request-ID replay without duplicate output;
4. governed prompt metadata visible in the UI;
5. one deterministic frontend-to-backend analysis.

Run once locally against the same Docker profile and save
`docs/features/assets/ph-004/01-ci-e2e-smoke-pass.png`, captured from the
user-visible final scenario after assertions. The document must also link the
CI run URL/hash when shipped.

## Acceptance Criteria

- [ ] PR CI runs all declared fast gates.
- [ ] Agent eval failure blocks merge and preserves reports.
- [ ] Playwright failure blocks merge and preserves trace artifacts.
- [ ] Live tests remain opt-in and cost-bounded.
- [ ] Local commands reproduce CI behavior.
- [ ] No gate is marked successful with ignored failures.
- [ ] Screenshot and CI evidence are recorded.

## Implementation Progress

PR workflow now validates loopback bindings, runs deterministic Agent eval,
runs the project-hardening Playwright smoke, enforces the current 435-warning
ceiling, type-checks, builds, and uploads eval/Playwright reports. Mypy is not
yet enabled because PH-003 remains red; therefore this task is not complete and
must not be marked shipped.

Local deterministic eval and all four project-hardening Playwright scenarios
passed for implementation commit `960d29a`. CI-hosted evidence remains outstanding.

## Risks

The full existing E2E matrix is too expensive for every PR. Select scenarios by
risk, not convenience, and run the complete matrix nightly. Avoid GitHub
workflow logic that leaks secrets into forked pull requests.
