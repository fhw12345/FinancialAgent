---
title: Investment Mandates and Research Strategy Contracts
status: planning
version: n/a
last_updated: 2026-09-14
owner: maintainer
related_paths:
  - backend/src/models/portfolio_analysis.py
  - backend/src/agent/portfolio_phase2_prompt.py
  - backend/src/agent/portfolio/phase1_research.py
  - backend/src/agent/skills/financial/
  - backend/src/agent/skills/technical/
  - backend/src/agent/prompt_registry.py
  - frontend/src/components/portfolio/SettingsPanel.tsx
---

# IDQ-005：投资授权、研究期限与策略方法契约

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

- [ ] 确认pilot mandate、期限、基准与必需字段；记录decision log。
- [ ] 建StrategySpec/ValuationResult/Thesis/Forecast DTO与明确单位。
- [ ] 将原有方法转成小型deterministic calculators与input验证。
- [ ] 按模板生成Phase1/Phase2 Prompt，注册版本并记录实际使用。
- [ ] 接001/004，展示strategy/horizon/invalidation/assumptions。
- [ ] 保留旧研究原文，新增legacy_strategy标签，不补写历史策略身份。

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

- [ ] ST-01…10、真实API E2E与总计划质量门禁通过。
- [ ] 首发策略所有参数、必需数据、期限、基准、成本和变更流程已明确确认。
- [ ] 方法返回的事实／假设／主观概率在UI与export中同样清晰。
- [ ] 版本、截图、changelog、双语案例和protected PR完成；不把软件出货称作策略有效。
- [ ] 回滚禁用新策略版本但保留旧record读取；不把新结果重标旧版本。

仍需维护者确认：首发模板、允许估值方法/行业范围、具体阈值、是否支持ETF look-through。
不支持的类型明确inapplicable/blocked。不要为追求覆盖率把银行、ETF、亏损股都硬套同一估值。
