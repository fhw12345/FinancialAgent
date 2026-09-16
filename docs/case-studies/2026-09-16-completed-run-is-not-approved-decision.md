---
title: A Completed Run Is Not an Approved Decision
status: shipped
version: backend@0.54.0, frontend@0.35.0
last_updated: 2026-09-16
owner: maintainer
related_paths:
  - backend/src/agent/portfolio/consistency_gate.py
  - backend/src/models/decision_assessment.py
  - backend/src/database/repositories/decision_assessment_repository.py
  - frontend/src/components/portfolio/AddTransactionModal.tsx
---

# A Completed Run Is Not an Approved Decision

> **TL;DR (EN)**: A research process completing is not evidence that its investment
> recommendation is usable. Stage A removes that accidental promotion: all new AI
> outputs are non-actionable assessments, legacy decisions are read-only, and manual
> recording stays independent. Risk, point-in-time evidence and strategy validation
> are still unfinished; this is containment, not proof of investment quality.
>
> **TL;DR (中文)**：研究运行结束不代表投资建议通过验证。A 阶段把新 AI 输出限制为非行动性
> 评估，旧建议只读，手工交易独立登记。风险、时点证据和策略门禁尚未接齐；本次是安全收口，
> 不是有效投资方法或超额收益的证明。

## 1. Context

The IDQ review found three connected failures: permissive legacy BUY schemas,
consistency-check exceptions returning a pass, and an unavailable Portfolio Agent
falling back to evidence-free model recommendations. Several writers could then
create `suggested`/`signal` rows. An apparently harmless local “Mark Executed” action
could turn those unverified records into real holdings/cash bookkeeping changes.

## 2. Investigation

The first targeted regression run passed eight cases and failed four on legacy
repository write methods. Closing only the Dashboard path would not fix optimizer,
watchlist or Deep writes. Deep persistence also ran after terminal chat completion,
which could report success before storage failed. A further review found that
Phase 1 stringified error envelopes into apparently valid research.

The browser path crossed the actual UI, background run, ReAct tool loop, structured
model adapter, consistency gate, assessment repository and Mongo. Only provider
receipts were recorded; approval/execution responses were not browser-mocked.
Storage failure is explicitly fault-injected, while replay/cancellation use the real
repository/lifecycle. The first manual transaction scenario exposed an unrelated
but acceptance-critical numeric form defect: react-hook-form watched strings, so
`typeof value === "number"` never auto-calculated the required total. Using numeric
registration fixed the user workflow rather than bypassing it through an API seed.
An early test-only search middleware also bypassed CORS; it was removed in favor of
the normal search API/provider boundary.

## 3. Root Cause

Operational success, research completeness and permission to act had been conflated.
Prompt warnings were descriptive text, not an enforced persistence contract. Legacy
read compatibility was incorrectly reused as permission for new writes. Multiple
entry points and post-completion callbacks made a UI-only correction insufficient.

## 4. Fix

- Strict `DecisionAssessment` with `actionable=false`, `action=null`, and no `ready`
  enum; drafts are separate from authoritative eligibility.
- One atomic immutable batch per source/request identity; retries compare content
  hashes, concurrent same-input writes reuse the winner, conflicting inputs fail.
- Unavailable checks, missing research/quotes and invalid proposals retain explicit
  reasons rather than inventing HOLD. No bare-model fallback when the agent is absent.
- Legacy create/upsert/batch/fill paths reject; historical reads remain unchanged.
  Associated cancelled/failed/in-progress runs project as partial research artifacts.
- Deep saves before terminal completion; persistence failure propagates. A stopped
  Dashboard run does not start another model phase once its cancellation is observed.
- Separate assessment UI and legacy statistics. Independent Add Transaction remains
  available and cannot be linked as an AI-validated order.
- Three assessment modules now have enforced critical coverage floors; the required
  hosted browser gate gains the decision-safety lane.

Local acceptance passed: backend 2100/frontend 266 tests; final-image six safety,
four Copilot, six hardening and eleven default browser cases; two equal-manifest
clean builds. The default browser lane initially ran against the wrong native
fixture (which translates recorded text); rerunning on its intended hardening
fixture restored its real assertions, without weakening them. Implementation
`75e2431779b631b74077b033544197296152c9c2` merged through protected PR #8 as
`5ce5d8a14bfbefe74e1d71968409d1502d02397d`; hosted run 35087643908 passed all
three browser lanes and quality gates. See the
[feature record](../features/investment-decision-safety-containment.md) for current
receipts and the precise remaining release conditions.

## 5. Lessons

1. Safe legacy deserialization does not imply safe new-write authorization.
2. A failed verifier cannot attest to the thing it failed to verify.
3. A denial UI needs a server-side denial and a no-side-effect assertion.
4. Preserve manual bookkeeping without pretending it proves an AI recommendation.
5. Independent provider brands, passing software tests and valid numeric geometry
   still do not establish correct facts, suitable investments or profitable strategy.
