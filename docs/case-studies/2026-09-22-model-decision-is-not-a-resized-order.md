---
title: A Model Decision Is Not a Resized Order / 模型决策不能被悄悄改写
status: in-progress
version: backend@0.59.0, frontend@0.40.0
last_updated: 2026-09-22
owner: maintainer
related_paths:
  - backend/src/services/decision_policy/model_decision.py
  - backend/src/services/decision_policy/model_decision_gate.py
  - frontend/src/components/portfolio/ModelDecisionPanel.tsx
---

# A Model Decision Is Not a Resized Order / 模型决策不能被悄悄改写

> **TL;DR (EN)**: The user wanted the model to make the decision, not fill in targets
> themselves. We let the model state one explicit action and target per researched
> symbol, then run the unchanged human-review gate. Code rejects instead of resizing,
> persists the paid output before validating, and never re-calls the model on replay.
>
> **TL;DR (中文)**：用户要的是模型直接给出决策。实现上模型为每只研究过的股票给出明确
> 动作与目标仓位，再走原有的人工审阅门禁。代码只拒绝、不改写；付费输出先持久化再校验，
> 重放绝不再次调用模型。

## 1. Context / 背景

IDQ-001-B required the user to type target weights. The user clarified: the model should
decide, as a recommendation. The risk is that "helpful" code quietly turns an invalid
decision into a valid one — shrinking a position to fit a limit, or converting a BUY on
an existing holding into an ADD — so the approved batch no longer reflects what the model
actually recommended.

## 2. Design / 设计

- One structured `ModelDecisionSet`: BUY/ADD/REDUCE/SELL/HOLD, target weight, rationale,
  same-symbol evidence IDs, risks and review triggers. No quantities, prices or readiness.
- Scope is exactly the researched symbols intersected with the user-attested universe.
- A dedicated model gate checks scope, exposure vs action, action vs computed share delta,
  open/exit permissions, evidence membership, stance conflicts and policy version, then the
  full B gate runs unchanged. Every violation is a visible reason, never a rewrite.
- A per-request claim precedes the paid call; the immutable output is stored before
  validation. Inputs changing during the call fail publication; the stored decision can be
  re-validated without a second model call.

## 3. Findings / 发现

1. **Replay must not depend on current revisions.** The first version checked the control
   revision before looking up the stored decision. A legitimate replay after publication
   (which itself advanced the revision) returned 409. Replay now resolves the stored record
   first and never re-checks or re-calls.
2. **Cancellation is a failure, not "still running".** Catching only `Exception` left a
   cancelled call's claim running until lease expiry, after which a takeover would pay
   again. Cancellation is now recorded as failed through a shielded write.
3. **Scope follows research, not wishes.** Holdings research covered only AAPL in the
   recorded browser run; MSFT was correctly out of scope. Decisions cannot extend to
   symbols that were not researched in the same source.
4. **A blocked decision must say why where the user looks.** The first screenshot showed
   only "blocked"; reason codes now appear next to the model recommendation.

## 4. Verification / 验证边界

Real UI/API/graph/Mongo acceptance with only the outer Copilot transport recorded (built
from the real rendered prompt), plus deterministic unit/composition tests for every rule.
None of this shows the model's decisions are good investments — only that they are
recorded, checked and presented honestly. 这些验证只证明决策被如实记录、校验和展示，
不证明模型决策能带来收益。
