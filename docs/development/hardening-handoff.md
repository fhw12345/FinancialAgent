---
title: Project Hardening Active Handoff
status: in-progress
version: backend@0.51.5, frontend@0.32.5
last_updated: 2026-09-14
owner: maintainer
related_paths:
  - docs/features/project-hardening-program.md
  - docs/features/project-hardening-ci-agent-quality-gates.md
  - .github/workflows/pr-checks.yml
  - docker-compose.hardening.yml
  - docker-compose.hardening-images.yml
---

# Project Hardening Active Handoff

## 1. Current State

PH-001/002/004/005/010 have completed local acceptance, clean-image browser proof,
hosted PR validation, negative-gate/artifact verification and protected implementation
merge. The program remains **in-progress** because PH-009 has not started.

```text
published backend: 0.51.5
published frontend: 0.32.5
implementation PR: #1 (merged 2026-09-14)
implementation merge: 7cc3789b291cfb71865d3cb7a368a965957db5ca
shipment documentation: follows the implementation through a required-check PR
```

Always inspect `git status --short --branch` and fetch before resuming. Do not
assume the historical handoff HEAD is the current branch tip. GitHub CLI is now
authenticated through the system keyring; the prior login blocker is resolved.

## 2. Implementation and Evidence

| Work | Implementation | Evidence / merge |
| --- | --- | --- |
| PH-003 Backend strict types | `6344fd4` | `3ed53b9` |
| PH-006 Frontend typed boundaries | `1a35c1b` | `5fcbec6` |
| PH-007 Agent composition coverage | `54252dc` | `3521746` |
| PH-008 Reproducible builds | `4742bc8` | `ddf4284` |
| PH-001/002/005/010 closeout + PH-004 gates | `db1e4b8739c21fb160e6eadda65dab53617522aa` | `a115fd2`, then PR #1 merge `7cc3789b` |
| Hosted runner compatibility + negative controls | `1e78a4a0e684604dd7467938905fe29d83dfa37e` | PR #1 / hosted receipts |

Earlier foundation: `960d29a`, `34c4be0`, and deterministic/real-stack smoke
isolation `1d2615e` / `8583b4f`.

### Local/runtime acceptance

- Backend: **2,014 passed**, 27 live integrations deselected; Ruff, Black and
  mypy (279 source files) pass. Aggregate coverage rounds to 71%; all critical
  module floors pass.
- Frontend: **254 passed**, production ESLint zero warnings, test/E2E budget
  unchanged at **131**, TypeScript and production build pass.
- Deterministic eval passes without live model calls.
- Two clean builds have identical complete installed dependency manifests and
  frontend asset hashes. Backend: 120 distributions including app/pip; frontend:
  746 installed package paths. Both runtime users have UID 1000.
- Final image-only acceptance: **6 smoke cases and 11 default E2E cases passed**.
  Backend mounts only test fixtures; frontend mounts no source or dependencies.
- Curated screenshots are committed under PH-001/002/004/005/010 assets.

[Clean-build receipts](../features/assets/ph-004/clean-build-validation.json)
record the immutable image IDs. App inputs did not change in the later CI-only fix.

### Important defects fixed

- PH-002 UI refresh now invokes snapshot creation and consumes request-local
  full-history/basket/Treasury/news/IPO inputs. It does not mutate singleton
  category providers or purge all provider TTLs. Persistence failures are explicit;
  public degradation metadata never contains raw provider credentials/URLs.
- Real Redis dedup orchestration exposed duplicate provider calls after failure.
  Callback outcomes are retained; only pre-fetch cache transport failures permit
  fallback. Unconfigured optional Redis still allows a direct fetch.
- PH-005 rejects Markdown images as well as raw HTML and repairs fenced-code
  text/background contrast. The narrow renderer extraction keeps ChatMessages
  at 406 lines; it is not the PH-009 decomposition program.
- PH-010 records evaluation provenance at execution start and carries it through
  initial/progress/final/failure/budget reports. Old reports remain unknown.
- Bandit findings were fixed using pinned defusedxml/DTD rejection and explicit
  non-security SHA1 caching; no production rule suppression was added.

## 3. Hosted CI and Merge Enforcement

[PR #1](https://github.com/fhw12345/FinancialAgent/pull/1) merged normally; no admin
bypass was used. Main requires `Unit Tests` from GitHub Actions app **15368**, with
strict up-to-date checks and administrator enforcement. No reviewer requirement
was added to the single-user repository.

| Scenario | Run | Result |
| --- | --- | --- |
| Initial PR run | `34818319625` | Failed on missing env file; PR observed BLOCKED under required-check protection |
| Restored normal PR, attempt 2 | `34819419375` | All gates passed, CLEAN/MERGEABLE before merge |
| mypy negative control | `34819876537` | Expected real mypy failure; JUnit retained |
| eval negative control | `34819884649` | Expected CLI failure; JSON/Markdown retained |
| Playwright negative control | `34819891538` | Six normal tests passed, deliberate seventh failed; trace/video/screenshot/HTML and logs retained |

[Hosted receipts](../features/assets/ph-004/hosted-ci-validation.json) contain run
URLs/head hashes, artifact IDs/expiry and verified file hashes. Raw downloads remain
ignored under `backend/artifacts/hosted-ci/`; do not commit them.

Negative controls are explicit `workflow_dispatch` probes, not regular PR checks.
They verify failure exits/artifacts using the real commands without modifying
committed application source. Actual PR merge blocking was separately verified
on the initial failing PR. Normal PRs always use probe `none`.

The runner's Compose required env-file existence despite `--no-env-resolution`;
local Compose 5.2 did not. CI uses an empty ignored placeholder for port rendering,
never local secrets. Do not remove this compatibility setup based only on a local
config run. The 131 lint warnings are accepted non-increasing follow-up debt.

## 4. Hardening Status

| Task | Status |
| --- | --- |
| PH-001 Local network perimeter | shipped |
| PH-002 Insights shared prefetch | shipped |
| PH-003 Backend types | shipped |
| PH-004 CI quality/browser gates | shipped |
| PH-005 Markdown safety | shipped |
| PH-006 Frontend quality | shipped |
| PH-007 Composition coverage | shipped |
| PH-008 Reproducible builds | shipped |
| PH-009 Source decomposition | planning |
| PH-010 Version metadata | shipped |

## 5. Next Work — PH-009 Only

The integrated build/CI baseline is accepted. Read the PH-009 spec before beginning.
Prioritize:

```text
backend/src/services/data_manager/manager.py
backend/src/agent/langgraph_react_agent.py
backend/src/services/insights/categories/ai_sector_risk.py
backend/src/agent/portfolio/flows.py
frontend/src/components/portfolio/DecisionTracker.tsx
frontend/src/components/EnhancedChatInterface.tsx
frontend/src/components/chat/useAnalysis.ts
```

Use mechanical extraction commits and `git diff --color-moved`. Put behavioral
fixes in separate test-first changes. Preserve the PH-007 critical coverage floors,
full types/lint/test gates, all required browser scenarios and screenshot evidence.
Do not solve file-length failures with legacy exemptions.

## 6. Operational Notes

- Local single-user app only; no broker execution, cloud deployment or billing.
- `docker desktop start`, then `docker info`, before starting services. A failed
  `docker compose up` must stop the sequence; never endlessly poll a missing server.
- Frontend validation reuses images/dependency volumes. Never npm ci in containers
  or Docker builds. CI's npm ci runs on the native GitHub runner.
- `.env*` changes require `docker compose up -d --force-recreate <service>`.
- `docker-compose.hardening.yml` isolates key-free fixture ports `3011/18091`.
  Layer `docker-compose.hardening-images.yml` for image-only acceptance. Switch
  back to the base profile or rebuild before expecting source edits to be served.
- `scripts/run-ci-browser.sh` starts native CI servers with bounded readiness and
  cleanup, using the same fixture/test selection as local Docker.
- Git Bash: use `MSYS_NO_PATHCONV=1` with absolute Linux container paths. The
  host Azure CLI bundles Python for stdlib/Git policy scripts; backend gates run
  on Python 3.12. Linux Git scanning a Windows mount may time out.
- `ph-quality` is a disposable tooling container, not an API runtime. Its inherited
  API healthcheck is not meaningful while it runs only a validation command.
- Raw logs/reports/traces/videos stay ignored; curated screenshots and receipts
  are captured after assertions and committed.
- Branch protection means future code/docs updates go through a passing PR;
  do not bypass it to make shipment bookkeeping easier.
