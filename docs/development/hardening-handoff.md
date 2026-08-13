---
title: Project Hardening Active Handoff
status: in-progress
version: backend@0.51.4, frontend@0.32.4
last_updated: 2026-08-13
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
branch: main
HEAD: 3521746 docs(agent): record orchestration coverage shipment
origin/main: 3521746
working tree: clean
backend: 0.51.3
frontend: 0.32.3
```

Latest implementation/documentation pairs:

| Task | Implementation | Documentation | Status |
| --- | --- | --- | --- |
| PH-003 Backend strict types | `6344fd4` | `3ed53b9` | shipped |
| PH-006 Frontend typed boundaries | `1a35c1b` | `5fcbec6` | shipped |
| PH-007 Agent composition coverage | `54252dc` | `3521746` | shipped |

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

## 4. Hardening Status Matrix

Formal document status at handoff:

| Task | Status | Actual state / blocker |
| --- | --- | --- |
| PH-001 Loopback perimeter | in-progress | Code, contract check, real-stack E2E and screenshot exist; formal closeout remains |
| PH-002 Insights prefetch | in-progress | Contract fix, Python regression and browser evidence exist; formal closeout remains |
| PH-003 Backend types | shipped | Complete |
| PH-004 CI gates | in-progress | mypy, eval, deterministic browser smoke, production lint and critical coverage floors exist; test/E2E warning debt and CI-hosted evidence remain |
| PH-005 Markdown safety | in-progress | Raw HTML removed, component/browser security proof exists; formal closeout remains |
| PH-006 Frontend quality | shipped | Complete |
| PH-007 Composition coverage | shipped | Complete |
| PH-008 Reproducible builds | shipped | Lock-preserving mirrors, semantic package-lock verification, non-root runtime users, two clean builds, healthy fresh images, browser proof, screenshot, versions, changelogs, and shipment docs complete |
| PH-009 Source decomposition | planning | Start only after PH-008 or an explicit integration decision |
| PH-010 Version metadata | in-progress | Runtime/UI metadata and browser proof exist; formal closeout remains |

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

### Step 4 — PH-009 Source Decomposition

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
2. Run `git status --short --branch`; expect clean `main == origin/main`.
3. Start with the formal closeout review for PH-001, PH-002, PH-005, and
   PH-010; do not mark any of them shipped if current browser evidence has
   regressed.
4. Continue PH-004 only after confirming which evidence must come from local
   gates versus GitHub Actions.
5. Start PH-009 only after the integrated build/CI baseline is accepted.
