---
title: Approval Is Not a Fill / 批准不是成交
status: shipped
version: backend@0.58.0, frontend@0.39.0
last_updated: 2026-09-18
owner: maintainer
related_paths:
  - backend/src/services/decision_policy/
  - backend/src/models/decision_review.py
  - frontend/src/components/portfolio/PaperReviewPanel.tsx
---

# Approval Is Not a Fill / 批准不是成交

## TL;DR (EN / 中文)

**EN:** A human-review button needs an atomic eligibility boundary, not a toggle on an
AI assessment. Freeze inputs, validate the actual subset, fence concurrent mutations
and time expiry, and preserve the distinction between approval and any trade/fill.

**中文：** 人工批准不是把 AI 的 false 改为 true。必须绑定输入、复算所选子集，
在同一原子边界阻断账户并发写入和到期竞态；批准仍不是交易或模拟成交。

## Context / 背景

IDQ-002/004/005 supplied risk math, sealed structured evidence and explicit research
contracts. None made an AI assessment executable. IDQ-001-B's approved first scope is
**user-entered target weights**, deterministic human-paper-review eligibility and a
separate approval record. Numeric limits, peers, costs, strategy activation and target
weights remain the user's decisions, not coding-agent defaults.

已有风险计算、封存证据和研究契约不代表可以买卖。首版由用户明确填写目标权重，
代码复算数量与全账户限制；人工批准仅是一条审阅记录，不是券商指令或模拟成交。
真实交易的独立手动记账继续存在，且不得冒充 AI 验证。

## Architectural Boundary / 架构边界

A naive approval implementation checks several collections, then inserts an approval.
An account or policy edit between those steps makes a stale approval look current.
Standalone Mongo cannot be assumed to support multi-document transactions.

The implementation uses a shared `review_control` aggregate. Supported input writes
announce a persistent mutation ticket before touching holdings/settings/policies and
advance its world revision. Prepared immutable receipts become authoritative only when
a CAS on that same aggregate publishes their hashes against unchanged revisions,
generation and idle state. A newer review supersedes the previous current pointer;
old receipts remain readable but do not remain eligible. Approval re-runs the exact
selected subset: an unapproved sale cannot supply cash-floor or concentration headroom.

“先检查多个集合、再写批准”存在竞态。共享控制文档记录输入修订、在途写入票据、
当前提案与批准事件；最终 CAS 才是发布边界。账户变动要么先发生而阻断 CAS，
要么后发生并立即让当前资格失效。失败或孤儿准备记录不能成为 ready。
不自动超时清理未知写入票据；异常账户需要明确核对，在途票据不能 HTTP 强制解锁。

## Review Findings / 审查发现

1. **No error is not a positive check.** Old assessments did not persist an explicit
   passed consistency attestation. B adds one for new records; legacy/Deep receipts
   without it cannot be silently backfilled into ready.
2. **Time also races.** A valid check can expire during storage delay. The final Mongo
   CAS compares `$$NOW` with the immutable expiry, capped at the next XNYS close.
   Application-time prechecks alone are not enough.
3. **A monitoring rule is not a valuation-method requirement.** Debt/FCFF monitoring
   previously depended on selecting DCF. Shared typed proxy arithmetic now checks the
   debt rule without forcing a second valuation estimate.
4. **Target sizing is not a stop-loss plan.** This target-only pilot enforces sigma,
   position/sector/cash/turnover constraints; it explicitly does not apply an absent
   stop-loss plan or claim the preview stop-risk budget as a maximum-loss bound.
5. **Finite operands do not ensure a finite result.** Final diff review reproduced
   `1e308 + 1e308 → infinity`, then `net_debt / infinity → 0`, falsely passing the
   peer-PE-only debt monitor. A red real-gate regression produced ready. The shared
   FCFF helper now rejects nonfinite arithmetic before either monitoring or valuation;
   pre-correction images are excluded and final builds/browser proof are rerun.
6. **An HTTP failure is not always browser-visible as a response.** An injected unhandled
   storage fault can surface through CORS as a network error. The browser test checks
   its failure state, independently observes the real API's 500, and proves no record
   was published. It does not replace the tested result with a browser mock.

审查补强了“明确检查通过”与“没有异常”的区别，以及数据库保存期间跨越有效期／
交易日收盘的竞态。债务监控和 DCF 估值解耦，但仍保留同样的单位、财年、符号和
正分母检查。前端明确说明没有止损或最大亏损保证。最终审查还复现了有限操作数相加溢出后，
债务比率假装为 0 的问题；共享计算函数现已拒绝非有限结果，旧镜像被排除并全量重验。存储故障的测试既检查真实 API
失败，也检查 UI 未宣称成功，而不是依赖可能被 CORS 隐藏的响应事件。

## Verification / 验证边界

Tests run real gates/calculators and the real UI/API/graph/Mongo path. Only synthetic
outer model/provider data, deterministic clocks and explicit storage fault injection
are substituted. The recorded Mongo clock changes only the clock operand: Mongo still
executes the actual deadline/revision/generation/ticket comparison.

Positive acceptance must show ready → explicit subset approval with byte-equivalent
structural holdings/cash/transaction counts and no additional model call. Negatives
cover missing facts/checks, stale versions, omitted-sale subsets, concurrent writes,
cancellation, corrupted preparations and delayed expiry. Independent manual recording
then invalidates current approval without deleting its historical receipt.

Post-review validation passed **2286 backend / 275 frontend tests**, all critical/strict gates,
**43 final-image browser cases**, repeat equal-manifest/source builds C/D and real recreation
persistence. Curated screenshots and receipts are linked from
[the feature](../features/investment-decision-review-gates.md). Protected PR #16 merged
implementation `2ced1281b5de87efec0931a220232983fa92d054` as
`2b8abddd54e3d4dc4f140956642fe5207ae3f99a`; hosted run 35345193633 passed all gates and
seven browser lanes. Downloaded ZIP/report hashes were verified. The accepted images
are live with independent credentials/routing/account state preserved and all personal
review settings still unconfigured. None of these engineering results proves investment
effectiveness.

通过工程与合成回放验证，只能说明指定规则及失败边界得到执行；不能说明来源绝对
正确、自由文本已核实、历史 PIT 已成立、预测已校准或投资会盈利。未配置的真实账户
仍保持未配置，不通过本次开发替用户开启策略或填入个人参数。
