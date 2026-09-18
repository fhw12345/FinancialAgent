---
title: Deterministic Paper Review Readiness and Human Approval
status: shipped
version: backend@0.58.0, frontend@0.39.0
last_updated: 2026-09-18
owner: maintainer
related_paths:
  - backend/src/services/decision_policy/
  - backend/src/models/decision_review.py
  - backend/src/models/decision_assessment.py
  - backend/src/api/portfolio/
  - frontend/src/components/portfolio/
---

# IDQ-001-B：确定性 ready 与人工 paper 审阅批准

## Scope / Authorization

Maintainer authorized the next task after IDQ-005: explicit user target weights,
code-calculated quantities, whole-batch validation and human review approval.
No personal limits or target weights are supplied by the agent. No broker execution,
real-account mutation, simulated fill, ledger creation, automatic stance→BUY mapping,
PH-009 work or deferred IDQ-003 work is authorized here.

Existing `DecisionAssessment`/strategy/evidence outputs remain immutable non-actionable
research. New `ReviewBatch` is a separate typed contract: `ready` means **approvable
for human paper review**, never executable. Legacy orders remain read-only and all
old mark-executed paths stay closed. Approval records are not IDQ-008 paper fills.

## Policy / Decision Table

Explicit versioned investment-review policy binds the local declared account, current
confirmed risk/cost policy, one confirmed strategy version and a user-attested allowed
symbol list. USD, long-only, no leverage and no unfilled-sale financing are fixed pilot
constraints. User must enter the maximum proposed account sigma and proposal TTL;
no values are inferred from old risk tolerance or model confidence.

User must acknowledge the forward, daily-close reference basis, provider/identity and
conditional-valuation limitations. This does not certify historical PIT, source truth,
free prose, common-share identity or future profitability. Strict historical readiness
is not offered. Permitted instruments require explicit user attestation, not provider
classification alone. Actual future paper consumption will require IDQ-008 revalidation.

| Check | Failure |
| --- | --- |
| Complete, confirmed policy + matching risk/strategy revisions | research_only / needs_review |
| Source run completed, research not partial/legacy/degraded | insufficient_evidence / needs_review |
| Fresh sealed same-run evidence/dossiers; recorded claims revalidate | insufficient_evidence |
| Applicable complete strategy inputs/model estimates; no invented defaults | insufficient_evidence / blocked |
| BUY has no triggered/unavailable required monitoring check | needs_review |
| Explicit target symbol belongs to source and attested universe | blocked |
| Current account/closing reference/history agree with the source capture | needs_review; new research required |
| Full proposed account satisfies 002 constraints and declared sigma budget | blocked |
| TTL / last completed session / control generation still current | needs_review (`PROPOSAL_EXPIRED` / stale reason) |
| Durable batch preparation and final control CAS both succeed | otherwise no ready publication |

BUY/SELL/HOLD are derived from rounded share delta, not stance/confidence. HOLD has no
execution prices; flat HOLD displays WAIT. No short intent is introduced. Target-only sizing has no stop-loss plan or
maximum-loss bound; the preview policy's stop-risk budget is not applied without a
stop. The pilot enforces account sigma/exposure/cash/turnover instead, explicitly
disclosed at confirmation. Reduction never reuses short-entry geometry. The daily closing mark is a **reference**, not an
execution quote. Positive and missing-data negative cases must both be demonstrated.

## Atomicity / Lifecycle

- One Mongo `review_control` aggregate coordinates a world revision, mutation tickets,
  immutable policy versions, one current review pointer/generation and bounded approval
  events. Budgets: 100 policy versions, 200 published reviews, 200 approvals and
  200 control events; exhaustion returns 409 without pruning immutable history or
  replay keys. Each prepared receipt is capped at 2 MiB. No standalone Mongo
  multi-document transaction is assumed.
- Structural holding/manual-transaction/settings, risk-policy and strategy mutations
  announce a ticket and advance the shared revision **before** their writes. Finishing
  removes that ticket and advances revision again. Even a rejected announced attempt
  conservatively advances the fence; it is not rolled back into a former approval.
  Nested writes share the outer ticket.
  Approval never commits while a mutation is in flight.
- Risk/evidence/strategy checks and provider I/O happen outside the atomic commit. The
  immutable candidate/approval receipt is prepared first; a CAS on the same control doc
  publishes the reference only if revision/generation/policy and idle state still match.
  Mongo's `$$NOW` must also precede the immutable expiry at that same CAS; expiry
  is capped at the next XNYS session close. A storage delay cannot approve an expired
  batch or carry the old reference across a completed-session boundary.
  Orphan preparations are not ready or approved. Concurrent mutation either precedes
  and blocks that CAS, or follows and immediately invalidates current eligibility.
- At most one current review batch per local account. A new publication supersedes the
  earlier pointer; history stays readable. Repeated request IDs with the same payload
  reuse the result; different payloads conflict and cannot resurrect a cancelled batch.
- Subset approval recomputes allocation for exactly the selected targets. Estimated SELL
  proceeds cannot finance BUYs, nor can an omitted SELL supply concentration headroom.
- Cancellation uses the same aggregate CAS. Historical approvals retain their original
  receipt but lose current validity on account/policy/strategy/session/TTL changes.
- Mutation failure marks the control uncertain. Manual bookkeeping remains available;
  review readiness is paused. Explicit idle account reconciliation may clear uncertainty
  against a current fingerprint. Abandoned in-flight tickets after a crash are never
  timed out into safety: stop writers and reconcile offline; no HTTP force-unlock exists.
- Direct database edits and unsupported external writers are not coordinated APIs;
  content fingerprints catch their observed changes, but do not provide a distributed
  transaction guarantee for arbitrary bypass writes. Runtime remains single-user local.

## API / UI Contract

New read/configure/propose/approve/cancel endpoints use trusted-origin local-action
headers, bounded payloads, no-store responses and server-computed readiness. Clients
cannot submit readiness, prices, quantities, approval status or formula code.

Portfolio UI keeps research separate from manual target proposals. It displays per-gate
receipts, source/policy/version IDs, reference prices, calculated deltas, expiry, current
validity and subset checks. All approvals explicitly say no actual/simulated fill.
Risk/strategy configuration and source research remain explicit prerequisite actions;
no approval button triggers paid model research or rewrites the user's account.

Routes: `GET/POST /api/portfolio/review-policy`, POST `/review-policy/deactivate`,
POST `/review-control/reconcile`, `GET/POST /review-batches`, GET `/review-batches/{id}`,
and POST `/review-batches/{id}/approve` or `/cancel`. Proposal payloads carry one
assessment ID, 1–20 distinct `{symbol, target_weight}` entries and expected world/review
revisions. Approval supplies selected symbols and explicit review-only acknowledgment.
The old `/assessments/{id}/approve` and `/decisions/{id}/approve` still reject.

## Test / Browser Acceptance

- DP-01…11 from the parent plan, plus strict numeric/schema/identity forgery cases.
- Real allocation boundary tests: limit equality vs just-over, aggregate cash/sector,
  sell-funded buys, omitted-sale subset, fractional lots and max-account-sigma.
- Snapshot/dossier/strategy membership and recomputation; missing/failed/unknown data
  cannot become ready because an LLM says confident or a request contains `ready`.
- CAS races: approve vs mutation/policy change/cancel, duplicate/conflicting requests,
  failed preparation/commit, partial mutation and explicit idle reconciliation.
- Required evidence families are quote/overview/ohlcv/income/cash-flow/balance-sheet.
  News/filing gaps remain explicitly disclosed noncritical context, not proof of zero
  events. Prose/source truth/historical PIT are always unverified. Pre-B records lack
  positive consistency-check attestation; no backfill. Deep has no such positive
  check receipt in this pilot and cannot be promoted by having a completed run alone.
- Browser: policy+targets → ready → explicit approval with zero account/transaction/fill
  changes; another account/policy edit makes old approval stale; missing evidence and
  invalid subsets remain blocked; reload persists results; legacy has no execution path.
- Curated screenshots under `assets/idq-001-b/` after real frontend/API/Mongo assertions.
  Only recorded outer providers/models may be substituted. No live model probe required.
- Full existing backend/frontend gates, critical floors, security/deterministic eval,
  image-only regressions, repeat clean builds, versions/indexes/bilingual case study,
  implementation then shipment protected PRs and clean synchronized main are required.

## Acceptance / Protected Publication

Final diff review found that finite statement operands could overflow the shared FCFF
proxy and produce a false zero debt ratio. A red real-gate regression reproduced it;
the shared calculator now rejects nonfinite results. Pre-correction images A/B are
excluded. All results below are the successful **post-review** builds C/D and full
final-image revalidation, not the earlier passing normal-data cases.

- Backend **2286 passed / 27 live integrations deselected**, aggregate **74.8868%**;
  strict mypy **339 source files**, Black/Ruff/Bandit/evaluation and all old/new critical
  floors pass. Frontend **275 tests / 31 files**, production lint **0**, total warnings
  **131**, types and build pass. Nine script tests / six subtests pass; 21 rendered
  Compose bindings remain loopback-only. See [local receipt](assets/idq-001-b/local-validation.json).
- **43 final-image browser cases:** 6 review + 4 strategy + 3 evidence + 3 risk + 6 safety
  + 4 Copilot + 6 hardening + 11 default. The new Mongo-clock race proves expiry can
  defeat publication after validation even if the application's clock still says valid.
- Two successful unchanged-input clean builds match full dependencies, frontend assets
  and application source trees; see [build receipt](assets/idq-001-b/clean-build-validation.json).
  Policy/source/approved-review responses remain byte-equivalent across real backend/
  frontend recreation; see [persistence receipt](assets/idq-001-b/persistence-validation.json).
- Synthetic replay screenshots use the explicitly recorded **2026-09-17T12:00:00Z**
  clock, not the live account: [approved](assets/idq-001-b/01-approved-review.png),
  [stale after independent bookkeeping](assets/idq-001-b/02-stale-approval.png),
  [rejected subset](assets/idq-001-b/03-rejected-subset.png).
- Implementation `2ced1281b5de87efec0931a220232983fa92d054` merged through protected
  [PR #16](https://github.com/fhw12345/FinancialAgent/pull/16) as
  `2b8abddd54e3d4dc4f140956642fe5207ae3f99a`. Hosted
  [run 35345193633](https://github.com/fhw12345/FinancialAgent/actions/runs/35345193633)
  passed every required gate and seven browser lanes (32 cases). The downloaded
  artifact ZIP digest and all seven report hashes/stats were verified; no credential
  files were present. See [hosted receipt](assets/idq-001-b/hosted-validation.json).
- Live **localhost:3013** runs the accepted D images at 0.58.0/0.39.0. Independent
  Copilot credentials, Astra default, routing revision 1, role map, account and policy
  hashes survived recreation. Risk policy, strategy and review policy remain explicitly
  **unconfigured**. A real browser read-only check showed the new panel without approval
  or model POSTs. See [live receipt](assets/idq-001-b/live-validation.json).
- Required `Unit Tests` from Actions app 15368 remained strict/up-to-date and enforced
  for administrators; no bypass. No investment-effectiveness claim, live model probe,
  actual trade or simulated fill is part of this acceptance.

## Completion / Rollback

- [x] Policy, target proposal, ready gate and approval are one coherent application path.
- [x] Positive and negative/race/persistence tests and browser receipts pass locally.
- [x] Old research remains non-actionable; manual actual-trade recording remains separate.
- [x] No live policy/strategy/target values are auto-configured; credentials/roles survive.
- [x] Full quality/build/browser/hosted evidence, protected implementation merge and shipment documentation recorded.

Before a binary rollback, deactivate the review policy while B is available, retaining
its control/history fence; do not delete the aggregate or allow older uncoordinated
writers to revive a current approval on re-upgrade. Rollback disables new publication/
approval, never restores legacy AI execution or a fail-open validator. Numeric/claim matching is not proof of alpha.
