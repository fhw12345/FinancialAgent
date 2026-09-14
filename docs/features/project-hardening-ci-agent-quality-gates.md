---
title: CI Agent Quality and Browser Gates
status: shipped
version: backend@0.51.5, frontend@0.32.5
last_updated: 2026-09-14
owner: maintainer
related_paths:
  - .github/workflows/pr-checks.yml
  - backend/requirements-ci.lock
  - scripts/ci-negative-control.py
  - scripts/run-ci-browser.sh
  - scripts/check-repository-policy.py
  - docker-compose.hardening.yml
  - docker-compose.hardening-images.yml
  - .gitleaks.toml
---

# PH-004: CI Agent Quality and Browser Gates

## Scope and Contract

PRs targeting main execute one required `Unit Tests` job. A failing command fails
the job; no quality gate uses `continue-on-error`. Main requires this check from
GitHub Actions app **15368**, with strict up-to-date checks and administrator
enforcement. No reviewer requirement is added to this single-maintainer repository.

The job enforces:

- actionlint, rendered loopback bindings (all profiles), negative policy fixtures;
- changed-source 500-line limit and version/lock consistency against the PR base,
  not just `HEAD~1` (documentation-only commits need no additional runtime bump);
- Gitleaks on the committed tree and PR commit range;
- locked Python runtime/CI tools, no-build-isolation editable install, `pip check`;
- locked frontend dependencies on the **native runner**, never npm ci in Docker;
- Bandit medium-or-higher severity/confidence, Ruff, Black and strict mypy;
- backend tests and critical per-module coverage floors;
- deterministic Agent evaluation with zero live model calls;
- frontend tests, zero-warning production lint, the 131-warning test/E2E ceiling,
  TypeScript and build;
- real-API deterministic Playwright for routing, buffered output, replay
  deduplication, configured Prompt metadata, Health/version consistency, Markdown
  security and shared Insights prefetch/calculation/persistence.

PR updates cancel superseded runs. The job and server-readiness loops are bounded.
Reports, server logs, traces, videos and failure screenshots upload even on failure
and are retained for **14 days**. Raw reports stay uncommitted; curated screenshots
and verification receipts are committed separately.

Live-provider and restart-heavy suites remain manual/opt-in with explicit budgets.
The 131 warnings are a non-increasing follow-up budget, not a weakened production
lint gate. Repository-wide legacy source decomposition remains PH-009.

## Implementation and Merge

- Runtime/contract implementation: `db1e4b8739c21fb160e6eadda65dab53617522aa`.
- Initial evidence commit: `a115fd23dceaea5dae71f78ed7a612896197fd57`.
- Hosted-run compatibility and probes: `1e78a4a0e684604dd7467938905fe29d83dfa37e`.
- [PR #1](https://github.com/fhw12345/FinancialAgent/pull/1) merged through the normal
  required-check path on 2026-09-14, merge `7cc3789b291cfb71865d3cb7a368a965957db5ca`.
  No administrator bypass was used.

The first hosted run exposed a Compose-version difference: the runner required the
service env file to exist despite `--no-env-resolution`, while local Compose 5.2
accepted its absence. CI creates an **empty ignored placeholder**, solely for
port-contract rendering. It neither copies secrets nor alters local runtime config.

Initial Bandit findings were repaired, not suppressed: SEC XML uses pinned
`defusedxml` with DTD/entity rejection; SHA1 cache keys declare non-security use
without changing their values. Gitleaks exceptions require a specific rule, fixture
path and exact known synthetic value; a negative control proves another token in
the same file is still detected.

## Hosted Evidence

[Curated hosted receipts](assets/ph-004/hosted-ci-validation.json) record run/head
identities, artifact IDs/expiry, verified file hashes and protection settings.

| Scenario | Hosted run | Result |
| --- | --- | --- |
| Initial real PR failure | [34818319625](https://github.com/fhw12345/FinancialAgent/actions/runs/34818319625) | Missing env file; PR observed BLOCKED after required-check protection enabled |
| Normal PR, restored after probes | [34819419375, attempt 2](https://github.com/fhw12345/FinancialAgent/actions/runs/34819419375) | Every declared gate passed; PR CLEAN/MERGEABLE |
| Intentional mypy failure | [34819876537](https://github.com/fhw12345/FinancialAgent/actions/runs/34819876537) | Failed at real mypy command; JUnit failure preserved |
| Intentional eval failure | [34819884649](https://github.com/fhw12345/FinancialAgent/actions/runs/34819884649) | Real eval CLI exited 1; JSON/Markdown show failed router threshold |
| Intentional browser failure | [34819891538](https://github.com/fhw12345/FinancialAgent/actions/runs/34819891538) | Six normal cases passed, deliberate seventh failed; trace/video/screenshot/HTML and logs preserved |

The normal and probe runs tested head `1e78a4a0e684604dd7467938905fe29d83dfa37e`.
The positive eval artifact correctly records the PR **merge ref** as its declared
build revision; dispatch probes record the branch SHA.

**Evidence boundary:** probes are explicit `workflow_dispatch` failure-exit and
artifact controls. They are not regular PR checks and do not make a green PR red.
Actual PR failure blocking was separately observed on the initial failed required
check. All probes invoke the same blocking commands; ordinary PRs always select
`none`, and the probe CLI refuses activation under a pull-request event.

The restored normal hosted run verified:

```text
Backend: 2,014 passed; 27 live integrations deselected
mypy: zero errors in 279 source files
Critical coverage floors / Ruff / Black / Bandit / Gitleaks: passed
Frontend: 254 passed; production warnings 0; total test/E2E warnings 131
TypeScript / frontend build / deterministic eval: passed
Real-API Playwright: 6 passed
Report upload: passed, downloaded and inspected
```

## Clean Builds and Browser Proof

Two clean `docker compose build --no-cache backend frontend` builds have matching
**complete installed** dependency manifests, not just matching top-level lock names.
Each installed frontend package version was checked against its real package file;
frontend production assets were built independently inside both images.

[Clean-build receipts](assets/ph-004/clean-build-validation.json):

| Manifest | Count | SHA256 (identical in both builds) |
| --- | ---: | --- |
| Backend distributions including app/pip | 120 | `87f739ccd6d8192e9bdd68170ee9a10185b7d54710e590a66735b46de93de974` |
| Frontend installed package paths | 746 | `18efc4df1ef5ba048bc9ca2aea121864f0e5513dd1a2038cfed3f73e83a3420b` |
| Frontend asset file-hash manifest | — | `eb491ba8a47308ff251925904e005ab6bbeef3de0f4d78a33a7e867930706b8d` |

Final runtime images:

- backend: `sha256:c39f3833b13d0ae1136558fe71a6b8b91593b474ebc26152a1b539c4204f5c61`;
- frontend: `sha256:70e372189cd7db1747fa0d770284cda6bcb2a9aef82063ac2ca8773d7fda61e5`.

Both were healthy, UID 1000 and free of app-local env files. Backend mounted only
test fixtures; frontend mounted neither application source nor dependencies.
Six fresh-image smoke cases and eleven default E2E regressions passed.
The later CI-only repair did not change these application image inputs.

[Curated PH-004 screenshot](assets/ph-004/01-ci-e2e-smoke-pass.png) shows a real
browser-triggered deterministic eval result and configured Prompt versions, not
fictional model usage. The no-model lane correctly shows no actually-used prompts.

## Reproduction

Docker Desktop must be ready before starting services. Reuse existing images and
dependencies; no npm installation inside containers is needed:

```bash
docker compose -f docker-compose.hardening.yml up -d --no-build mongodb redis llm backend frontend
# Confirm 127.0.0.1:18091/api/health and 127.0.0.1:3011 are ready.
UPDATE_E2E_EVIDENCE=true docker compose -f docker-compose.hardening.yml run --rm --no-deps browser
```

Add `-f docker-compose.hardening-images.yml` after the base file for image-only
acceptance. Native CI uses the same `tests.e2e.hardening_app` and `test:e2e:ci`
selection through `scripts/run-ci-browser.sh`. On Git Bash, use
`MSYS_NO_PATHCONV=1` for absolute container paths.

To verify intentional failures without modifying committed application source:

```bash
gh workflow run pr-checks.yml --ref <branch> -f probe=mypy
gh workflow run pr-checks.yml --ref <branch> -f probe=eval
gh workflow run pr-checks.yml --ref <branch> -f probe=playwright
```

## Acceptance Criteria

- [x] Real PR CI executes all declared fast gates.
- [x] Agent eval failure in a PR fails the required check, blocks merge and preserves reports.
- [x] Playwright failure in a PR fails the required check, blocks merge and preserves trace artifacts.
- [x] The required job blocks a failing PR, including for administrators.
- [x] Live tests remain opt-in and cost-bounded.
- [x] Local/CI use the same deterministic fixture and smoke selection.
- [x] No ignored failures turn a gate green.
- [x] Screenshot, build, hosted run and artifact evidence are recorded.

## Remaining Follow-ups

- PH-009 must remove legacy oversized production files; changed files are already
  gated without a legacy exemption.
- Test/E2E lint debt remains capped at 131. Dependency audit debt and upgrading
  Node/action runtime versions are separate follow-ups. Hosted runs reported the
  old action majors' Node 20 deprecation notice but completed all gates successfully.
- CI artifact links expire after retention; committed hashes/receipts and executable
  probes preserve the verification record without committing raw traces.
