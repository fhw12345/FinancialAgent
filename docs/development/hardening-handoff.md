---
title: Project Hardening Active Handoff
status: in-progress
version: backend@0.57.0, frontend@0.38.0
last_updated: 2026-09-18
owner: maintainer
related_paths:
  - docs/features/project-hardening-program.md
  - docs/features/investment-decision-quality-program.md
  - docs/features/project-hardening-ci-agent-quality-gates.md
  - .github/workflows/pr-checks.yml
  - docker-compose.hardening.yml
  - docker-compose.hardening-images.yml
---

# Project Hardening Active Handoff

## 1. Current State

### IDQ-005 authorized / in progress (2026-09-18)

Maintainer approved the fundamental pilot: 252 XNYS sessions, SPY total return,
USD US non-financial common equities, conditional peer PE and DCF. Numeric valuation
assumptions/peer rationale/invalidation thresholds remain explicit user inputs;
there is no permission to configure the live account or open ready/approval.
Branch `feat/idq-005-strategy-contracts`, target 0.57.0/0.38.0. Immutable version CAS,
sealed peer inputs, separate Portfolio/Deep stance prompts, typed valuation/monitoring
receipts and explicit UI confirmation are implemented locally. Backend 2217/frontend
272 tests pass with strict gates and new critical floors. Final image-only acceptance
passes 37 cases. Two unchanged-input builds match full manifests/assets/source trees;
strategy/deactivation/history survive recreation. Hosted publication remains pending.
Live 3013 uses accepted 0.57.0/0.38.0 images; private login/routing is preserved and
personal risk/strategy values remain unconfigured. Preserve live
3013 credentials/routing revision 1 and unconfigured risk/strategy state. No live probes.
PH-009/003 stay postponed; 001-B is a subsequent task, not implicitly authorized.

### IDQ-004 shipped (2026-09-17)

Maintainer changed priority to **004 → 005 → 001-B**, postponing 003, then explicitly
authorized [evidence snapshots](../features/investment-evidence-snapshots.md).
Shipped at 0.56.0/0.37.0 through protected PR #12: implementation
`3f339f771d4f7214d83d002b5b6d84e6c47994d1`, merge
`86d912e14e34bb9320ee0de54a6c8cc7ee72c830`. Sealed per-symbol
aggregates, collector fencing, typed source/unit/period/PIT metadata, frozen tools,
structured-field validators and Portfolio/Deep dossiers are implemented locally.
Matched fields do not certify prose/source truth; no ready/approval/strategy is enabled.
Local backend 2180 / frontend 271 tests pass; final image-only acceptance passes 33
scenarios. Two post-review no-cache builds match full manifests/assets/source trees.
Hosted run 35209071011 passed all gates and five browser lanes; downloaded reports
were verified in the [receipt](../features/assets/idq-004/hosted-validation.json).
Live 3013 runs accepted images with private
credentials/routing revision 1 and unconfigured personal risk policy preserved.
At IDQ-004 shipment, 005 was not yet authorized. Current authorization is recorded above.
No live inference is required; PH-009 remains paused.

### IDQ-002 shipped (2026-09-17)

The maintainer authorized the next [risk/allocation task](../features/investment-portfolio-risk-allocation.md).
Shipped at 0.55.0/0.36.0 through protected PR #10. Implementation
`17b6a4b6884794302c747fa162b03f6856636417`, merge
`ef1fd2cd6897858fcb7a32638b871e2148215ded`. Implements daily-close
XNYS snapshots, full-account vs invested sigma, dated covariance, fractional holdings,
explicit preview-policy CAS and post-trade batch checks. No ready/approval is enabled.
Backend 2142 / frontend 269 tests and strict gates pass locally. Final image-only
acceptance passes 30 scenarios; two unchanged-input clean builds per component match
full manifests/assets. Hosted run 35193568404 passed every gate and all four
browser lanes; downloaded reports are verified in the
[receipt](../features/assets/idq-002/hosted-validation.json). Live 3013 uses accepted
images with its private credential volume and routing revision 1 preserved; no live
inference was requested and no personal risk policy was configured automatically.
At IDQ-002 shipment, PH-009 and IDQ-003–009 were unstarted. See current authorization above.

### IDQ-001-A shipped (2026-09-16)

The maintainer authorized the narrow [safety containment slice](../features/investment-decision-safety-containment.md).
Shipped at 0.54.0/0.35.0: implementation `75e2431779b631b74077b033544197296152c9c2`,
protected PR #8, merge `5ce5d8a14bfbefe74e1d71968409d1502d02397d`.
New AI outputs are non-actionable assessments; legacy orders are read-only, manual
real-trade recording is separate. No ready or approval can be produced in A.
Local backend 2100/frontend 266 tests pass; final image-only acceptance has six
safety, four Copilot, six hardening and eleven default scenarios. Two clean builds
match complete dependency/asset manifests. Hosted run 35087643908 passed every gate
and all three browser lanes; downloaded reports were verified. See
[receipts](../features/assets/idq-001-a/hosted-validation.json).
At A shipment, IDQ-001/000 remained in-progress and other children were planning;
current IDQ-002 authorization is recorded above. PH-009 stays paused.
The live localhost:3013 instance uses the final images; private credentials and the
full role map/routing revision 1 were preserved. No new live inference was performed.

### Shipped GHC-002 multi-vendor role routing (2026-09-16)

GHC-002 shipped at backend 0.53.0/frontend 0.34.0 via protected PR #6,
merge `c00efe6d884eb8dd49090dd49aa47a54c3d28208`, implementation
`0719b92389f211018ce93d8cd2573bd64a0b903d`.
See [GHC-002](../features/copilot-multivendor-role-routing.md). Native Responses
and Chat Completions, versioned role overrides, actual Portfolio/translation/check
bindings and role-aware replay are implemented. Local tests: backend 2061, frontend
261; full lint/types/security and critical coverage passed. Two clean builds match;
final image-only 4 Copilot + 6 hardening + 11 default E2E passed.

Live account: 16/16 bounded structured probes and Gemini/Grok tool round trips passed.
The default remains Astra; the discussed editable multi-vendor role map was explicitly
applied on the live UI at localhost:3013. Final-image news/debater/translation probes
passed. Existing OAuth was preserved; no MAI call or model-policy change was made.
Hosted CI run 35055009845 passed every gate and both browser lanes. Both reports
were downloaded and verified; no credential files were included. See
[hosted receipts](../features/assets/ghc-002/hosted-validation.json).
At the GHC-002 release, PH-009 and IDQ were unstarted. Current A authorization is recorded above.

### Shipped GHC-001 native Copilot (2026-09-15)

Native Copilot shipped at backend `0.52.0` / frontend `0.33.0` through protected
PR #4, merge `94a190f2d1838de198eb4a9e94b85c2e15ede495`. Implementation:
`5b097d086ec109a7720ab8afcb8443bc2c85d10a`; browser supplement: `6e5ba29`.
See [native provider spec](../features/native-github-copilot-provider.md) and
[hosted receipts](../features/assets/ghc-001/hosted-validation.json).
At the GHC-001 release, PH-009 and all IDQ runtime changes were unstarted.

Core and recorded browser tests pass; the real account separately authorized and
passed structured inference plus a bounded native tool-result round trip on
gpt-6-astra. Real credentials are isolated in a private Docker volume and must
never be copied into the repo, fixtures, images, or CI artifacts. The live UI is
localhost:3013 (backend 18095); the recorded test stack is 3012/18094.
Two final clean builds and image-only acceptance (3 native, 6 hardening smoke,
11 default E2E) passed. Real authorization/model selection survived recreation
onto those images and live structured inference passed again. Hosted CI run
34953213465 passed all backend/frontend/security and both browser lanes; downloaded
artifacts retain both reports and contain no credential files. Runtime source and
dependency inputs are unchanged by the later test-only supplement.

### Previously shipped hardening baseline

PH-001/002/004/005/010 have completed local acceptance, clean-image browser proof,
hosted PR validation, negative-gate/artifact verification and protected implementation
merge. The program remains **in-progress** because PH-009 has not started.

```text
hardening release backend: 0.51.5
hardening release frontend: 0.32.5
implementation PR: #1 (merged 2026-09-14)
implementation merge: 7cc3789b291cfb71865d3cb7a368a965957db5ca
shipment documentation: PR #2 merged as f0a5ed0 (2026-09-14)
subsequent release: GHC-001 at 0.52.0 / 0.33.0; PH-009 and IDQ still paused/planning
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

## 5. Current Direction — IDQ-005; PH-009 Paused

The maintainer explicitly requested **not to execute PH-009**. IDQ-001-A is now
separately authorized and shipped; see the current state above and the
[program](../features/investment-decision-quality-program.md). IDQ-001 remains
in-progress even after A ships. B requires confirmed policy and IDQ-002/004/005;
none of those limits or approvals may be invented to make A look complete.
IDQ-002 software is shipped as non-actionable risk/allocation previews. IDQ-004 is
shipped as a bounded evidence/structured-field layer; subsequent order is 005 then
001-B, with 003 postponed. IDQ-005 now has explicit pilot authorization; 001-B still
requires a separate instruction. Other child
plans remain planning. No paper execution or investment-quality claim.

### PH-009 Resume References (Not an Active Work Queue)

The integrated build/CI baseline is accepted, but resumption still needs maintainer
approval. The earlier priority list is retained only for that future decision:

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
