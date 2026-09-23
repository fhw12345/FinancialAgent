---
title: Model-Proposed Portfolio Decisions for Human Review
status: shipped
version: backend@0.59.0, frontend@0.40.0
last_updated: 2026-09-22
owner: maintainer
related_paths:
  - backend/src/models/model_decision.py
  - backend/src/services/decision_policy/model_decision.py
  - backend/src/services/decision_policy/model_decision_gate.py
  - backend/src/api/portfolio/model_decisions.py
  - frontend/src/components/portfolio/ModelDecisionPanel.tsx
---

# IDQ-001-C：模型给出投资决策，代码校验，人工决定

## Scope / Authorization

Maintainer asked that the model make the investment decision as an explicit
recommendation, then said “开始”. The assistant-proposed v1 boundary applies:

- The model returns one explicit action per researched symbol — **BUY, ADD, REDUCE,
  SELL or HOLD** — plus an account-equity target weight for position changes,
  rationale, captured evidence IDs, key risks and review triggers.
- Code computes quantities and runs the unchanged IDQ-001-B gate. Blocked decisions
  are shown with their reasons; code never silently resizes, rewrites to HOLD or drops
  a model decision.
- Every decision still needs explicit human approval. Approval never changes real
  holdings/cash, calls a broker or creates a simulated fill.
- Scope is the symbols of one completed Portfolio research source, intersected with the
  user-attested review universe. Holdings research covers existing positions; watchlist
  or picks research covers explicitly researched candidates. Merging multiple sources and
  autonomous candidate discovery (IDQ-003) are not included.
- No personal limits are inferred. Model decisions are disabled until the user confirms a
  review-policy version that enables them and explicitly answers whether new positions
  and full exits may be proposed. No live model probe is part of development; the user
  explicitly triggers each paid decision call.

## Contract

`ModelDecisionSet` is strict structured output (`extra=forbid`, finite numbers,
weights in `[0, 1]`, no readiness/approval/quantity/price fields). Validation codes:

| Case | Result |
| --- | --- |
| Missing or duplicate decision for a scoped symbol, or an out-of-scope symbol | blocked |
| BUY on held / ADD, REDUCE, SELL on flat / SELL with non-zero target | blocked |
| Action disagrees with computed share delta (e.g. REDUCE that increases shares) | blocked |
| New position or exit when the policy does not permit it | blocked |
| Non-HOLD without same-symbol available, non-conflicted captured evidence IDs | insufficient_evidence |
| BUY/ADD without a bullish strategy stance; SELL against a bullish stance | needs_review |
| Decision produced under a policy version that is no longer active | needs_review |
| Target rounds below one lot | shown as HOLD with `MODEL_TARGET_BELOW_LOT` |

HOLD targets are not traded; held/flat remains visible. All IDQ-001-B checks remain:
positive consistency receipt, sealed evidence/dossier/strategy revalidation, full
account constraints, sigma budget, monitoring, freshness, lifetime, CAS and subset
revalidation without borrowing omitted-sale headroom.

## Lifecycle

1. `POST /api/portfolio/model-decisions` (local action, rate limited) requires explicit
   confirmation, expected control revision/generation and a request ID. The server
   rejects before any model call when the policy disables model decisions, source is not
   completed/eligible for review, or inputs are mutating/uncertain.
2. A per-request claim prevents duplicate calls for the same request. The immutable
   output is persisted before validation; replay returns the stored decision without
   another paid call. A failed call is recorded as failed and cannot be resumed.
3. The stored decision is converted to targets and published through the review CAS.
   If inputs changed during the call, publication fails; the user may re-validate the
   stored decision without a new model call. Stale results are never auto-refreshed.
4. Provenance records prompt `portfolio-model-decision@1`, role
   `portfolio_decisions`, provider, actual routed model, protocol and routing revision.

## Acceptance / Protected Publication

- Backend **2316 passed / 27 live deselected**, strict mypy 345 files, Black/Ruff/Bandit/eval,
  all existing plus five new critical floors. Frontend **278 tests / 32 files**, production
  lint 0, total warnings 131, types and build.
- **46 final-image browser cases**: 9 review/model + 4 strategy + 3 evidence + 3 risk +
  6 safety + 4 Copilot + 6 hardening + 11 default. Two clean builds match full manifests.
- Screenshots: [ready model decision](assets/idq-001-c/01-model-decision-ready.png),
  [blocked model decision](assets/idq-001-c/02-model-decision-blocked.png).
  Receipts: [local](assets/idq-001-c/local-validation.json),
  [builds](assets/idq-001-c/clean-build-validation.json).
- Review found and fixed: replay rechecking current revisions (false 409), cancellation
  leaving a running claim, and blocked reasons not shown beside the recommendation.

- Implementation `8f5d15d2ae2894eafad70c64f05c79218a18ae7d` merged via protected
  [PR #18](https://github.com/fhw12345/FinancialAgent/pull/18) as
  `afac9c2f746020829e515bad85e08c136746656d`. Hosted
  [run 35854518856](https://github.com/fhw12345/FinancialAgent/actions/runs/35854518856)
  passed all gates and seven browser lanes (35 cases); artifact ZIP digest and report
  stats verified, no credential files ([receipt](assets/idq-001-c/hosted-validation.json)).
- Live localhost:3013 runs the accepted images at 0.59.0/0.40.0 with Copilot login,
  Astra default, routing revision 1, role map and the migrated SPCX holding preserved.
  Risk policy, strategy and review policy (including model decisions) remain
  **unconfigured**; no live model call ([receipt](assets/idq-001-c/live-validation.json)).

## Acceptance Criteria

- Unit/composition tests for schema forgery, every validation row, replay without a
  second call, claim conflict, failed call, policy disabled, stale re-validation, subset
  approval of model decisions, and unchanged manual path.
- Real browser: explicit enablement → holdings research → model decision call (recorded
  outer transport) → ready → human approval with zero ledger changes; blocked decision
  displayed with reasons; reload persistence.
- Full existing gates, final-image regressions, repeated builds, docs, case study and
  protected two-stage publication. No investment-effectiveness claim.
