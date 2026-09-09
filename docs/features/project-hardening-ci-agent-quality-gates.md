---
title: CI Agent Quality and Browser Gates
status: in-progress
version: backend@0.51.5, frontend@0.32.5
last_updated: 2026-09-09
owner: maintainer
related_paths:
  - .github/workflows/pr-checks.yml
  - Makefile
  - backend/scripts/run_agent_eval.py
  - frontend/playwright.config.ts
  - docker-compose.hardening.yml
  - docker-compose.hardening-images.yml
  - backend/requirements-ci.lock
  - .gitleaks.toml
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

## 2026-09-09 Continuation Plan

- Keep `in-progress` until a real PR run URL, failure artifacts, and publication
  exist. GitHub CLI has no API login; a Git push dry-run succeeded, so transport
  availability is tracked separately from hosted PR authorization.
- Pin CI tooling separately from runtime dependencies; constrain editable
  installs to the production lock instead of re-resolving the runtime graph.
- Add cancellation, least-privilege permissions, bounded readiness/timeouts,
  explicit Vitest run mode, changed-source length/version checks, Gitleaks and
  Bandit. Preserve reports and server logs on failure.
- Exercise routing, buffered streaming, idempotent replay, governed prompt
  metadata, and a real API path using the existing deterministic events fixture.
- Retain the 131 test/E2E warning ceiling as explicit follow-up debt; production
  ESLint stays zero-warning. This is not a reason to weaken any current gate.
- Validate locally with the same smoke selection and save a curated PH-004
  screenshot only after browser assertions. Hosted gate-failure injection and
  branch-protection verification remain required before closeout.

## Implementation Progress

PR workflow now validates loopback bindings, runs deterministic Agent eval,
runs the project-hardening Playwright smoke, enforces zero production warnings
plus the isolated 131-warning test/E2E ceiling, type-checks, builds, and uploads
eval/Playwright reports. PH-003 now
passes strict mypy across all backend source and the PR workflow executes the
same blocking command. This task remains in progress until hosted CI evidence
and publication are complete; the 131-warning test/E2E ceiling is an explicit
non-increasing follow-up budget, not a relaxed production lint gate. PH-007 now enforces
all declared critical orchestration coverage floors through
`scripts/check-critical-coverage.py`.

Local deterministic eval and all four project-hardening Playwright scenarios
passed for implementation commit `960d29a`. CI smoke isolation was corrected in commit `1d2615e`; CI-hosted evidence remains outstanding.

## Current Local Validation — 2026-09-09 (Not Shipped)

Prepared workflow changes are **not** hosted evidence. Tested implementation:
`db1e4b8739c21fb160e6eadda65dab53617522aa`, backend `0.51.5` / frontend `0.32.5`.
The implementation and curated evidence are committed and pushed on
`hardening/closeout-ci`; `gh pr create` still fails because gh has no API login.

| Gate | Local result |
| --- | --- |
| Locked runtime + CI tools, no-build-isolation editable install, pip check | passed (includes `editables==0.5`) |
| Ruff / Black / strict mypy | passed; mypy 279 source files |
| Backend tests / critical coverage | 2,014 passed, 27 live tests deselected; all floors passed |
| Deterministic Agent eval | passed |
| Frontend tests / lint / types / build | 254 passed; 0 production warnings; 131 total warnings; fresh output build passed |
| Policy unit tests / changed-source length / PR-base version check | passed; no last-commit-only version assumption |
| Workflow actionlint / shell syntax | passed |
| Gitleaks current source + exact synthetic-fixture exceptions | passed; negative token in same fixture file correctly blocks |
| Dedicated real-API browser smoke | 6 passed on final images, without app source/dependency mounts |
| Default deterministic E2E regression suite | 11 passed |
| Bandit full production scan, medium+ severity/confidence | passed after tested fixes; no rule suppression added |
| Hosted PR run / failure artifacts / branch protection | **not verified**, no GitHub authorization |

The three initial Bandit findings were fixed, not suppressed:

- SEC parsing now uses `defusedxml==0.7.1` with DTD rejection and preserves
  empty-result handling for malformed/hostile filings. XML/entity controls failed
  before the fix and passed after it. The compatible transport extraction keeps
  the touched parser under 500 lines; this is not the PH-009 program.
- Translation SHA1 explicitly uses `usedforsecurity=False`; a regression proves
  the cache key is unchanged.
- Final review also repaired Redis dedup re-fetching a failed provider callback;
  real Redis orchestration now participates in the PH-002 composition tests.

Gitleaks exceptions are restricted to the `generic-api-key` rule, two sanitizer
fixture paths, and three exact known synthetic values. No entire test directory
or historical findings baseline is excluded. The pinned scanner uses rule-level
AND allowlists; the negative control verifies that a different token in the same
file remains detectable.

### Local replay

Docker Desktop must be ready (`docker desktop start`, then `docker info`). Reuse
existing application images/dependencies; no npm installation is needed:

```bash
docker compose -f docker-compose.hardening.yml up -d --no-build mongodb redis llm backend frontend
# Confirm HTTP readiness at 127.0.0.1:18091/api/health and 127.0.0.1:3011.
UPDATE_E2E_EVIDENCE=true docker compose -f docker-compose.hardening.yml run --rm --no-deps browser
docker compose -f docker-compose.hardening.yml run --rm --no-deps browser npm run test:e2e
```

The isolated stack binds only two application ports, publishes no databases,
and mounts no backend env files. It uses the same `tests.e2e.hardening_app`
and `npm run test:e2e:ci` selection as native CI's `scripts/run-ci-browser.sh`.
Native CI has bounded server readiness and retains server logs. On Windows,
use `MSYS_NO_PATHCONV=1` for absolute Linux container paths. Native host Python
can run the repository Git policy script; Linux Git scanning the Windows bind
mount timed out and was not counted as a passing check.

[Curated PH-004 screenshot](assets/ph-004/01-ci-e2e-smoke-pass.png) shows the real
deterministic evaluation API result and **configured** Prompt versions. The
actual-used Prompt list is correctly empty for the no-model evaluation lane.
Chat dispatch/buffering/replay uses the deterministic events agents with real
API lifecycle and Mongo/Redis persistence. It does not prove live model quality.

There is no CI run URL yet. Restore GitHub authorization (`gh auth login` in the
maintainer terminal), push the prepared branch and run a real PR
including negative-gate/failure-artifact checks, then complete the two-commit
publication workflow. Do not mark this feature shipped before those steps.

### Final clean-build and fresh-image evidence

Two final `docker compose build --no-cache backend frontend` builds passed after
the last production fix. [Curated receipts](assets/ph-004/clean-build-validation.json)
record both immutable IDs and full installed-manifest comparisons:

- backend: 120 installed distributions including the app/pip; matching SHA256
  `87f739ccd6d8192e9bdd68170ee9a10185b7d54710e590a66735b46de93de974`;
- frontend: 746 installed package paths, each checked against its real
  `package.json`; matching SHA256
  `18efc4df1ef5ba048bc9ca2aea121864f0e5513dd1a2038cfed3f73e83a3420b`;
- frontend production assets were built independently inside each image and
  their file-hash manifests match:
  `eb491ba8a47308ff251925904e005ab6bbeef3de0f4d78a33a7e867930706b8d`;
- both image users have UID 1000; no app-local `.env*` files were present.
  Frontend build context now explicitly excludes `.env*`.

Run image-only acceptance with the extra override:

```bash
docker compose -f docker-compose.hardening.yml -f docker-compose.hardening-images.yml up -d --no-build --force-recreate mongodb redis llm backend frontend
# Wait for Health/readiness, and inspect image IDs, mounts and loopback publishers.
UPDATE_E2E_EVIDENCE=true docker compose -f docker-compose.hardening.yml -f docker-compose.hardening-images.yml run --rm --no-deps browser
```

Final backend image: `sha256:c39f3833b13d0ae1136558fe71a6b8b91593b474ebc26152a1b539c4204f5c61`.
Final frontend image: `sha256:70e372189cd7db1747fa0d770284cda6bcb2a9aef82063ac2ca8773d7fda61e5`.
Live inspection confirmed both healthy and non-root. Backend mounts only test
fixtures; frontend mounts nothing. The six smoke cases and eleven default E2E
cases then passed, and PH-001/002/004/005/010 screenshots were refreshed.

## Risks

The full existing E2E matrix is too expensive for every PR. Select scenarios by
risk, not convenience, and run the complete matrix nightly. Avoid GitHub
workflow logic that leaks secrets into forked pull requests.
