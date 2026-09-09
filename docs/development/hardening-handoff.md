---
title: Project Hardening Active Handoff
status: in-progress
version: backend@0.51.5, frontend@0.32.5
last_updated: 2026-09-09
owner: maintainer
related_paths:
  - docs/features/project-hardening-program.md
  - .github/workflows/pr-checks.yml
  - backend/src/agent/
  - frontend/src/
---

# Project Hardening Active Handoff

## 1. Goal

Continue the repository-wide hardening program without losing lifecycle,
testing, documentation, and shipment context after Pi compaction. The program
is not complete and must remain `in-progress` until the remaining build,
source-decomposition, and CI evidence tasks meet their browser and documentation
requirements.

## 2. Repository State at Handoff

```text
branch: hardening/closeout-ci
base main / origin/main: ddf4284 docs(build): ship PH-008 reproducible builds
implementation: db1e4b8739c21fb160e6eadda65dab53617522aa (pushed)
evidence: documentation commit following implementation; verify git status on resume
last published: backend 0.51.4 / frontend 0.32.4
pending versions: backend 0.51.5 / frontend 0.32.5
```

Latest implementation/documentation pairs:

| Task | Implementation | Documentation | Status |
| --- | --- | --- | --- |
| PH-003 Backend strict types | `6344fd4` | `3ed53b9` | shipped |
| PH-006 Frontend typed boundaries | `1a35c1b` | `5fcbec6` | shipped |
| PH-007 Agent composition coverage | `54252dc` | `3521746` | shipped |
| PH-008 Reproducible builds | `4742bc8` | `ddf4284` | shipped |

Earlier hardening foundation:

- `960d29a` — loopback ports, Insights prefetch contract, Markdown safety,
  authoritative versions, build-lock foundation;
- `34c4be0` — initial hardening specs and browser evidence;
- `1d2615e` / `8583b4f` — deterministic versus real-stack browser smoke
  isolation and documentation.

## 3. Completed Work

### PH-003 — Backend Type Safety

- strict mypy reduced from 297 errors in 81 files to zero across 275 source
  files;
- Pydantic plugin enabled;
- provider/cache shapes, heterogeneous gather results, Optional services,
  repository contracts, and Portfolio mixin dependencies repaired;
- blocking mypy runs in PR CI;
- backend `0.51.2`, status `shipped`.

### PH-006 — Frontend Runtime Boundaries

- production API/SSE boundaries contain no explicit `any`;
- unknown JSON is validated before dispatch;
- malformed optional SSE events are ignored without corrupting later stream
  state;
- production ESLint is zero-warning;
- isolated test/E2E warning debt is capped at 131 and cannot increase;
- accessibility, Hook dependency, chart metadata, Portfolio error, and typed
  dictionary issues repaired;
- frontend `0.32.3`, status `shipped`.

### PH-007 — Agent Orchestration Composition Coverage

Four composition suites were added:

- `backend/tests/test_react_agent_composition.py`;
- `backend/tests/test_portfolio_flow_composition.py`;
- `backend/tests/test_order_optimizer_composition.py`;
- `backend/tests/test_data_manager_provider_composition.py`.

They exercise real internal orchestration and fake only model/provider/storage
transports. Two production defects were found and fixed:

1. ReAct retained a transient exception and re-raised it after a successful
   retry; success now clears stale failure state.
2. Phase 2 failure-history messages used invalid `source="system"`; they now use
   the valid assistant source `llm`.

Critical coverage floors now enforced by
`scripts/check-critical-coverage.py`:

| Module | Current | Floor |
| --- | ---: | ---: |
| ReAct orchestration | 60.05% | 60% |
| Portfolio flows | 64.58% | 55% |
| Phase 1 | 74.66% | 65% |
| Phase 2 | 69.77% | 65% |
| Phase 3 | 77.78% | 65% |
| Plan builder | 88.64% | 60% |
| Suggestion executor | 95.92% | 60% |
| DataManager | 71.11% | 70% |

Final PH-007 validation:

```text
backend tests: 1,985 passed
live integration tests: 27 deselected
aggregate backend coverage: 69%
Ruff: passed
Black: passed
mypy: zero errors
Agent deterministic evaluation: passed
Portfolio Playwright: passed
UAW-005 cancellation/reload Playwright: passed
```

Curated evidence:

- `docs/features/assets/ph-007/01-portfolio-decision-after-reload.png`;
- `docs/features/assets/ph-007/02-agent-cancelled-terminal-state.png`.

### 2026-09-09 — Unpublished Closeout / CI Work

Docker Desktop was started with `docker desktop start` and the engine is ready.
Do not repeat curl waits after failed Compose startup. A dedicated
`docker-compose.hardening.yml` stack now reuses existing images without npm
installs, and binds frontend/backend to `3011/18091`. The backend mounts source,
tests and package metadata only, not local env files.

Candidate implementation:

- PH-001: rendered-Compose checker (all profiles, long syntax, no env resolution),
  negative controls, live publishers, real Health screenshot and remote-access docs;
- PH-005: test-first fix for remote Markdown images; narrow renderer extraction
  keeps ChatMessages at 406 lines; expanded corpus, fenced-code contrast repair,
  and browser screenshot;
- PH-010: source/installed/fallback tests, root/Health/OpenAPI checker and real
  metadata screenshot; eval provenance now survives initial/progress/final/failure
  and budget-exhausted reports. Historical reports remain explicitly unknown;
- PH-002: visible refresh now executes snapshot prefetch and consumes the exact
  full-history/basket/Treasury/news/IPO inputs through a request-local provider view.
  Real Redis dedup tests found and fixed re-fetching after provider failure.
  The screenshot now comes from real API/calculation/Mongo/Redis execution;
- PH-004: pinned CI tools, concurrency cancellation, read-only permissions,
  explicit tests, policy/security gates, bounded native browser launcher, same
  deterministic browser selection locally/CI, and 14-day failure artifacts.

Validation: backend 2,014 tests / 27 deselected, Ruff/Black/mypy (279 source files)
and critical floors passed; aggregate coverage rounds to 71%. Frontend 254 tests,
production lint zero, total warnings 131, TypeScript and build passed. Deterministic
eval passed; final fresh-image Playwright 6 passed and default Playwright 11 passed.
Gitleaks passed with narrowly-scoped synthetic sanitizer exceptions and a negative
control. Bandit is green: SEC XML now uses pinned defusedxml with DTD/entity
rejection, and SHA1 cache hashing explicitly declares non-security use. Actionlint,
policy unit tests and changed-source/version checks pass. No security rules were
suppressed for the production fixes.

Two final clean builds compare full installed manifests: 120 backend distributions,
746 frontend package paths, plus identical frontend production-asset hashes.
Receipts: `docs/features/assets/ph-004/clean-build-validation.json`.
The final image-only browser run mounts no application source/dependency paths;
backend mounts only `/app/tests`, frontend mounts nothing. Both images are healthy,
UID 1000, and exclude app-local env files.

Remaining blocker: `gh auth status` has no login and no reusable GitHub API
credential was available. The implementation branch push succeeded, but
`gh pr create` exited 4 asking for login; Git transport and gh API authorization
must be treated separately. A real PR run, negative-gate/failure-
artifact checks, branch-protection proof and final shipment still cannot be claimed.

Implementation hash: `db1e4b8739c21fb160e6eadda65dab53617522aa`.

Next actions after `gh auth login`: push any final evidence commit, create the PR
from `hardening/closeout-ci` to `main`, monitor all gates, verify failure artifacts
and required checks, then perform the final shipment/merge status updates. A
branch push alone is not a passed CI run or a shipped feature.
All five tasks remain `in-progress`; committed screenshots are under
`docs/features/assets/ph-001`, `ph-002`, `ph-004`, `ph-005`, `ph-010`. Raw reports
remain ignored under backend artifacts and frontend Playwright output.
The isolated hardening stack is still available on `3011/18091` with the image-only
override active (source edits need rebuilding or switching back to the base profile).
`ph-quality`
is a disposable validator container with the locked CI tools. The host's Azure CLI
installation includes Python 3.13 for stdlib/Git policy scripts; backend gates
were run with Python 3.12 inside the validator. No global Python/npm install or
Git credential storage was changed.
See the [case study](../case-studies/2026-09-09-closeout-checklists-are-not-evidence.md).

## 4. Hardening Status Matrix

Formal document status at handoff:

| Task | Status | Actual state / blocker |
| --- | --- | --- |
| PH-001 Loopback perimeter | in-progress | Code, contract check, real-stack E2E and screenshot exist; formal closeout remains |
| PH-002 Insights prefetch | in-progress | Real refresh/prefetch/calculation/persistence, dedup failure handling and fresh-image browser proof pass; publication pending |
| PH-003 Backend types | shipped | Complete |
| PH-004 CI gates | in-progress | Full local gates and fresh-image smoke pass; missing GitHub authorization/hosted evidence blocks shipment |
| PH-005 Markdown safety | in-progress | Raw HTML removed, component/browser security proof exists; formal closeout remains |
| PH-006 Frontend quality | shipped | Complete |
| PH-007 Composition coverage | shipped | Complete |
| PH-008 Reproducible builds | shipped | Lock-preserving mirrors, semantic package-lock verification, non-root runtime users, two clean builds, healthy fresh images, browser proof, screenshot, versions, changelogs, and shipment docs complete |
| PH-009 Source decomposition | planning | Start only after PH-008 or an explicit integration decision |
| PH-010 Version metadata | in-progress | Real endpoint/UI and evaluation provenance (including legacy compatibility) verified; publication pending |

The formal shipped count understates implemented work because PH-001, PH-002,
PH-005, and PH-010 have implementation and evidence but were deliberately not
marked shipped before their final closeout review.

## 5. Recommended Next Sequence

### Step 1 — Formal Closeout Review

PH-008 shipped at backend `0.51.4` / frontend `0.32.4` in implementation commit
`4742bc8` with documentation shipment evidence. The prior package-registry TLS
blocker was resolved using lock-preserving transport mirrors, semantic
`package-lock.json` verification, and final fresh-image Playwright evidence at
`docs/features/assets/ph-008/01-clean-build-runtime.png`.

Review PH-001, PH-002, PH-005, and PH-010 against their checklists. If every
listed assertion and screenshot is still valid on current `main`, change each
to `shipped` in a documentation shipment commit. Do not silently mark them
shipped if current clean-image or integrated-browser evidence has regressed.

### Step 2 — Finish PH-004 CI Evidence

Remaining work:

- confirm a real GitHub Actions PR run executes every declared gate;
- retain failure artifacts for eval and Playwright;
- decide whether the 131 test/E2E warnings are a follow-up budget or must be
  reduced further before PH-004 shipment;
- add concurrency cancellation and any still-missing security hooks;
- record CI run URL/hash and curated screenshot in PH-004.

### Step 3 — PH-009 Source Decomposition

Only start after the integrated build/CI baseline is accepted. PH-007 is now the
behavioral freeze that protects this refactor.

Priority oversized production files:

```text
backend/src/services/data_manager/manager.py
backend/src/agent/langgraph_react_agent.py
backend/src/services/insights/categories/ai_sector_risk.py
backend/src/agent/portfolio/flows.py
frontend/src/components/portfolio/DecisionTracker.tsx
frontend/src/components/EnhancedChatInterface.tsx
frontend/src/components/chat/useAnalysis.ts
```

Keep extraction commits mechanical. Run `git diff --color-moved`; put any
behavior fix in a separate test-first commit.

## 6. Required Validation Commands

Backend:

```bash
docker compose run --rm --no-deps backend python -m ruff check src/
docker compose run --rm --no-deps backend python -m black --check src/
docker compose run --rm --no-deps backend python -m mypy src/
docker compose run --rm --no-deps backend python -m pytest tests/ -q \
  --cov-report=json:coverage.json
python scripts/check-critical-coverage.py
```

When running from Git Bash without host Python, inspect `backend/coverage.json`
with Node or run the Python script in an environment where repository root and
`backend/coverage.json` are mounted consistently. A prior ad-hoc Docker command
failed because MSYS rewrote `/repo` to `C:/Program Files/Git/repo`; this was a
host path-conversion issue, not a coverage failure.

Frontend:

```bash
docker compose exec -T frontend npm run test -- --run
docker compose exec -T frontend npm run lint:production
docker compose exec -T frontend npm run lint -- --max-warnings 131
docker compose exec -T frontend npm run type-check
docker compose exec -T frontend npm run build
```

Agent/browser:

```bash
make eval
make test-e2e
```

Use task-specific Compose profiles for UAW scenarios. Do not run UAW-005 against
the generic events backend; it requires the cancellation fixture on ports
`3004/18085`. Wait for backend Health before opening the browser. A prior UAW-004
attempt failed because Playwright started while the dedicated backend was still
initializing; the readiness-confirmed rerun passed.

## 7. Operational Constraints

- Local single-user application only; no broker execution.
- Never commit secrets or `backend/.env.development`.
- After `.env*` changes use `docker compose up -d --force-recreate <service>`;
  restart alone does not reload environment variables.
- Raw Playwright reports/traces/videos stay uncommitted.
- Curated screenshots are captured only after assertions.
- Feature shipment requires implementation commit, browser evidence where
  applicable, version bump, changelog, roadmap/index updates, bilingual case
  study, documentation commit containing implementation hash, and push sync.
- Existing source max is 500 lines; PH-009 must fix legacy violations rather
  than exempting them.

## 8. Pi Compaction Configuration

Global Pi settings were updated outside the repository at:

```text
C:/Users/haowenfeng/.pi/agent/settings.json
```

Current model metadata:

```text
model: github-copilot/gpt-5.6-sol
context window: 1,050,000
```

Configured policy:

```json
{
  "compaction": {
    "enabled": true,
    "reserveTokens": 210000,
    "keepRecentTokens": 20000
  }
}
```

Pi triggers when:

```text
contextTokens > 1,050,000 - 210,000 = 840,000 tokens = 80%
```

The full session remains in JSONL and can be revisited through `/tree`.

## 9. First Actions After Compaction

1. Read this handoff completely.
2. Run `git status --short --branch`; the continuation is on
   `hardening/closeout-ci`, based on main/origin/main `ddf4284`. Preserve the
   implementation and evidence; do not reset it to the published base.
3. Local closeout checks and clean-image evidence are complete. Restore gh API
   authorization, create the PR from `hardening/closeout-ci`, and obtain hosted
   evidence rather than repeating the original investigation.
4. Monitor every declared gate, verify negative-gate/failure artifacts and required
   checks, then merge/publish and update statuses. No additional task from this
   continuation is shipped yet.
5. Start PH-009 only after the integrated build/CI baseline is accepted.
