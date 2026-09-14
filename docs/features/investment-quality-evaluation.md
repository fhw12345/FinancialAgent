---
title: Research Quality and Investment Outcome Evaluation
status: planning
version: n/a
last_updated: 2026-09-14
owner: maintainer
related_paths:
  - backend/src/evals/
  - backend/src/api/evaluations.py
  - backend/src/services/pnl_service.py
  - frontend/src/pages/EvaluationPage.tsx
  - frontend/src/components/evaluation/
  - .github/workflows/pr-checks.yml
---

# IDQ-009：分层质量评估、前瞻收益与策略准入

## 1. Goal / Evidence Boundary

[总计划](investment-decision-quality-program.md) 的验证工作包，与PH-009不是同一任务。
早期提供oracle，最后整合001–008的证据。现有router/symbol deterministic eval保留；
其通过不等于研究事实准确，更不等于投资盈利。

当前live rubric部分使用字符串覆盖，unsupported_claim_rate仅匹配预设禁止表述；
旧pnl_service是方向收益。不能改个字段名就宣称新增了经济有效性验证。

本任务交付可重复、可审计且能报告负结果的评估系统；策略是否可以推广是另一个结论。
不自动调参追最好历史曲线，不执行真实交易，不在普通PR中付费调用或查询实时行情。

## 2. 三层评估对象

| 层 | 保留／新增指标 | 不能替代 |
| --- | --- | --- |
| E0 工程行为 | 路由、符号安全、生命周期、幂等、工具契约、预算 | 事实真实性 |
| E1 研究质量 | 数字/单位/期间正确、引用支持、重大反证覆盖、合理abstention | 投资收益 |
| E2 投资结果 | 净总收益、超额收益、回撤、换手、风险、概率校准 | 将来一定盈利 |

UI/API分别标 execution_mode、evidence_mode、outcome_mode，不能把fixture模式显示成
live provider/real money。旧指标维持历史定义并标legacy metric version。

## 3. E1 固定语料与真实oracle

先建立至少40个版本化的双语案例，各类至少4个：价格/单位、财务期间、估值计算、
missing/stale、conflicting evidence、重大反证、越界配仓、混合期限、prompt injection、
legacy/new-write差异。每类有正负例，关键错误标critical。

案例记录：expected claim/evidence graph、typed numeric oracle、policy/strategy/snapshot
IDs、预期action/readiness、允许/禁止工具、适用理由。标签由确定性计算和维护者审阅
确定，不让生成答案的同一个LLM独自定义标准答案。

### 指标定义

- `numeric_error_rate`：错误/必需核验的数值主张数；单位/期间不匹配同样算错。
  应有而未输出的值单列missing，不能通过少说话提高precision。
- `citation_support_precision`：真正支持对应主张的引用数/所有引用；另报recall与critical缺项。
- `material_contradiction_recall`：被正确承认/解决的重大反证数/预标重大反证数。
- `abstention_precision/recall`：该拒绝时拒绝、不该拒绝时仍能完成研究，两者都测。
- 对fact、derived、hypothesis、judgment分别评分；不把假设当事实错误，也不把事实错
  通过改名hypothesis逃掉策略所要求的数据。
- source existence、keyword match只作辅助诊断；“PE 20”出现在反驳句里不是正确事实覆盖。

### 固定PR门禁（目标）

- 所有critical cases通过；critical numeric/unit/period错误=0。
- 所有越权/注入/缺核心证据负例不能ready；所有预标重大反证被保留。
- 确定性calculator golden误差按002/005的单位容忍度；非finite值=0。
- 任何metrics NaN、空分母未标n/a、已跳过案例被计为pass都使报告校验失败。
- 新门禁有故意失败控制，验证真实CLI退出非零和artifact保留，不能只测试helper返回false。

## 4. Live 研究质量与人工审阅

显式opt-in，固定input/snapshot/prompt/model route/pricing版本和总费用/时间上限。
价格未知、预算未给、provider不可用时不运行付费路径。

- 同一case重复运行，报告成功率与变异，不挑最好一次。
- LLM judge只评定性维度，数值和政策由代码oracle验证。
- 报告judge与人工标签的一致性；盲化agent/model名称及实验组，防偏好长答案。
- 报错/超时/拒绝/预算停止全计入分母并分原因；不只对成功答案计算漂亮均值。
- 不以judge分数自动修改policy或策略、批准paper或改变默认路由。

006 A/B/C消融要预注册primary metric、资源预算、样本和比较方法。同资源与默认产品预算
分开报告。若C只更长/更贵而无关键错误下降，默认保持轻路径。

## 5. E2 前瞻结果与历史污染

主要依赖 [008 paper账本](investment-forward-paper-ledger.md)。每次预测/决策在结果发生
前封存。历史PIT回放只作补充：pretrained LLM可能记得后来发生的事情，即使工具只给
当时数据，也不能保证没有未来知识污染。匿名化/截断不是无污染保证。

必须披露：

- 决策注册时间、输入可知时间、model/version/知识污染限制；
- universe membership和delisted覆盖；不能只保留存活股票/实际BUY赢家；
- 数据修订、split/dividend与可成交性假设；
- 训练/验证/测试的时间分隔；重叠预测用purge/embargo或合适的时间块方法；
- 改过的策略/参数数量及选择过程，不能隐瞒多次试验。

评估模式明确 `fixture_replay`、`historical_pit`、`prospective_paper`；无broker模式。

## 6. 收益、风险和预测指标

### 策略级

- portfolio NAV total return、扣费用/滑点净收益；现金收益假设单列。
- 同期预注册市场/行业/现金和简单规则baseline的超额收益；不得结果出来后换benchmark。
- 最大回撤/恢复期、年化波动、turnover、exposure/concentration、成本占收益比。
- Sharpe等只在足够长度且方差有定义时给值，否则n/a；不从几天收益夸张年化。
- 收益归因区分市场/行业暴露与选股；高beta跑赢SPY不直接称alpha。
- 标明gross/net/未成交比例/缺mark覆盖、评估窗口和有效独立时间块数量。

### 预测级

- 先定义可观测事件，再做Brier/可靠性图；不能把confidence 8当80%。
- 概率事件必须互斥完备并有同一horizon，例如相对基准收益区间；目标价的三个离散点
  不自动成为可评分事件分类。主观情景无可判定事件时不评分。
- 价格分位预测用pinball loss、interval coverage及width，不套分类准确率。
- 未到期=unmatured；因缺数据无法判定=unscorable；两者都不能计作成功或失败。
- 同日同板块多只股票不是独立样本；置信区间按时间块/聚类处理。

## 7. 策略研究结论与准入（不等于软件status）

实验状态：`not_evaluated`、`insufficient_sample`、`evaluated_no_edge`、
`candidate_for_review`、`rejected`。不会因为UI功能shipped就把策略标validated。

实验激活前必须固定sample plan（样本量/独立时间块/到期条件）、primary benchmark、
primary metric、费用、风险上限、允许变更和多重比较处理。未登记这些字段就不能
输出candidate_for_review。

建议严格准入规则：到期/数据覆盖/样本计划均满足、无critical数据泄漏、风险与成本
限制未破、预注册的净超额收益不确定区间支持优势，且完成维护者审核。置信水平和
方法在实验前固定（例如95% block-bootstrap interval），不是看结果再调。

即使满足也只称“值得进一步观察”，不承诺未来盈利。未显示优势是合法、重要的结果；
不能降低阈值、删除坏样本或重置实验来把negative改成pass。

## 8. API、报告与实施切片

扩展现有Evaluation页面/API，新增suite/metric schema版本而非覆盖历史。
report包含requested/completed/failed/skipped/unmatured/unscorable counts、每个指标的
分子分母/定义、baseline、manifest hash、实际usage/cost、CI或手动run identity。
JSON与Markdown导出同源；分页history不能现场重算旧报告。

- [ ] 建40-case E1 corpus和数值/引用/abstention oracle；先服务001–007测试。
- [ ] 将keyword diagnostics与事实验证分开命名；保留历史metric定义。
- [ ] 加live blind审阅/消融报告、费用与失败对账。
- [ ] 接008 immutable ledger和005预测事件，建立收益/风险/校准函数。
- [ ] 加sample sufficiency与strategy review状态；UI明确研究结果不是买卖指令。
- [ ] 接CI fast deterministic lane；重型/付费/前瞻job保持显式opt-in。

## 9. 验证矩阵

拟新增 `test_research_quality_oracles.py`、`test_investment_evaluation_metrics.py`、
`test_investment_evaluation_governance.py`。

| ID | Fixture | Oracle |
| --- | --- | --- |
| QE-01 | 引用ID真实但数值/期间错误、只复制关键词 | E1失败，不能靠source存在通过 |
| QE-02 | 一例critical失败被大量普通成功稀释 | 全suite门禁失败 |
| QE-03 | 发布数据晚于cutoff/当前membership回填 | leakage标志，不能strict PIT或candidate_for_review |
| QE-04 | NAV [100,110,88,100] | 最大回撤20%；总收益0%；不能用均值掩盖回撤 |
| QE-05 | 008的固定fee/slippage账本 | net PnL=$95.90，gross/net明确，独立重算一致 |
| QE-06 | 二元预测p=0.8、y=1 | Brier=(0.8-1)^2=0.04；confidence=8不被转换后评分 |
| QE-07 | 恒定NAV／空结果／未到期／缺mark | 对应n/a/unmatured/unscorable，无NaN和虚构通过 |
| QE-08 | 策略亏损或落后benchmark | 显示负结果/evaluated_no_edge，不失败重跑挑赢家 |
| QE-09 | 同一snapshot/model，A/B/C有不同usage | 质量/成本/latency独立展示，不把多token称策略提升 |
| QE-10 | 修改primary metric、样本计划或benchmark | 新实验版本；旧结论不变 |
| QE-11 | report保存/导出失败、重试/reload | 无假已保存；成功后JSON/Markdown/history身份一致 |
| QE-12 | 故意引入numeric/evidence错误 | 实际CLI非零、CI required job失败并保留reports |

### Playwright

拟新增 `frontend/e2e/idq-investment-evaluation.spec.ts`：

- `idq-009-three-evaluation-layers`：真实API启动固定suite，UI分别显示E0/E1/E2，无paper
  样本时显示insufficient_sample；不能全绿冒充盈利。截图 `assets/idq-009/01-evaluation-layers.png`。
- `idq-009-negative-result-persists`：载入合成亏损paper账本，运行评估、导出、reload；
  负超额收益/费用/基准保持不变，无“投资成功”标签。截图 `assets/idq-009/02-negative-result.png`。

## 10. Acceptance / Rollback

- [ ] QE-01…12、真实API E2E、故意失败门禁和总计划质量流程完成。
- [ ] 每个指标能由冻结manifest/ledger复算，缺失与未到期样本不被藏进分母。
- [ ] Live费用／失败／变异如实计入；普通PR无付费调用。
- [ ] 三层报告及策略研究状态不会混淆；无alpha仍可验收软件功能。
- [ ] 版本、截图、changelog、双语案例、protected PR和artifact receipts齐全。
- [ ] 回滚新增计算/实验启动而保留已生成报告和定义，不删除不利结果。
