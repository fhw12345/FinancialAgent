---
title: Candidate Selection and Portfolio Fit
status: planning
version: n/a
last_updated: 2026-09-14
owner: maintainer
related_paths:
  - backend/src/agent/portfolio/universe_filter.py
  - backend/src/agent/portfolio/flows.py
  - backend/src/data/sector_universe.py
  - backend/src/models/portfolio_analysis.py
  - frontend/src/components/portfolio/AnalysisButtons.tsx
---

# IDQ-003：无偏候选筛选与组合适配

## 1. Context / Scope

[总计划](investment-decision-quality-program.md) 的候选工作包。当前 moderate 把市值
组排在动量组前，再被 Phase 1 的20个上限截断；≤50候选时也会直接返回原序列。
`risk_tolerance` 只是粗筛标签；Today’s Picks 使用空持仓并按 LLM confidence 选 BUY，
不能把结果说成适合用户现有组合的配置。

目标：可复现地发现候选，保留筛选意图；只有经过真实 portfolio fit 和
[001](investment-decision-policy-gates.md)/[002](investment-portfolio-risk-allocation.md)
才可变成可审阅建议。并依赖 [004](investment-evidence-snapshots.md) 的时点数据和
[005](investment-research-strategy-contracts.md) 的策略/基准。

不引入机器学习选股器，不承诺大市值=低风险、近期涨幅高=高收益，不扩大到期权/做空。

## 2. 两种产品语义

| 输出 | 使用账户持仓？ | 是否可批准？ |
| --- | --- | --- |
| ResearchCandidate | 可以独立发现；显示尚未评估组合适配 | 否 |
| PortfolioProposal | 必须加载真实快照、已有行业/因子暴露和资金 | 经001通过后才可以 |

界面明确“研究候选”与“组合建议”。没有账户或政策时仍可看候选，不构造虚假的空账户
宣称个性化。股票看好但已过度持有，可以产生不增配／减仓的组合动作。

## 3. 筛选契约

### UniverseSnapshot

保存 universe ID/version、membership `as_of`、instrument IDs、数据来源和筛选排除
原因。历史研究不能用今天的名单假装过去可投资；缺历史membership时只能当前／前瞻。
合并重复symbol前核对instrument身份；同公司不同share class不要因字符串相似错误合并。

### Eligibility 先于 Ranking

- 支持的交易所／币种／资产类型、有效listing状态、有效价格。
- 用户所选 sector；最小流动性（美元成交额、可用spread）、必需history、数据时效。
- 停牌／delisted／IPO历史不足有明确排除原因；不能把缺失动量当真实最差收益。
- 阈值属于 SelectionPolicy version，在启用前确认；不在本文替用户选择风险比例。
- 候选少于50也必须执行 eligibility 和排序；计算上限不是策略规则。

### 可复现的 v1 筛选排序

- 将 discovery mode 从风险承受能力分开：`large_cap`、`momentum`、`balanced`。
  旧 conservative/moderate/aggressive 只显示 migration suggestion，不冒充风险控制。
- 各排序有稳定 tie-break：score desc → market_cap desc → instrument ID asc。
- momentum 的session长度、复权、收益定义与策略固定。旧约21-session收益可保留为
  明示的候选特征，不直接声称有统计优势；未来换成长周期另升版本。
- `balanced` 在最终 research budget B 上分配配额，而不是先合并50再切20。
  偶数B每组B/2；奇数多出的名额按固定policy给large_cap，记录决定。
- 按两组配额轮流选下一未入选instrument；重叠者仅出现一次，记录所属来源和实际
  占用的那一组quota。耗尽一组后，用另一组的未选候选补齐。稳定去重，不得随机抽样。
- B=20 且两组互不相交、各有≥10：必须10+10；不得20+0。

这些排序是成本可控的候选生成，不是最终仓位权重。预算减少时要显示截断原因和未研究
数量，不把未进入研究的股票算成 HOLD／失败建议。

## 4. 组合适配与最终选择

1. 获取实际PortfolioSnapshot，而非 Today’s Picks 自建 `positions=[]`。
2. 统一持仓与候选的证据时点；各候选研究结果形成dossier。
3. 计算新增候选对行业、单股、相关／共同因子暴露和现金的影响。
4. 不再按 LLM confidence 直接 Top5。按strategy定义的、可复算的eligibility/优先级，
   再经过整批风险检查。主观 conviction 仅展示，不当概率。
5. 最多N个是产品预算，不是最低产量；全部不满足时显示“没有合格建议”。
6. 现有持仓与sector未知时不能把候选标为portfolio-compatible。

## 5. 数据、API与生命周期

拟新增 SelectionReceipt：`selection_id`、policy/strategy/universe/snapshot versions、
input/eligible/selected counts、每个instrument的source bucket/rank/exclusion、quota分配、
未研究原因、portfolio-fit状态、排序规则版本。

扩展现有 universe/picks/run response；具体路由实施前确认，不新增独立隐式后台任务。
receipt和已研究dossier在run中关联；只有明确重跑才用新行情。重试同request复用同一
selection；参数或universe变更产生新版本，不在翻页／翻译时重选。

## 6. 实施步骤

- [ ] 固化B05 60个候选/25个momentum被截掉的失败回归。
- [ ] 将budget作为selector输入，所有pool大小统一执行资格与排序。
- [ ] 实现quota/de-dup/tie-break与SelectionReceipt。
- [ ] 拆分candidate与portfolio proposal的API/UI语义。
- [ ] 接真实持仓与002 post-trade checks；移除confidence-only最终排序。
- [ ] 对selection失败、partial research、无合格建议提供明确终态。

## 7. 验证条件

拟新增 `test_candidate_selection_policy.py`、`test_candidate_portfolio_fit.py`。

| ID | Given / When | Then |
| --- | --- | --- |
| CS-01 | 60候选，市值/动量前25互斥，B=20 | 10+10；无重复；不会只剩市值前20 |
| CS-02 | 任意打乱输入，包含等分候选 | 相同policy/snapshot下顺序与receipt一致 |
| CS-03 | pool为5、20、49、50、51 | 所有情况执行eligibility；不会绕过停牌/缺数过滤 |
| CS-04 | 两组大量重叠、某组耗尽、B为奇数 | 符合明确quota规则，尽量补满但不重复，不超B |
| CS-05 | 全部动量数据不可用 | 显示unavailable，不声称每只收益为负无穷 |
| CS-06 | 现有科技仓位已达上限、新候选都是科技 | 可有研究候选；无新增风险ready建议 |
| CS-07 | 模型confidence最高但违约、低分候选合规 | 前者拒绝；不按confidence绕过fit |
| CS-08 | 无持仓/未确认policy | 只输出candidate，不能谎称个性化配置 |
| CS-09 | 当前membership用于过去日期 | strict历史模式拒绝或标污染，不能算无偏回测 |
| CS-10 | 模型无BUY、部分研究失败、预算用尽 | 不凑满N；未研究/不合格/失败分开统计 |

### Playwright

拟新增 `frontend/e2e/idq-candidate-selection.spec.ts`：

- `idq-003-balanced-selection`：选balanced/20、点击发现；可展开来源quota/排除原因，
  显示10+10的合成样例；刷新receipt一致。截图 `assets/idq-003/01-balanced-candidates.png`。
- `idq-003-candidate-not-allocation`：先看到候选，点击组合适配后因现有行业集中被阻断；
  API/Mongo无approved事件，不出现自动买入按钮。截图 `assets/idq-003/02-portfolio-fit.png`。

## 8. Acceptance / Risks / Rollback

- [ ] CS-01…10及真实API E2E通过；selector、gate、持久化没有被整体mock。
- [ ] 研究候选与可操作建议的UI/API字段明确分离。
- [ ] 旧结果保留旧排序版本，不能重标成新筛选产生的候选。
- [ ] 满足总计划质量门禁、证据、版本和protected PR出货流程。
- [ ] 回滚新推荐入口到candidate-only；保留旧receipt，不恢复静默cap截断。

风险：市值/动量都可能集中于同一因子；稳定排序不等于经济有效。由009做基准和因子
归因验证；先修可复现性与配额，不为追求回测收益临时改变排名参数。
