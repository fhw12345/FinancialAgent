---
title: Target Equity Basis Is a Contract / 目标权益口径是一份契约
status: in-progress
version: backend@0.61.0, frontend@0.42.0
last_updated: 2026-10-12
owner: maintainer
related_paths:
  - backend/src/services/portfolio_risk/post_cost.py
  - backend/src/services/portfolio_risk/allocation_checks.py
  - backend/src/services/decision_policy/model_risk_context.py
  - backend/src/services/decision_policy/model_prompt.py
---

# Target Equity Basis Is a Contract / 目标权益口径是一份契约

> **TL;DR (EN):** A target defined after costs cannot be sized from pre-cost equity and
> then called compliant. The real-model test correctly blocked the exact-cap proposal;
> the fix is a versioned cost-aware target calculation, not a loosened gate or silently
> smaller target. Frozen current risk inputs and pending proposal checks are also distinct.
>
> **TL;DR (中文)：** 费用后目标不能按费用前权益算股数后声称合规。真实模型测试的上限方案
> 被正确阻断；修复应是版本化费用感知计算，不是放松门禁或偷偷缩小目标。当前风险数据与
> 等待目标后执行的校验也必须分清。

## 1. Context

IDQ-009-A's single registered live batch produced a REDUCE-to-30% recommendation on a
synthetic 70%-AAPL account. Pre-cost sizing left30 shares; costs4.4 reduced equity to9995.6,
so weight became30.0132% and POSITION_LIMIT blocked it. The user authorized continuing
with the root-cause fix, but the six paid calls remain spent; no new inference is permitted.

## 2. Investigation / Root Cause

The original allocator consistently sized from pre-cost equity and enforced limits after
costs. Its checks were correct for its old basis. The model prompt, however, described a
post-trade-equity target. Clamping the result to the position cap would conceal this mismatch,
change the recommendation or bypass policy. Historical receipts and already-confirmed
policy semantics also cannot be silently updated to the new algorithm.

The prompt supplied equity/weights/cash weight but omitted computed account sigma,
coverage and detailed positions; it passed a preview stop-risk budget without disclosing
that a stop plan is inapplicable to target-only fundamental review. Live rationales therefore
asked for risk inputs that existed in the code or were intentionally deferred/inapplicable.

## 3. Fix

A new explicitly confirmed policy binds `post-cost-targets@1`. The continuous equity
identity E*=E0−cΣ|tiE*−vi| is solved over exact rational piecewise intervals. Signed
lot-grid conversion rounds buys down and reductions sufficiently far down to respect the
requested weight; actual cost/equity is rechecked after rounding. The target remains30%,
while29.9 remaining shares produce a disclosed achieved weight below30%. The solver never
uses a personal position/sector cap to change a target; a40% request against a30% policy
still fails. Omitted holdings and unfilled-sale financing checks stay intact.

Legacy previews remain idq-002@1. Optional new binding/receipt fields serialize away on
old records so immutable hashes still verify. The captured old paid report remains old
and blocked; a fresh deterministic replay does not relabel it as a new live success.

Prompt@2 carries frozen current account/risk/quantity/closing inputs, explicit unavailable
values and correlation presentation omissions, declared target basis and applicable rules.
A pending proposed-risk check is not missing current risk; no stop or maximum-loss bound
is invented. No actual research/return suitability is certified.

## 4. Verification

Red tests reproduce the old30.0132% result and an all-cash full-target cost failure.
Independent rational/brute-force oracles check target sizing, mixed directions, lot
interactions, odd-lot exits, unavailable inputs and unsupported numeric ranges. Captured
paid receipt hash/provenance stays verifiable. Actual UI/API/Mongo recorded-provider
regression confirms a new policy → unchanged30% target → versioned29.9-share receipt →
ready/human approval without ledger mutation, and the above-limit40% target remains blocked.
Local2383 backend/281 frontend tests and all strict/critical gates pass, with62 final-image
recorded-provider/UI regression executions, equal source/dependency/asset builds and real
recreation preserving exact new receipts. A PAPER browser wait was corrected to the returned
sequence/form remount (no financial assertion/retry/timeout changes). Hosted protected
publication remains pending; see [the feature](../features/investment-post-cost-targets-risk-context.md).

## 5. Lessons

Equity basis, cost model and rounding are authority-bearing contracts, not cosmetic text.
Upgrade with explicit version binding and visible receipts; preserve old evidence instead
of recalculating it to look repaired. Share the whole-account checks, and never hide an
invalid target behind silent resizing. A better prompt/data contract still does not prove
better investment outcomes; real-model revalidation requires separate new bounded consent.
