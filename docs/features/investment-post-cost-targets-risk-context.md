---
title: Post-Cost Target Sizing and Complete Decision Risk Context
status: shipped
version: backend@0.61.0, frontend@0.42.0
last_updated: 2026-10-12
owner: maintainer
related_paths:
  - backend/src/services/portfolio_risk/
  - backend/src/services/decision_policy/model_risk_context.py
  - backend/src/services/decision_policy/model_prompt.py
  - backend/src/models/portfolio_risk.py
  - frontend/src/components/portfolio/ReviewPolicyPanel.tsx
---

# IDQ-001-D：费用后目标仓位与模型风险上下文

## Authorization / Root Cause

User said “继续” after the IDQ-009-A findings. This authorizes fixing the target-basis and
risk-context boundaries, not additional live inference or personal policy activation.
The registered six-request live allowance is spent; all acceptance here is deterministic
or explicitly labeled recorded-provider replay. A future real-model recheck needs new consent.

The earlier model prompt said target weight used **after-trade equity**, while IDQ-002@1
sized shares from **pre-cost equity** and checked limits against **post-cost equity**.
The recorded REDUCE-to-30% case therefore became 30.0132% after costs and was correctly
blocked, but the target/sizing semantics did not agree. Risk context omitted current
computed sigma/coverage/correlations and showed a stop-risk preview field without saying
it was inapplicable to target-only fundamental proposals.

## Frozen Contract / Compatibility

- Preserve `idq-002@1` preview arithmetic and all historical receipt hashes. Older review
  policy versions default to the old allocation binding, never silently migrate.
- A newly explicitly confirmed `post-cost-target-paper-review@2` contract binds allocation
  `post-cost-targets@1`. UI describes after-cost targets, directional lot rounding and
  remaining differences before confirmation. No personal values are filled/activated.
- Requested weights are unchanged. Calculate shares for the declared target basis, not
  a policy-clipped smaller target. Targets above position/sector limits or relying on
  unfilled sales still block; no reduce-only override, concentration repair or cash resize.
- Missing new receipt/provenance fields serialize away on legacy records so immutable
  v1 assessment/review/evidence IDs/hashes remain verifiable. Risk estimator/session
  calculator stays idq-002@1; only allocation semantics change.

## Algorithm / Receipts

For pre-cost equity E0, uniform confirmed proportional cost rate c=(fee+slippage)/10000,
current proposed-symbol notionals vi and target weights ti, solve the continuous equation:

```text
E* = E0 - c * Σ |ti * E* - vi|
```

Targets sum ≤1; c≤0.2 under existing bounds. The unique positive solution is obtained by
exact rational piecewise-linear intervals, not an LLM formula or float convergence guess.
Non-proposed positions are fixed and still count in full-account checks.

Round signed trade deltas downward to the confirmed lot grid (buys floor, reductions
ceil their sale magnitude); full exit may consume the remaining odd lot. Recompute
actual cost/equity and, if rounding interactions exceed a declared target, repeat only
this target/lot conversion monotonically downward with a bounded iteration limit. Failure
to converge is blocked, never a successful approximation. This is disclosed sizing,
not changing the target or clipping to policy. Stop plans are not supported in this
new target-only allocator; legacy stop-risk previews remain available under v1.

Receipt binds allocator/basis/solver/rounding, original and continuous/actual equity,
actual aggregate costs, conversion iterations, and each original target versus effective
post-cost weight. Same batch/subset ordering gives the same result. The existing whole-
account cash/position/sector/turnover/history/sigma checks remain authoritative, including
unfilled SELL proceeds not being buying power.

## Prompt / Versioning

Register `portfolio-model-decision@2`; old records retain @1. The actual prompt uses the
frozen source capture/cost policy, not a mutable current-policy lookup. It supplies
account revision/session/currency, declared cash/equity, exact position quantities and
closing marks, full current risk metrics (account/invested sigma, HHI, beta availability,
coverage/common-session range/errors/exclusions/correlations), and candidate input
availability. Missing data stays unavailable/unknown, never neutral or zero.

Current risk diagnostics are not proposed risk approval, maximum-loss bounds or evidence
of suitability/profit. Proposed risk is computed only after a target set exists. The
preview stop-risk field is explicitly inapplicable/omitted from executable target rules;
no fabricated stop distance is needed. The template describes the bound policy's actual
legacy/pre-cost versus new/post-cost basis and directs the model to propose when data
supports it rather than treating a pending code check as missing current data.

## Validation / Protected Publication

- **2383 backend tests / 27 live integrations deselected**, aggregate75.9638%, strict
  mypy355 source files; all original plus shared-check95/post-cost90/risk-context90 floors,
  Black/Ruff/Bandit/eval and nine script tests/six subtests pass. **281 frontend tests**,
  production lint0/total131, types/build pass. [Local receipt](assets/idq-001-d/local-validation.json).
- **62 deterministic final-image scenario executions**: review/model/post-cost11 +
  portfolio-model replay9 + paper5 + strategy4 + evidence3 + risk3 + safety6 + Copilot4 +
  hardening6 + default11. New recorded geometry is ready/approved with29.9 shares and
  unchanged30% target; above-cap40% stays blocked. No live inference consumed.
- Two unchanged-input no-cache builds match dependency/source/asset manifests, UID1000,
  no local env/credentials: [build receipt](assets/idq-001-d/clean-build-validation.json).
  Policy/source/sizing/approval responses remain byte-equivalent across actual recreation:
  [persistence receipt](assets/idq-001-d/persistence-validation.json).
- [Curated approved sizing](assets/idq-001-d/01-post-cost-approved.png) uses the recorded
  2026-09-17T12:00:00Z clock and synthetic account, not the old paid report or live account.
- A rapid PAPER test helper selected the old form before sequence-driven remount; it now
  waits for the returned sequence/new form without changing financial assertions, retries
  or timeout budgets. Failed artifacts retained; full final-image regression rerun passed.
- Implementation `21e2e795020808ba08cb24402ac28cdd1de54bd2` merged via protected
  [PR#24](https://github.com/fhw12345/FinancialAgent/pull/24) as
  `e6d680f7183fc752dd0a14665adb931882738c9a`. Hosted
  [38233353603](https://github.com/fhw12345/FinancialAgent/actions/runs/38233353603)
  passed every required gate and nine browser lanes/51 cases; downloaded archive digest,
  embedded report hashes/stats and zero credential files were verified:
  [hosted receipt](assets/idq-001-d/hosted-validation.json).
- Live3013 runs accepted0.61.0/0.42.0 B images, preserving independent private credentials,
  defaultAstra/routing revision1/role map and all real-account/config hashes. Risk/strategy/
  review policies remain unconfigured; no policy is automatically migrated. Read-only
  browser validation and deployment made zero inference/trade calls:
  [live receipt](assets/idq-001-d/live-validation.json).
- Required Unit Tests/Actions app15368/strict up-to-date/admin enforcement are unchanged;
  no bypass. No fresh real-model acceptance is claimed; the prior paid report remains
  unchanged at old prompt/allocation versions and its original finding remains recorded.

## Tests / Browser Acceptance

- Red regression: captured concentrated geometry (10000 equity/70 AAPL shares, 30% target,
  1bps fees+10bps slip, 0.1-share lot). v1 remains blocked at 30.0132%; new basis computes
  29.9 remaining shares, unchanged target 30%, post-cost weight ≤30%, no policy override.
- Exact independent rational golden, zero-cost v1/v2 agreement, BUY/REDUCE/exit, mixed
  targets, fixed omitted holdings, sums>1, costs, lot/odd-lot, unsupported stops, numeric
  overflow, reorder/subset consistency and all previous policy negatives retained.
- Verify prompt includes actual current risk/cash/quantities/coverage, basis/version,
  no inapplicable stop budget, and unknown risk/beta remain unknown. A bounded correlation
  presentation explicitly lists omitted holdings; aggregate metrics and gate stay full-account.
  Bind source costs;
  racing account/configuration writes still prevent publication/approval.
- Verify new policy confirmation CAS, legacy hash/provenance/replay readers and old
  model outputs cannot be promoted under a different allocation/policy binding.
- Real UI/API/Mongo recorded-provider browser: explicit new contract → concentrated
  REDUCE 30% → versioned sizing/ready → human approval, original real/manual-paper ledger
  unchanged. Above-limit target still blocked, reload/recreation preserves exact receipts.
  Fresh test evidence IDs are used: not reuse/relabel the old paid record as repaired.
- Full quality/security/critical floors, 60+ final-image regressions, repeat builds,
  curated screenshots `assets/idq-001-d/`, docs/case study/versions and protected two-stage
  publication required. Original 009-A paid report remains unchanged and no new live calls.
