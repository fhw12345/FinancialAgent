---
title: Cash Is Not Missing Risk
status: in-progress
version: backend@0.55.0, frontend@0.36.0
last_updated: 2026-09-17
owner: maintainer
related_paths:
  - backend/src/agent/portfolio/risk_calculator.py
  - backend/src/services/portfolio_risk/
  - backend/src/services/holdings_ledger.py
  - backend/src/database/repositories/decision_assessment_repository.py
  - frontend/src/components/portfolio/RiskReceipt.tsx
---

# Cash Is Not Missing Risk

> **TL;DR (EN)**: Renormalizing stock weights after including cash in account equity
> silently turns account volatility into invested-subportfolio volatility. Keeping
> dated inputs, explicit denominators and missing-data states fixes the estimator;
> versioned policy and whole-batch previews then expose rejected allocations without
> pretending to approve them. This does not establish investment effectiveness.
>
> **TL;DR (中文)**：把股票权重重新归一化会抹掉现金，把股票部分波动率冒充账户波动率。
> 保留交易日期、明确分母与缺数状态后，再用用户确认的限额检查整个拟议组合，才能给出
> 可复算的风险预览。预览不等于批准，也不是投资效果证明。

## 1. Context

IDQ-001-A stopped unverified recommendations becoming actions. The next review found
that the old risk helper still reported a 90%-cash account as if it were fully invested,
paired returns by array length rather than session date, and omitted assets without
history. The same path truncated fractional holdings to integers. An old model size
hint also was not an actual equity-based portfolio policy.

## 2. Investigation

The first regression run failed twice: reported sigma was 0.3202 instead of about
0.03202, and the holding DTO rejected 0.5 shares. The corrected oracle separates
account sigma 3.2017% from invested sigma 32.0169%, with invested HHI=1.

The first pinned calendar candidate (exchange-calendars 4.11.3) was incompatible with
this repository's pandas 3 datetime resolution: valid 2026 sessions were rejected as
out-of-bounds. We pinned 4.13.2 and verified holidays/early closes rather than adding a
calendar bypass. The live dependency graph is locked; no scientific-package downgrade
or copied hand-written holiday approximation was used.

Real browser acceptance then caught a BSON boundary bug: datetime.date session keys
were valid Pydantic values but not BSON values. The central assessment writer now
serializes nested risk receipts using their JSON wire contract; a real BSON-codec
regression reconstructs dates and recomputes the same metrics after round-trip.

## 3. Root Cause

- A single ambiguous sigma name hid two different denominators.
- Anonymous arrays and subset renormalization concealed missing portfolio coverage.
- Current cached quote availability did not imply a common valuation session.
- Legacy integer DTO/context/ledger conversions destroyed fractional ownership.
- Descriptive risk settings and estimated sale proceeds were mistaken for enforceable
  limits and settled buying power.

## 4. Fix

- Full local-account snapshots bind quantities, cost basis, declared cash, common XNYS
  closing session, provider-adjusted dated returns, method and preview-policy revision.
- Missing marks/history, invalid dates/numbers, unsupported currency/instruments and
  insufficient intersections remain unavailable. Beta is never silently assumed one.
  Constants have zero sigma but undefined correlation; cash-only and zero-equity states
  have separate, explicit results.
- A separately confirmed preview policy has no preselected personal limits. Decimal
  share rounding and optional stop-risk sizing include conservative cost buffers;
  the whole proposed account is checked against concentration, cash and turnover.
  Unfilled sales cannot finance buys. Resizing has an explicit receipt, not a rewrite
  of the model's original draft.
- Holdings/picks/single-symbol research use the whole local account. Risk receipts are
  committed atomically with non-actionable assessments; stale projections preserve
  historical inputs rather than silently recalculating them.
- Fractional quantities remain fractional through UI, API, repository and manual
  bookkeeping. Decimal addition avoids residual dust on 0.3−0.1−0.2 sales.
- The UI shows separate current/proposed values, coverage, confirmed thresholds and
  exact rejection codes. Stage A still cannot produce ready, approval or execution.

## 5. Lessons and Evidence Boundary

A valid estimate is not a maximum-loss guarantee; sixty-day correlations can change
in a crisis and stops can gap. Provider-adjusted historical data is not a PIT archive.
Cash is a user-maintained declaration, not a newly implemented settlement ledger.
Full policy/evidence/strategy/approval integration remains future work.

Local quality gates: backend 2142, frontend 269; types/lint/security and critical
floors passed. Recorded-transport browser scenarios traverse actual API/graph/provider
adapters/Mongo. No live model allowance or investment-strategy benchmark was used.
Final-image acceptance passed 30 scenarios. Two unchanged-input builds per component
match full dependency/asset manifests: backend A/B and frontend B/C; frontend A was
excluded after the zero-cash HTML input correction. The live account's credentials
and role configuration were preserved; no synthetic risk limits were applied there.
Hosted shipment remains pending; see the
[feature record](../features/investment-portfolio-risk-allocation.md).
