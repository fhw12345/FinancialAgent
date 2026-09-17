---
title: Investment Decision Quality Program
status: in-progress
version: backend@0.56.0, frontend@0.37.0
last_updated: 2026-09-17
owner: maintainer
related_paths:
  - backend/src/agent/portfolio/
  - backend/src/agent/deep_workflow.py
  - backend/src/services/insights/
  - backend/src/services/pnl_service.py
  - backend/src/evals/
  - frontend/src/components/portfolio/
---

# IDQ-000：投资决策可信度与策略验证计划

> **TL;DR (EN)**: Preserve the working Agent/runtime foundation, but separate
> evidence, research, portfolio constraints, and investment outcomes. This is a
> staged program: IDQ-001-A containment, IDQ-002 risk previews and IDQ-004 sealed evidence/structured-field checks have shipped.
> It introduces no profitability claims, broker integration, or authorization to start PH-009.
>
> **TL;DR (中文)**：保留已通过工程门禁的底座，补齐“事实有依据、建议受约束、结果能验证”
> 的闭环。目前 IDQ-001-A 安全收口、IDQ-002 风险预览和 IDQ-004 封存证据/字段校验已出货；其余目标仍待实施，工程验收不代表策略有超额收益。

当前出货切片：[IDQ-001-A](investment-decision-safety-containment.md)。没有 ready、批准或
paper 执行资格。[IDQ-002](investment-portfolio-risk-allocation.md) 已出货风险数学与
非行动性配仓预览；[IDQ-004](investment-evidence-snapshots.md) 已出货封存证据与结构化字段校验（不认证全文/来源真伪）。
维护者确认顺序调整为 **004 → 005 → 001-B**，003 后移；其余任务未启动，PH-009 继续暂停。

## 1. 目标、基线与证据等级

审阅基线：`f0a5ed0e44f7f1b7ad37007976c1872249d66133`，backend `0.51.5` /
frontend `0.32.5`。[Project Hardening](project-hardening-program.md) 已完成 9/10，
**PH-009 按维护者要求暂停执行，仍为 planning；本计划不是启动其重构的许可。**

当前定位是本地单用户研究辅助系统，不是自动交易系统。成功目标：

1. 无法验证的事实不进入可操作建议；数据不足不伪装成 HOLD 或正常风险。
2. 仓位、现金、集中度等约束由代码执行，不依赖 Prompt 中的 MUST。
3. 每个研究判断能追溯到确定时点、口径和来源；多 Agent 不损失关键反证。
4. 策略规则先定义、版本先冻结，再进行前瞻评估；软件通过与策略有效分开验收。

### 已观察基线，不是未来功能验收

| ID | 当前源码／离线观察 | 影响 | 负责子计划 |
| --- | --- | --- | --- |
| B01 | 主 Phase 2 未完整消费 context 的 `max_position_pct` / `risk_tolerance` | 设置不等于真实约束 | IDQ-001/002 |
| B02 | consistency gate fail-open；标记进入 metadata，但新增 violations 未明确进入主 prompt | 质量检查不能可靠阻断建议 | IDQ-001/004 |
| B03 | 内存构造的 BUY 缺 size、entry、thesis 仍被现有 schema 接受 | 历史兼容放宽了新写入 | IDQ-001 |
| B04 | 90% 现金／10% 单股的合成样例：报告波动 0.3202，而账户加权约 0.0320 | 股票子组合与账户风险口径混淆 | IDQ-002 |
| B05 | >50 候选时，moderate 的 cap-25 ∪ momentum-25 再截前 20，样例中动量候选由 25 变 0 | 实际选股策略被排序改变 | IDQ-003 |
| B06 | Deep 报告前缀截断约 3000/6000 字符 | 后置财务内容与反证可能遗漏 | IDQ-006 |
| B07 | 过热、融资压力、降息预期混为单分数；部分缺数使用 50 等占位 | 缺数据／压力可能被解释为中性或低风险 | IDQ-007 |
| B08 | 事后方向收益、关键词 rubric 尚不是完整投资评估 | 不能据此宣称盈利能力 | IDQ-008/009 |

B03–B05 仅为不联网的内存样例，不是市场实测。B04 假设现金无波动。其余是调用链
审阅。未来实现应先把相应观察固化为失败回归测试，不把此表当作测试已经通过。

## 2. 范围与非目标

### 建议的 v1 范围（启用前需确认）

- USD 计价、可验证的美股普通股／ETF；long-only、无杠杆。
- 人工确认的投资约束；独立区分研究候选、组合建议和 paper allocation。
- 日频前瞻验证优先；复杂订单、跨币种、期权、做空均显式不支持。
- 既有研究／历史报告继续可读；新建议必须走新门禁。
- 保留 FastAPI、LangGraph、MongoDB、Redis 和既有 AgentRun/SSE 协议。

### 不做

不接券商、不下真实订单、不增加云部署／多用户权限／计费；不承诺收益；不因一个
漂亮回测自动选策略；不把所有财务研究都强制成 Fibonacci 交易；不启用无限 Agent
辩论；不以本计划名义进行全仓库机械拆分或大规模迁移。

除 [A 阶段](investment-decision-safety-containment.md) 和
[IDQ-002](investment-portfolio-risk-allocation.md)、[IDQ-004](investment-evidence-snapshots.md)
明确列出的实现外，本文 DTO、
集合、接口、文件名和阈值仍为**拟定契约**。各 planning 子计划保留 `version: n/a`；
本总计划的版本标记已出货组件的实现基线，不表示其余契约已经出货。

## 3. 目标链路与职责

```text
InvestmentPolicy + StrategySpec + ResearchRequest
                  ↓
Immutable EvidenceSnapshot + PortfolioSnapshot
                  ↓
Deterministic calculations / validated facts
                  ↓
ResearchDossier → targeted challenge → unresolved concerns
                  ↓
Strict DecisionProposal → deterministic PolicyGate
                  ↓
Post-trade portfolio checks → reviewable decision
                  ↓
Explicit human approval → isolated paper ledger
                  ↓
Matured outcome evaluation + baseline comparison
```

- LLM：解释、假设、检索计划、反证；不得自行证明数据有效、突破风险上限或执行公式代码。
- 确定性代码：数值、时间、证据引用、资格、风险预算、生命周期与账本。
- 人：选择投资约束与策略，批准 paper 动作，评审策略研究结论。
- 行情结果：检验策略；Agent 自信分不能替代真实观测。

### 跨模块共同身份

每个新决策保留：`run_id`、`decision_id`、`policy_id/version`、`strategy_id/version`、
`snapshot_id`、`portfolio_snapshot_id`、`dossier_id`、实际 Prompt/model usage、
backend version/revision/source、`as_of`、创建时间和语义 schema version。

PortfolioSnapshot还绑定account scope/ID/revision；真实持仓与不同paper实验不能混用。
记录不可偷偷重算成“当前版本”。调整策略、风险设置、数据或人工选择产生新版本／事件。
运行完成、决策可用、人工批准、paper 成交、策略被验证是五个不同概念。
HOLD通过`exposure_context/hold_reason`区分继续持有和空仓等待；WAIT只是后者的UI标签，
不另外发明交易action。批准部分建议视为新选择批次，必须重算约束。

## 4. 子计划、边界与实施次序

| 任务 | 重点 | 优先级 | 直接前置 |
| --- | --- | --- | --- |
| [IDQ-001 决策契约与硬门禁](investment-decision-policy-gates.md) | 状态、严格写入、降级、审批失效 | P0 | A 无；B 依赖 002/004/005 |
| [IDQ-002 组合风险与确定性配仓](investment-portfolio-risk-allocation.md) | 日期对齐、现金口径、交易后约束 | P0 | 001-A 公共契约 |
| [IDQ-003 候选筛选与组合适配](investment-candidate-selection.md) | 配额、稳定排序、候选与建议分离 | P0/P1 | 最终闭环依赖 002/004/005 |
| [IDQ-004 时点证据与主张验证](investment-evidence-snapshots.md) | 数据快照、PIT、引用、数值验证 | P0/P1 | 001-A 身份契约 |
| [IDQ-005 投资方法与研究模板](investment-research-strategy-contracts.md) | 期限、估值口径、失效条件、基准 | P1 | 001-A/004 |
| [IDQ-006 结构化多 Agent 研究](investment-agent-research-orchestration.md) | 覆盖率、争议状态、预算、消融 | P1/P2 | 004/005 |
| [IDQ-007 多维 Insights 风险](investment-insights-risk-dimensions.md) | 缺数状态、风险维度、方法版本 | P0/P1 | 可独立修缺数；完整引用依赖 004 |
| [IDQ-008 前瞻 Paper 账本](investment-forward-paper-ledger.md) | 审批、未来成交、现金账、企业行动 | P2 | 001-B/002/004/005 |
| [IDQ-009 研究与投资评估](investment-quality-evaluation.md) | 事实 oracle、收益基线、校准、发布门槛 | 全程 | oracle 先行；完整评估依赖 003/006/007/008 |

### 非循环的交付里程碑

1. **M0：契约冻结与 oracle**：确认政策语义、建立 B01–B05 失败测试及 IDQ-009 固定语料。
2. **M1：安全收口**：001-A 先阻止不安全新建议；002 修数学；003 修筛选；007 去假中性。
   这些可独立提交，但未接入证据链的决策只能 research-only，不能提前宣称 ready。
3. **M2：可信决策**：004 → 005 → 001-B；002 的交易后 validator 接上真实调用链。
   003 再接组合适配。至此才允许启用新的人工可审阅建议。
4. **M3：高质量研究**：006 在统一 dossier 上做有预算的补充研究与反证。
5. **M4：前瞻结果**：008 建账，009 做分层评估／消融。可以得出“策略无优势”的正确结论。

M1 不需要等待全部功能；用窄 helper/adapter 避免新行为混入机械重构。涉及已经超长的
调用文件时，只做实现本任务所必需的边界提取并满足 touched-source ≤500 行；全仓库
PH-009 仍不启动。若安全改动无法在此边界内完成，先记录阻塞并请求维护者决策。

### 文件所有权／集成规则

- 001 管模型、decision policy 和写入出口；002 管风险／配仓数学；004 管 provider
  envelope／snapshot；005 管策略与 Prompt 输入契约；006 管 Deep graph。
- 003 与 001 均涉及 `portfolio/flows.py`，必须顺序集成，不允许分别复制策略判断。
- 007 管 Insights API/UI；008 管 paper 账本；009 管 eval registry/report。
- 共同 DTO 在 001-A 先约定；各任务不得自建第二套 `ready`、时间、引用或版本语义。

## 5. 跨任务验收契约

### 安全与一致性

- 新建议通过 API、后台 Portfolio、单股、Picks 等所有入口，最后共享同一写入门禁。
- 批次先完整计算交易后状态再批准；不能逐条批准后才发现总资金超限。
- 任何调用失败、取消、超预算、陈旧审批都不能留下未通过门禁的 actionable 状态。
- Redis 仅为缓存／加速；Mongo 是 durable 记录。重试不重复模型结果、建议、审批或成交。
- 所有金额与股数有单位、精度、时点；拒绝 NaN/Infinity、负现金、非法 action/intent。
- 外部文本仍为不可信数据；不执行新闻中的指令或任意公式字符串。
- 原始用户持仓、密钥、provider URL 中的凭据不进入截图、日志 artifacts 或公共文档。

### 验证层次

1. 纯函数：已知数值 oracle、边界和性质测试。
2. 契约／组合：真实内部路由、provider adapter、gate、数据库写入；只 mock 最外层传输。
3. API：schema、错误码、幂等、乐观并发、历史兼容。
4. 浏览器：从可见按钮进入真实 API，断言中间态、终态、刷新后持久化及反例。
5. Live/paper：单独显式启用，固定预算，不进入普通 PR 的随机／付费门禁。

公共 Playwright 约定：1440×1100、禁动画、固定 UTC clock/交易日历、合成账户与录制
传输、真实 Mongo/Redis。采用稳定 test IDs；截图在断言后产生。不得 mock 整个决策
API 后宣称跨层验证。各子计划列出场景及待生成的 `assets/idq-00x/` 路径。

## 6. 通用质量门禁与证据要求

继承 [PH-004](project-hardening-ci-agent-quality-gates.md)，不降低任何现有门禁：

- Backend Ruff/Black/mypy、全量测试、关键模块 coverage floors；新决策门禁每个拒绝
  分支有测试，不能只用覆盖百分比代替业务断言。
- Frontend 全量测试、production lint 0 warnings、总 test/E2E warnings ≤131、类型与构建。
- 路由／符号 deterministic eval、repository policy、Gitleaks、Bandit、actionlint。
- 指定真实 API Playwright 和受影响的既有默认 E2E。新增选择必须写入正式脚本／CI，
  不能只保留开发者临时命令。
- Runtime/build 输入改变时更新 clean-build、依赖 manifest 与 image-only browser 证据；
  只改文档不重复宣称应用镜像已变更。
- Docker 内不运行 npm ci；复用已有镜像／依赖卷。`.env*` 改动必须 force-recreate。
- 每个实现按实施提交 → 含其 hash 的出货文档提交 → protected PR CI → push/sync。
  版本、changelog、索引、双语案例、截图和 run receipts 缺一不可。

最初的规划提交不包含实现验收。后续各子任务必须独立提供代码、版本、浏览器和
出货证据；本总计划的未勾选项不因某个组件通过 CI 而自动变成已完成。

## 7. 三种完成条件必须分开

| 层级 | 可判定条件 | 不能推导出的结论 |
| --- | --- | --- |
| 计划可执行 | 契约、owner、依赖、失败行为、test oracle 和 E2E 明确 | 功能已实现 |
| 软件出货 | 指定门禁／E2E／证据／版本／提交／合并完成 | 策略具有 alpha |
| 策略可推广 | 预注册、样本外／前瞻、适当基准、成本、误差与风险经评审 | 将来一定盈利 |

不得让“评估得出负收益／无优势”导致软件验收失败后改阈值粉饰结果。

## 8. 必须在对应阶段确认的选项

| 决策 | 建议起点 | 未确认时行为 | 最迟确认点 |
| --- | --- | --- | --- |
| 投资范围／long-only／币种 | US liquid stocks/ETF，USD，无杠杆 | research-only | 001-B |
| 最大单股／行业／现金下限／风险预算 | 用户显式填写；本文不替用户选择比例 | 不允许新增风险建议 | 001-B/002 |
| 首发策略 | 005 的中期基本面模板；短期模板独立 | 不把多周期信号混成 BUY | 005 |
| Freshness／事件窗口 | 随策略版本固定，延迟行情显式标注 | 不满足关键输入则 blocked/review | 004/005 |
| Provider PIT 能力／授权 | 无可靠 publication time 就标 unknown | 不用于严格历史验证 | 004/009 |
| Paper 成交／费用／基准 | 008 的 next-session market pilot | 不生成回测收益结论 | 008 |
| Live 调用总预算／并发 | 显式选择，不因打开页面触发 | 默认不付费执行 | 006/009 |

## 9. Program Acceptance Checklist（未来实施）

- [ ] 所有入口共用严格决策门禁，历史宽松模型只读。
- [ ] 现金、日期、单位与拟议组合约束有可复算 oracle。
- [ ] 候选筛选稳定且无截断偏置；候选不能直接绕过配仓。
- [ ] 关键数字绑定时点证据，缺失／冲突不会伪装成正常。
- [ ] 方法、期限、基准、论点失效条件明确且版本化。
- [ ] 多 Agent 不丢失重大反证；无证据的共识不标 verified。
- [ ] Insights 区分风险维度与数据完整度，无未经验证的自动买卖映射。
- [ ] Paper 账本可复算、无未来成交、无重复交易且与真实账户隔离。
- [ ] 研究质量与投资绩效分别评估；无优势也可如实发布评估。
- [ ] 子计划质量门禁、浏览器证据与出货流程全部完成。

## 10. 变更记录

- 2026-09-14：基于 Agent/投资框架审阅建立规划；所有 IDQ 任务为 planning。
  只创建文档与更新导航／handoff，未实施上述行为，也未恢复 PH-009。
