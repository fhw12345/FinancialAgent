---
title: Investment Decision Contracts and Policy Gates
status: shipped
version: backend@0.58.0, frontend@0.39.0
last_updated: 2026-09-18
owner: maintainer
related_paths:
  - backend/src/models/trading_decision.py
  - backend/src/agent/portfolio/flows.py
  - backend/src/agent/portfolio/phase2_decisions.py
  - backend/src/agent/portfolio/consistency_gate.py
  - backend/src/api/portfolio/decisions.py
  - frontend/src/components/portfolio/DecisionTracker.tsx
---

# IDQ-001：严格决策契约与确定性门禁

## Current Delivery Boundary

[IDQ-001-A](investment-decision-safety-containment.md) 已于 0.54.0/0.35.0（PR #8）
出货安全收口；[IDQ-001-B](investment-decision-review-gates.md) 现于 **0.58.0/0.39.0**
通过受保护 PR #16 出货人工目标权重审阅。实施提交 `2ced1281b5de87efec0931a220232983fa92d054`，
合并 `2b8abddd54e3d4dc4f140956642fe5207ae3f99a`，CI 35345193633 全绿。

A 的研究评估与旧订单仍不可批准或执行。B 是独立的 `review-policy` / `review-batches`
契约：用户明确填写目标权重，代码复算证据、研究契约和完整账户／实际批准子集；
同一控制文档的 CAS、写入票据与数据库到期检查阻断陈旧批准。接入 002/004/005 不会
自动配置任何个人参数，也不把已有研究升级为 ready。

**出货范围是 manual-target、forward daily-close、human paper review。** 不提供自动配仓、
止损／最大亏损保证、历史 PIT 认证、来源真伪／自由文本认证、模拟成交或真实执行。
现有账户风险／研究／审阅政策均保持未配置。完整契约、限制及验收证据以 B 子文档为准；
本父计划的 broader investment/ledger 目标不代表获准开启 IDQ-008 或 PH-009。

## 1. 目标与根因

[总计划](investment-decision-quality-program.md) 的 P0 安全边界。原审阅基线的 Prompt 有许多
MUST，但历史兼容 schema 曾允许新 BUY 缺少价格／size／research，consistency gate 曾
fail-open，主研究不可用时曾存在无正常工具证据的 LLM shortcut。A 已关闭这些写入旁路。

目标不是让 LLM 更听话，而是让任何 LLM 输出都不能绕过新建议的确定性写入出口。
旧报告继续可读，但“能反序列化”与“允许成为新建议”是不同资格。

## 2. Scope / Ownership / Dependencies

- A 阶段：共同身份、状态、legacy read adapter、入口清点与不安全路径收口。
- B 阶段：接入 [002 风险](investment-portfolio-risk-allocation.md)、
  [004 证据](investment-evidence-snapshots.md)、[005 策略](investment-research-strategy-contracts.md)
  后开放 ready；前置未就绪只能 research-only。
- 实际小模块：`models/decision_assessment.py`、`models/decision_review.py` 与
  `services/decision_policy/`。所有 touched source ≤500 行；只窄提取持仓测试 fixtures，未启动 PH-009。
- 不改券商／权限架构；不增加 override 来跳过 critical gate；不重写全部 Portfolio flow。
- 约束AI建议和paper批准，不阻止用户登记已经发生的真实交易；手工记录不能被标成
  通过AI门禁，且相关账户变动应使该账户的旧建议失效。

## 3. 契约语义（B 的实际字段／范围以子文档为准）

### InvestmentPolicy（用户确认、不可变版本）

`policy_id/version`、`confirmed_at`、`base_currency`、`universe_id`、`long_only`、
`allow_leverage=false`、`max_position_weight`、`max_sector_weight`、`min_cash_weight`、
`max_turnover`、`risk_budget`、允许的 strategy versions。

权重统一为总账户 equity 的 `[0,1]` 小数，不再混用 `% of cash`。旧
`max_position_pct` 不直接沿用为新政策；必须让用户确认语义与数值。无政策确认时，
允许读研究，不允许新增风险建议。

### 输出分层

1. `ResearchProposal`：模型输入／输出及证据引用；不拥有 ready 权限。
2. `DecisionAssessment`：服务端计算状态、拒绝原因与 evidence/risk receipts。
3. `ValidatedDecisionBatch`：通过整个批次交易后检查的结果，不是逐条孤立批准。
4. `ReviewApproval`：人工批准且绑定所有版本；不是成交记录。

共同字段遵循总计划。额外字段包括 `schema_version`、`batch_id`、`action`、`intent`、
`exposure_context=held|flat`、`hold_reason=maintain|wait`、
`target_weight`、`current_weight`、`delta_weight`、`horizon`、`strategy_checks`、
`policy_checks`、`data_checks`、`expires_at`、`supersedes_id`。
`portfolio_scope`必须明确local_holdings或指定paper_experiment；不同账户的snapshot不可
互换。同一研究可复用，但批准到另一个账户前必须重新生成与其绑定的proposal。

- action 仅 BUY/SELL/HOLD。A draft 保留 open_long/close_long/hold；B 根据持仓及
  舍入后数量差明确区分 open_long/add_long/reduce_long/close_long/hold，不引入 short。
- BUY/SELL 必须有策略所要求的研究和价格计划／计算引用；size 由 002 计算，不相信
  模型自行指定股数。HOLD 不强制虚构 entry/stop/target；flat+wait在UI显示WAIT，但不是
  新增可交易action。held+maintain与flat+wait在008/009中分别评估。
- long-term reduction 不伪装成 short entry；执行价格计划与研究目标价分别存储。
- 数字必须 finite；金额／股数使用明确精度，禁止 JSON NaN/Infinity。
- 新 DTO `extra=forbid`；LLM 返回 `status=ready` 不能赋予资格。

### 状态不是交易动作

| `readiness` | 含义 | 可人工批准 paper？ |
| --- | --- | --- |
| research_only | 仅研究／政策未确认／新依赖尚未接好 | 否 |
| insufficient_evidence | 核心事实缺失、时点未知或无法复算 | 否 |
| needs_review | 可展示争议／已有判断已陈旧，必须重新检查 | 否 |
| blocked | 违反硬政策、非法方向、无可靠账户状态 | 否 |
| ready | 当前快照与版本下所有必要检查通过 | 是，但批准时再检查 |

无结论时 action 可以为空；不得用 HOLD 掩盖基础设施失败。run operational status 与
readiness 独立：一次正常结束的研究可以产生 blocked assessment，UI 不能把它显示成
“投资建议成功”。模型／存储故障仍按既有 AgentRun 错误语义处理。

## 4. Gate 决策表与优先级

| 输入／故障 | 必须产生的结果 | 禁止行为 |
| --- | --- | --- |
| symbol 不属于授权 universe／不属于本次请求 | blocked + `SYMBOL_NOT_AUTHORIZED` | 模型换一只股票继续 |
| BUY 缺核心估值输入或关键报价过期 | insufficient_evidence + 明确 field IDs | 推测价格／补中性值 |
| SELL 大于实际持仓／出现 short intent | blocked + `UNSUPPORTED_EXPOSURE` | 以“减风险”为由放行 |
| 超单股／行业／现金／turnover 上限 | blocked 或重新生成可验证的新批次 | 静默截断后保留旧解释 |
| gate 模型超时／校验未完成 | needs_review + `CHECK_UNAVAILABLE` | `passed=True` |
| 发现重大矛盾／证据不支持数字 | insufficient_evidence / blocked，保留具体原因 | 仅存 warning 仍 actionable |
| Portfolio Agent 不可用 | research_only 或运行失败 | 无数据 shortcut 出 BUY/SELL |
| 用户取消／budget exhausted | 无新 ready／approval／paper fill | 把已有 partial 升级为最终建议 |
| 持久化失败 | 失败响应、可重试 | 返回建议已保存／已批准 |

多个原因全部保留；展示主状态按 blocked → insufficient_evidence → needs_review →
research_only → ready。必要检查清单由 strategy/policy 固定，非关键新闻缺失可以显式
降级但不必阻断；缺失程度由代码字段决定，不由模型自行豁免。

## 5. 实施步骤

- [x] 入口清点：holdings、picks、single-symbol、legacy optimizer、chat/Deep verdict
  的持久化及导出；区分非交易研究与可操作建议。
- [x] 固化“空 BUY 被接受”的失败测试；保留 legacy reader 的正例。
- [x] 实现状态、reason codes、版本身份与单一 `assess_and_persist` 出口。
- [x] 移除／封锁无证据 shortcut 的 actionable 资格；接入 gate 的明确失败状态。
- [x] 将 004 的引用验证与 002 的整批交易后检查接入，不以 `_format_analyses` 的文字
  warning 替代真实 guard。
- [x] 用独立 assessments / review-batches API 分离研究、审阅与 legacy 指标，而非混入旧 decisions。
- [x] 实现人工批准接口与 stale check；更新 DecisionTracker、研究面板和错误提示。

## 6. API、持久化与并发

- 既有 decisions/assessments 保留原文与不可执行语义，不混入新审阅状态。
- 实际使用 `GET/POST /api/portfolio/review-batches`、GET `/review-batches/{id}` 与
  POST `/review-batches/{id}/approve` 或 `/cancel`；旧 decisions/assessments approve 始终拒绝。
  ReviewApproval 只是人工审阅记录，尚无 paper fill 消费者。
- approve 路径绑定 batch ID；请求含 `request_id`、selected symbols、
  `expected_revision` / `expected_generation` 与明确确认。服务端绑定完整 receipt hashes。
  单股批准按one-item batch处理；批准子集时重新计算
  所选批次，不能沿用包含未获批准SELL的整批风险receipt。
- 服务端重新取 authoritative 状态；冲突返回 409 `review_revision_changed`，不自动批准新版本。
- schema 非法返回 422；有效但被拒绝的研究可作为 assessment 读取，不能计为 ready。
- decision batch 和 approval 的 durable 写入必须幂等。用唯一键、CAS 和显式提交标记；
  不假定本地 standalone Mongo 支持多文档事务。未完整提交的批次不可被消费。
- 已持久化／已受理请求的相同 ID 与内容复用结果；不同 payload 返回 409。
- 审批后政策变化使当前审阅资格失效，但历史不改写；读取只投影 stale，用户显式重提案
  才创建新校验回执。批准本身没有执行资格。
  政策变更、审批与消费必须有共同的revision/CAS协调点；仅先查policy再写另一个集合
  不是原子校验。实施前选定单文档aggregate或有序事件方案并做竞争测试。

## 7. 已执行验证矩阵（A + scoped B）

A 的安全契约／持久化／调用链测试保持；B 使用 `backend/tests/test_review_*.py`、
真实 review API/存储/计算器组合与前端确认表单测试。2286 backend / 275 frontend
全量测试、关键覆盖率及严格质量门禁通过。具体范围与回执见 B 子文档。

| ID | Given / When | Then：可判定 oracle |
| --- | --- | --- |
| DP-01 | legacy BUY 无 price/size | reader 可读，legacy=true；新 writer 拒绝；无 ready row |
| DP-02 | 所有关键字段有效且限额恰好等于上限 | 通过；上限 + 最小可表示量拒绝 |
| DP-03 | 伪造 evidence ID／错误单位／跨 run ID | 拒绝，原因精确指向对应字段 |
| DP-04 | consistency timeout、模型结构化错误 | check unavailable；actionable count=0 |
| DP-05 | pa 缺失、partial research、quote stale | 不调用无证据 recommendation shortcut |
| DP-06 | 两个 BUY 单独合规、合起来现金／行业超限 | 整批不能 ready，不能部分写成 approved |
| DP-07 | approve 与政策变更／取消并发 | 至多一个合法结果；旧版本不能生成 paper fill |
| DP-08 | Mongo 写入错误后重试同 request | 首次失败；恢复后唯一记录，无假成功 |
| DP-09 | 任一入口／导出传入假 `ready` | 公共 gate 重新计算，不信任调用者状态 |
| DP-10 | 合规批次含SELL+BUY，用户只批准BUY | 重新检查子集；不能使用未批准SELL的现金/风险空间 |
| DP-11 | 用户登记真实交易后旧AI建议被批准 | 手工登记正常；旧建议stale；手工记录不标AI validated |

### Playwright

实际脚本为 `frontend/e2e/decision-safety.spec.ts`（六例）与
`frontend/e2e/decision-review.spec.ts`（六例），使用真实 UI/API/graph/Mongo。
覆盖缺证据、legacy 只读、ready→人工批准且账本不变、独立记账后 stale、拒绝子集、
账户／到期竞态和持久化失败。全回归共 43 个最终镜像场景；截图分别见
[A evidence](assets/idq-001-a/01-insufficient-evidence.png) 与
[B approved](assets/idq-001-b/01-approved-review.png)、
[B stale](assets/idq-001-b/02-stale-approval.png)、
[B subset](assets/idq-001-b/03-rejected-subset.png)。

## 8. Acceptance / Rollout / Rollback

- [x] DP-01…11 对应契约／组合测试及上述真实 browser 场景通过；无模型／legacy 写入旁路。
- [x] A 阶段只收口安全；B 阶段必要依赖未齐全时绝不输出 ready。
- [x] 全量质量门禁、截图、版本、changelog、双语案例、受保护实施合并与出货记录齐备。
- [x] A 研究记录从不作为行动资格；B 新提案强制校验，不能用 shadow/legacy 绕过。
- [x] 回滚仅停止新批准并保留历史；不能恢复静默放行的旧写入出口。

最大风险是误阻断和历史兼容破坏。用显式 reason codes、strict-write/legacy-read 分离和
非关键字段策略降低误阻断，不用 fail-open 消除错误提示。
