---
title: Investment Mandates and Research Strategy Contracts
status: shipped
version: backend@0.57.0, frontend@0.38.0
last_updated: 2026-09-18
owner: maintainer
related_paths:
  - backend/src/models/research_strategy.py
  - backend/src/services/research_strategy/
  - backend/src/services/market_data/research_income.py
  - backend/src/services/evidence/
  - backend/src/agent/prompt_registry.py
  - frontend/src/components/portfolio/ResearchStrategyPanel.tsx
  - frontend/src/components/portfolio/StrategyReceipt.tsx
---

# IDQ-005：投资授权、研究期限与策略方法契约

## Confirmed Pilot / Implementation Contract (2026-09-18)

Maintainer explicitly confirmed: medium-term fundamental research, **252 XNYS trading
sessions**, **SPY total-return benchmark**, USD US non-financial common equities, with
conditional peer PE and DCF. Banks/insurance/other financials and ETF look-through are
inapplicable in this pilot. Short-term research remains a separate disabled experimental
contract. This approval is the software pilot scope, not personal valuation assumptions
or activation of a live strategy.

- Numeric assumptions are blank until explicit confirmation: discount/growth/terminal
  growth/tax rate/projection years, valuation discount, earnings-decline and debt/FCF
  invalidation thresholds, and financial-age/closing-price freshness limits. Peer membership
  and selection rationale are fixed before provider fetch. Costs bind a user-confirmed
  IDQ-002 risk-policy revision, not a second cash/position ledger.
- A single-document CAS aggregate stores immutable strategy versions and an active-for-
  future-research pointer. Confirmation needs expected revision and request identity;
  same-request replay is idempotent, divergent/stale writes conflict. Deactivation keeps
  history. Opening/selecting/saving never invokes a model; running research is separate.
- Selected versions, cost assumptions, peer snapshot IDs and method versions are frozen
  into new evidence captures. Old sealed records/hash verification stay compatible and
  old assessments are explicitly legacy_strategy, never backfilled. A later edit cannot
  alter in-flight prompts or historical receipts; stale projections require new research.
- Fundamental Phase 1/Phase 2 use separately registered prompts, not the old mixed
  Fibonacci/forced stop/target instructions. Active strategy output separates investment
  stance from portfolio_action=null / execution_intent=null. No fabricated HOLD for
  missing inputs. Deep uses the same contract and evidence/calculation receipts.
- PE uses positive annual diluted EPS and a predeclared peer set with comparable dated
  EPS/closing-price receipts; derive the peer median PE, never invent a sector multiple.
  DCF is a disclosed FCFF **proxy model**: CFO + interest×(1−declared tax) − capex,
  projected under declared assumptions, then subtract net debt and divide by annual
  diluted-average shares. Accrual/cash-interest and future-dilution limitations are explicit.
  This is not audited FCFF or a verified fair value. No method averaging/triangulation
  merely because two outputs share a currency; unavailable/inapplicable is valid.
- Additional income-statement evidence preserves fiscal period, financial currency and
  provider normalization. Missing financial currency, earnings/shares, peers, dates,
  conflicts or unsupported company type produces no invented valuation. Current provider
  restatements remain retrieval_only, not historical PIT. No new arbitrary formula evaluator.
- Material theses reference captured evidence; monitoring conditions are rendered from
  the confirmed contract. Forecast scenarios are conditional/unverified; v1 probability
  is null, never confidence/10 or an empirical historical-frequency claim.
- Always non-actionable. Full InvestmentPolicy, ready/review approval and paper execution
  remain IDQ-001-B/008. No live inference, synthetic personal limits, PH-009 work or IDQ-003
  implementation is authorized by this task.
- Test-first ST-01…10 plus CAS/replay/stale/cancel/persistence/unit/scope/old-record controls;
  real API/Mongo browser evidence, all existing gates, final repeated builds, versions,
  bilingual case study and two-stage protected publication are required.

## 1. Context / Objective

[总计划](investment-decision-quality-program.md) 的方法论工作包。当前一条Prompt混合
短期技术、数周催化剂和年度估值，且价格锚过度依赖Fibonacci。多列几个指标不是策略，
三种情景概率相加为1也不等于预测经过校准。

目标：先说明“研究什么、多久、相对什么基准、何时改变观点”，再定义需要的数据和
确定性方法。允许基本面看多、短期等待、组合减仓同时成立。

前置：[001-A](investment-decision-policy-gates.md)、[004](investment-evidence-snapshots.md)。
不挑选用户实际仓位比例、不承诺任何模板盈利、不自动启用付费策略搜索。

## 2. StrategySpec 与 Request 契约（拟定）

- strategy_id/version、name、status（内部版本生命周期，不替代feature frontmatter）。
- universe、currency、allowed asset/intent、research horizon及单位（sessions/calendar days）。
- 主要问题、benchmark ID/version、决策规则、rebalance/event触发、退出/失效条件。
- required vs optional evidence清单、freshness policy、估值／指标method versions。
- 参数、假设、缺失规则、成本模型、比较baseline、假设注册时间。
- 不可变版本；用户修改参数创建新版本。Prompt文本改变不隐式改变策略规则。

ResearchRequest引用policy/strategy，并区分 `purpose=research|portfolio_proposal`。
无确认策略或政策时只做research-only。聊天的期限/约束可用于草稿，不能替用户静默
改变已经确认的投资政策。

## 3. 建议的两个独立模板

### A. 中期基本面研究（首发候选）

- 评估未来若干季度的盈利质量、自由现金流、资产负债表、估值与论点失效条件。
- 建议pilot明确选一个主评估期限，例如252 trading sessions；事件复核另定义，不因
  看到结果不好而临时改为60日。数字属于候选参数，启用前确认。
- 必需：有效价格/股数口径、可用财务期间、盈利/现金流/债务信息、支持估值的inputs。
- 收入增长、利润率、SBC/稀释、资本开支、净债务与ROIC等按商业模型选择；银行、
  亏损成长、周期公司不能强制共用EV/EBITDA或PEG规则。
- 技术指标可用于交易时机提示，不拥有内在价值解释权。
- 输出valuation range、关键敏感性、与价格隐含预期的差异；资料不足可无估值结论。

### B. 短期规则型交易研究（独立实验，默认不启用）

- 先固定信号定义、入场时点、最长持有期、退出规则、流动性、成本与风险预算。
- 可以研究趋势/动量/技术价位，但必须由确定性indicator计算并可回放。
- Fibonacci只是一种待验证feature；不能因为“黄金比例”名称就认定存在edge。
- 无需虚构两种财务估值；但必须满足明确的数据/事件排除规则与交易后风控。
- 若没有预注册规则，输出观察而不是BUY/SELL。

## 4. 数值方法与证据要求

### 估值

1. `ValuationResult`区分 ratio、enterprise value、equity value、per-share USD，不能把
   PE=25与DCF=$150都放进无单位value后直接平均。
2. 同行集合在取结果前固定，记录选择条件/成员/日期、会计口径、异常值处理。
   没有同行数据就不输出“比同行便宜”。
3. 采用可适用的不同方法，不能把同一种PE重复两次充当triangulation。
   若仅一种方法适用，明确局限并按策略决定review，不为了字段数制造第二种方法。
4. DCF/倍数等由calculator registry运行；保留discount、growth、margin、dilution、
   net debt、share count来源和假设。`g >= discount rate`的永续模型等非法参数拒绝。
5. 历史财报与forward estimates分开；模型假设不伪装成分析师共识或已披露事实。

### 预测、情景与论点

- thesis记录有限数量的**重大**主张，不机械要求永远恰好3条；每条事实有004引用。
- bull/base/bear情景是条件假设，不默认拥有校准概率。未知概率允许null。
- 若输出概率，必须定义互斥且完备的事件、期限与conditioning、base-rate dataset ID；
  非经验概率标subjective，不允许把conviction/10当成功概率。
- target price/horizon与execution reference分开；12个月目标不解释为下周take-profit。
- 每个thesis有invalidation/monitoring条件，例如特定财报指标或融资事件，不只是价格跌了。
- 具体历史频率必须来自数据计算；禁止“SPY每几年必跌一次”等无来源例子被复制成事实。

## 5. 决策规则与文本职责

- investment stance、portfolio action、execution intent是三个独立字段。
- 看多且持仓已超限可建议减仓；未持有时HOLD必须说明是wait，不计为持有收益。
- close_long的reduce order不复用open_short的几何语义；不强制为减仓虚构“卖出后获利价”。
- 规则阈值、需要哪些证据、何时停止研究由StrategySpec定义；LLM只解释结果与例外。
- 旧Prompt里的主观仓位、固定指标要求分阶段迁移，保留registry版本、实际usage和回归。
- 一般教育性回答不强迫用户先填投资政策；只有个性化/可操作建议被限制。

## 6. 接口、版本与实现切片

拟增加 strategy list/detail/version endpoints及研究请求的strategy_id；扩展现有设置
面板，不建立第二套现金/持仓表。默认列表显示“未启用／需确认”，不能选择后立即付费运行。

- [x] 确认pilot mandate、期限、基准与必需字段；记录decision log。
- [x] 建StrategySpec/ValuationResult/Thesis/Forecast DTO与明确单位。
- [x] 将原有方法转成小型deterministic calculators与input验证。
- [x] 按模板生成Phase1/Phase2 Prompt，注册版本并记录实际使用。
- [x] 接001/004，展示strategy/horizon/invalidation/assumptions。
- [x] 保留旧研究原文，新增legacy_strategy标签，不补写历史策略身份。

## 7. 验证条件

拟新增 `test_investment_strategy_contracts.py`、`test_valuation_calculators.py`、
`test_strategy_prompt_composition.py`。

| ID | Fixture | Oracle |
| --- | --- | --- |
| ST-01 | 中期vs短期同一股票同一数据 | 各自required字段、期限、benchmark独立；不混合目标价 |
| ST-02 | basic PE calculator：EPS=$5、合法peer multiple=20 | implied per-share value=$100，证据/单位齐全 |
| ST-03 | EPS缺失/亏损不适用、peer set缺失 | unavailable/inapplicable；不自动填sector PE |
| ST-04 | DCF增加discount、固定其余正现金流 | value非增；g>=r拒绝；结果可由保存inputs复算 |
| ST-05 | 企业价值减净债务再除稀释股数 | golden fixture精确吻合；错million scale拒绝 |
| ST-06 | 同一valuation method两次 | 不能计作两种独立方法 |
| ST-07 | subjective scenario含假历史频率或无dataset | 不能标empirical/calibrated |
| ST-08 | 基本面bullish但已有仓位超cap | stance不变，portfolio增加动作被002拒绝 |
| ST-09 | 修改horizon/参数但试图沿用version | 拒绝；必须新版本；历史报告不变化 |
| ST-10 | 缺必需证据却给很高confidence | 不升级ready；confidence不补充证据 |

### Playwright

拟新增 `frontend/e2e/idq-strategy-contracts.spec.ts`：

- `idq-005-explicit-mandate`：未确认政策仅能看研究；确认合成策略后，报告显示明确期限、
  基准、假设与失效条件。截图 `assets/idq-005/01-strategy-contract.png`。
- `idq-005-valuation-unavailable`：录制provider缺EPS/peers；UI解释不适用/缺失，不显示
  虚构fair value；刷新保持旧报告。截图 `assets/idq-005/02-missing-valuation.png`。

## 8. Acceptance / Rollback / 未决问题

- [x] ST-01…10、真实API E2E与总计划质量门禁通过。
- [x] 首发范围、期限、基准、必需数据和参数/成本/变更语义已确认；个人数值须经显式 UI/API 确认，真实账户未自动启用。
- [x] 方法返回的事实／假设／主观概率在UI与export中同样清晰。
- [x] 版本、截图、changelog、双语案例和protected PR完成；不把软件出货称作策略有效。
- [x] 回滚禁用新策略版本但保留旧record读取；不把新结果重标旧版本。

首发范围已于 2026-09-18 确认，见本文顶部。个人数值假设、同行和阈值仍须在 UI/API
显式确认才创建/启用版本；本次范围确认不会填入真实账户。短期模板和 ETF look-through
不启用，不支持类型明确 inapplicable。Provider 的 equity/country/sector 分类只是研究
适用性筛查，不是独立 share-class 或未来 ready 资格证明。

## Validation / Shipment

- Backend 2217 passed / 27 live integrations deselected, coverage rounds to 74%;
  Black/Ruff/mypy (330 files), Bandit, deterministic Agent evaluation and script checks pass.
- All existing critical floors are preserved; new floors cover contracts, calculators,
  applicability, CAS store, adapters, monitoring and composition.
- Frontend 272 tests / 30 files, production lint zero, total test/E2E lint ceiling 131;
  type-check passes. Final image-only acceptance passes 4 strategy + 3 evidence + 3 risk
  + 6 safety + 4 Copilot + 6 hardening + 11 default scenarios (37 total).
- [Contract screenshot](assets/idq-005/01-strategy-contract.png) follows assertions of
  252 XNYS sessions, SPY total return, PE=100 USD/share and null portfolio/execution action.
  [Missing valuation](assets/idq-005/02-missing-valuation.png) follows assertions of
  missing EPS/shares, unavailable estimates and unchanged reload results.
- All browser data/model receipts are synthetic outer transports with real API/graph/
  adapter/Mongo paths. No live model probe or investment-performance comparison was run.
- Two unchanged-input no-cache builds A/B match full installed manifests (125 backend
  distributions / 746 frontend paths), frontend assets and production source trees.
  The initial B transport returned truncated registry JSON and was excluded; bounded
  retry passed the same lock checks. [Build receipts](assets/idq-005/clean-build-validation.json).
- [Local receipts](assets/idq-005/local-validation.json) record accepted image IDs, UID
  1000, fixtures-only backend/no frontend mounts, and unchanged historical strategy /
  deactivation / assessment responses after actual backend recreation.
- Live localhost:3013 runs 0.57.0/0.38.0 with private login/routing revision 1 preserved.
  Personal risk policy and research strategy remain unconfigured; synthetic parameters
  were never copied into the live account. No live inference was requested.
- Implementation `6104c3a8bcff891c506c554931c126a285362cb4` merged through
  [protected PR #14](https://github.com/fhw12345/FinancialAgent/pull/14) as
  `0a9699d9af365bb734d5033668c65c7ffc12a1ff`.
  [Hosted CI 35321163990](https://github.com/fhw12345/FinancialAgent/actions/runs/35321163990)
  passed all gates and all six browser lanes. Downloaded artifacts retain six HTML
  reports with verified hashes and no credential files; see
  [hosted receipts](assets/idq-005/hosted-validation.json). No admin bypass.
- [Bilingual case study](../case-studies/2026-09-18-research-mandate-is-not-a-trade.md).
