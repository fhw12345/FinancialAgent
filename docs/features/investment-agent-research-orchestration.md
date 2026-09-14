---
title: Structured Agent Research and Bounded Adversarial Review
status: planning
version: n/a
last_updated: 2026-09-14
owner: maintainer
related_paths:
  - backend/src/agent/deep_workflow.py
  - backend/src/agent/debate_types.py
  - backend/src/agent/deep_react_agent.py
  - backend/src/agent/subagent_invoker.py
  - backend/src/agent/subagents/
  - backend/src/evals/model_budget.py
---

# IDQ-006：结构化研究交接、有预算的反证与消融验证

## 1. 根因与目标

[总计划](investment-decision-quality-program.md) 的Agent编排工作包。当前Deep按技术、
新闻、财务拼报告，再截前3000/6000字符；关键后置领域和追加辩护可能不进入裁决。
多模型重复同一条新闻不是独立验证，合并Concern/Rebuttal也不能直接命名为verified facts。

目标：跨阶段保留重大证据与争议；按任务需要升级研究；用实际边际收益决定是否增加辩论。
前置：[004](investment-evidence-snapshots.md)、[005](investment-research-strategy-contracts.md)。
不更换LangGraph，不增设无限自治“投资委员会”，不启动PH-009全局拆分。

## 2. ResearchDossier 契约

消费004的不可变dossier，至少包含：

- symbol/instrument、研究问题、policy/strategy/horizon/snapshot IDs；
- 各required领域的coverage和缺数原因；
- claims及其fact/derived/hypothesis/judgment类型与verification；
- thesis、supporting/contradicting evidence、重大assumptions；
- concerns（唯一ID、materiality、challenged claim IDs、evidence IDs）；
- response（承认/反驳/补证）、resolution与仍未解决的原因。

Markdown是展示视图，不是后续节点读取全部事实的唯一载体。所谓“verified”只由004的
验证决定，不能因双方达成一致而设置；模型裁决最多是agreed interpretation。

## 3. 节点与交接规则

1. **Planner**：从策略决定required domains；按纯技术用户请求可以缩小研究，但不能
   输出需要基本面证据的投资结论。
2. **Evidence acquisition**：受控工具、统一snapshot；相同事实优先共享，不为角色独立
   重复联网。要验证来源独立性，记录原始文档，而非仅比较provider名字。
3. **Specialists**：输出typed findings/claim IDs；不自行修改portfolio policy或其他角色结果。
4. **Challenger**：优先挑战影响决策的假设、数字和替代解释，不要求每轮凑固定数量反对意见。
5. **Resolution**：每个material concern得到支持、反驳、承认或unresolved状态。
6. **Synthesis**：所有required领域、重大concerns和反证必须被显式考虑；缺失进入001。

### 上下文预算

- 删除 `report[:3000]` 等按前缀决定知识覆盖的方式。
- 先放策略约束、重大风险/反证和required domain摘要，再放次要细节。
- 截断只影响展示/非关键文本，记录被省略claim IDs；不能省略未解决material concern。
- 预算不足以表达核心dossier时返回insufficient_evidence/needs_review，不继续“完整裁决”。
- 每轮都收到上轮争议和response，不只再次读原始报告前缀。

## 4. 升级、停止与成本

默认rule-first routing保留。Deep可由明确用户请求或material conflict触发；常规单股
查询不自动付费多轮。显式请求也不能突破预算和工具权限。

- RunBudget统一记录最大wall time、input/output tokens、费用、model/tool calls、每领域
  并发、retries；router、rebuttal、judge、summary、translation都计入或明确分项受限。
- 复用既有budget/progress原语或提取共享小边界，不能复制两套口径。
- 调用前预留最大可能费用、调用后结算；失败调用计费也记录；价格未知则不启动付费调用。
- 并发预算预留必须原子； cancellation取消所有子任务并等待cleanup，不能晚到结果改终态。
- 有限并发独立研究，但provider限流、共享cache和request-local状态有组合测试。
- 达到硬上限必须停止；无新material evidence且争议状态无变化时也停止，并保留unresolved。
- 不把“没有继续辩论”当作观点已被证明；stop reason持久化并展示。

## 5. 消融实验预注册

由 [009](investment-quality-evaluation.md) 执行，同一冻结语料和证据比较：

- A：单Agent；B：多领域研究无辩论；C：多领域＋定向反证。
- 固定input、model route/version、工具权限、data snapshot和各自预算。
- 同时报告equal-resource实验与product-default实验，避免用更多token赢得不公平比较。
- 主要质量指标：critical numeric errors、material contradiction recall、claim support、
  可复算字段、正确abstention；另报成本/latency和judge-human agreement。
- 不用字数、格式完整或LLM自信分衡量Deep是否更好。
- 没有可靠改进则保留轻路径，Deep可作为明确标注的opt-in；不能因本功能实现而默认升级。

## 6. 持久化、API与实现步骤

复用AgentRun与标准SSE，不新建独立执行状态机。新增事件payload使用既有seq/run_id：
coverage、concern resolution、budget progress、research stop reason；终态持久化后再发
对应最终事件，reload与replay不能增加模型调用。

- [ ] 将长技术前缀/后置财务关键反证写成失败回归。
- [ ] 建typed dossier-to-node inputs和coverage validator。
- [ ] 接concern状态转换，去除“合并=verified”的隐含语义。
- [ ] 接统一budget、bounded concurrency和cancel/failure compensation。
- [ ] 更新Prompt registry版本与实际usage，兼容旧Markdown报告读取。
- [ ] UI显示缺失领域、未解决争议和停止原因；不要只显示“多轮完成”。

## 7. 验证矩阵

拟新增 `test_research_dossier_coverage.py`、`test_deep_budget_composition.py`、
`test_deep_concern_lifecycle.py`。

| ID | Fixture | Oracle |
| --- | --- | --- |
| AR-01 | 技术报告>6000字符，财务尾部有致命debt covenant反证 | critic/judge收到该claim ID；不能因位置被删 |
| AR-02 | 多篇转载共享同一原始filing | evidence独立来源计数=1，不=角色/转载数 |
| AR-03 | 辩护承认错误，下一轮开始 | 下一轮看见承认；不再把原错误当verified fact |
| AR-04 | 没有新增证据、重复concern | 在固定停止规则内终止，unresolved仍保留 |
| AR-05 | 缺required domain或snapshot seal失败 | 无完整ready裁决；覆盖缺口可见 |
| AR-06 | 两个并发调用争用只够一个的budget | 至多一个预留成功；已付费失败不丢usage |
| AR-07 | stop时子Agent/tool尚在运行 | 全部取消/清理；无late terminal overwrite/新suggestion |
| AR-08 | 多run同symbol、不同policy/context | 无singleton污染，concern与cache按run隔离 |
| AR-09 | 恶意新闻要求扩大工具权限／买入 | 权限和policy不变；内容只被当作数据 |
| AR-10 | 旧报告reload/new report导出 | 旧report不补verified；新版本/usage/stop reason一致 |

### Playwright

拟新增 `frontend/e2e/idq-research-orchestration.spec.ts`：

- `idq-006-material-counterevidence`：真实Deep路由＋录制传输，展开研究coverage，确认
  后置财务反证在最终解释中存在且未解决状态正确。截图 `assets/idq-006/01-counterevidence.png`。
- `idq-006-budget-stop-reload`：预算或Stop触发终态，UI显示停止原因，刷新不续跑，API/Mongo
  无ready建议。截图 `assets/idq-006/02-budget-stop.png`。

## 8. Acceptance / Risks / Rollback

- [ ] AR-01…10、两类E2E及总计划质量门禁通过。
- [ ] 重大concern覆盖100%；任一漏项使固定语料门禁失败。
- [ ] 实际预算和所有调用usage可对账，无假免费／无无限重试。
- [ ] 有A/B/C实验报告；默认路由是否升级由结果评审决定，不能按功能完成自动升级。
- [ ] 截图、版本、changelog、双语案例、run receipt、protected PR完成。
- [ ] 回滚Deep新路径到受控单研究路径；不得绕过001/004，新dossier仍可读取。

模型可能同质化、judge可能偏爱长答案、并发可能加大provider压力。用独立来源身份、
blind评审、同预算比较和有界并发减轻，不用增加更多角色掩盖问题。
