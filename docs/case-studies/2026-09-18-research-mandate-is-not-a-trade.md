---
title: A Research Mandate Is Not a Trade
status: in-progress
version: backend@0.57.0, frontend@0.38.0
last_updated: 2026-09-18
owner: maintainer
related_paths:
  - backend/src/services/research_strategy/
  - backend/src/models/research_strategy.py
  - backend/src/agent/portfolio/research_prompt.py
  - backend/src/agent/deep_workflow.py
  - frontend/src/components/portfolio/ResearchStrategyPanel.tsx
---

# A Research Mandate Is Not a Trade

> **TL;DR (EN)**: A one-year research horizon cannot safely inherit a short-term
> entry/stop/take-profit prompt. The confirmed fundamental pilot now freezes its
> horizon, benchmark, peer set, assumptions and evidence requirements, then produces
> conditional valuation receipts and a separate research stance. It still grants no
> portfolio action, execution intent, approval or claim of investment effectiveness.
>
> **TL;DR (中文)**：一年研究期限不能直接套用短线入场/止损/止盈提示词。首发基本面契约
> 现在冻结期限、基准、同行、假设及证据要求，产出条件性估值记录和独立研究立场。
> 它不赋予组合行动、执行或批准资格，也不证明投资效果。

## 1. Context

The maintainer approved a 252-XNYS-session, SPY-total-return, USD US non-financial
common-equity pilot. Peer PE and DCF are conditional methods; financials, insurance
and ETF look-through are outside this pilot. Numerical rates, thresholds and peers
were explicitly **not** delegated to the model or silently defaulted by the agent.

## 2. Investigation

The initial regression failed because no registered fundamental prompt existed.
The old portfolio renderer required execution geometry for every BUY/SELL and mixed
Fibonacci references into valuation. Merely adding a horizon label would leave those
instructions and the old output schema in charge of the actual model call.

We therefore gave the confirmed branch independent registered research prompts and
structured conclusions with separate stance, null portfolio action and null execution
intent. Evidence carries the immutable strategy version and predeclared peer IDs.
Inactive/old paths remain visibly unconfigured/legacy instead of receiving fabricated
strategy history.

Real browser testing also caught a local-HTTP compatibility issue: `crypto.randomUUID`
was unavailable on the Docker host alias, crashing the newly opened form. The project
already had a secure-random fallback; exporting/reusing it fixed the root rather than
changing browser security flags. A component regression covers this path. A prior
portfolio test also had a floating capture clock against fixed closing dates; its
clock is now pinned consistently rather than weakening freshness checks.

## 3. Root Cause

A prompt had been carrying responsibilities that belong to versioned code contracts:
method applicability, units, holding horizon, required facts and invalidation criteria.
Model confidence and a formatted target price were not substitutes for those contracts.

## 4. Fix

- One bounded CAS aggregate retains immutable confirmed versions and an active pointer.
  Request replay is idempotent, stale/divergent updates conflict, and late replay cannot
  resurrect a deactivated strategy. Saving/selecting makes no model call.
- Personal assumptions start blank. Costs bind an explicitly confirmed risk-policy
  revision; later changes mark old receipts stale without rewriting their values.
- Same-symbol/period/unit checks bind annual diluted EPS, declared peer median PE,
  cash flow, interest, debt, cash and shares to sealed records. No post-hoc peer exclusion
  or sector-multiple fallback is used to rescue a missing result.
- The DCF explicitly models an unlevering proxy, not audited FCFF. Tax/growth/discount
  are user assumptions; annual diluted-average shares are held constant. Dollar scale,
  fiscal date, signs, positive denominators and terminal-growth bounds are checked.
- Monitoring flags are computed for comparable earnings decline, debt/FCFF and discount
  to each model estimate. Missing inputs stay unavailable; estimates are never averaged
  into a claim of certainty. Flags cause review, not an automatic trade.
- Portfolio and Deep consume the same frozen contract. Conditional scenarios have null
  probabilities, and model theses remain unverified prose with captured evidence IDs.

## 5. Lessons / Evidence Boundary

A provider's equity/country/sector classification is a bounded research applicability
screen, not independent proof of share-class eligibility. Historical PIT, full personal
InvestmentPolicy, ready/approval and a paper outcome ledger remain later work. The
SPY total-return benchmark is a declared evaluation contract, not a measured return
comparison or a claim of outperformance.

ST-01…10 numeric/contract tests and actual frontend/API/Mongo scenarios cover the pilot.
Backend 2217/frontend 272 tests and strict gates pass; final image-only acceptance passes
37 cases, including Portfolio/Deep, missing values and stale/deactivation. A registry
transport returned truncated JSON on one clean-build attempt; that attempt was rejected
and retried with the same lock/source inputs, not treated as a successful build.
The bounded clean-build retry matched full manifests/assets/source trees. Immutable
strategy, deactivation and historical receipts survived actual backend recreation.
A supplemental browser run hit one read-transport socket hang-up; the unchanged bounded
rerun passed all four strategy assertions, without suppression or weakened expectations.
The live account's login/roles remain intact and personal risk/strategy configuration
remains empty. Hosted publication receipts are pending in the [feature record](../features/investment-research-strategy-contracts.md).
