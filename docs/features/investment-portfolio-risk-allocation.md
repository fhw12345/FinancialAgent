---
title: Deterministic Portfolio Risk and Allocation
status: in-progress
version: backend@0.55.0, frontend@0.36.0
last_updated: 2026-09-17
owner: maintainer
related_paths:
  - backend/src/agent/portfolio/risk_calculator.py
  - backend/src/agent/portfolio/context_builder.py
  - backend/src/agent/portfolio/phase2_decisions.py
  - backend/src/agent/optimizer/plan_builder.py
  - backend/src/models/derivations.py
  - frontend/src/components/portfolio/PortfolioSummary.tsx
---

# IDQ-002：组合风险口径与确定性配仓

## Implementation Contract (2026-09-17)

Authorized next task after IDQ-001-A. Stage A remains enforced: even a feasible
allocation preview is **not ready, approved or executable**. No live model probes,
real trades, inferred risk limits, or PH-009 work are authorized here.

- New immutable daily-close USD/local_holdings risk snapshots use XNYS completed
  sessions (pinned exchange-calendars), unadjusted close marks at one common session,
  and explicit adjusted-close total returns (no forward fill). Sixty-session window,
  minimum thirty shared observations; duplicate/non-session/future/bad rows are
  unavailable, never silently dropped to publish subset risk. Cash has zero estimated
  short-window volatility. Historical provider data is not a PIT archive.
- Snapshot content hashes bind quantity/cost/cash account revision, provider inputs,
  session, method and optional confirmed **risk-preview policy** revision. This is not
  the complete InvestmentPolicy/strategy contract promised by IDQ-001-B/005.
- A separate explicit policy confirmation form has no preselected personal limits.
  It records equity-based position/sector/cash-floor/turnover/per-trade risk limits,
  lot size, fees and slippage, using whole-document revision CAS. Existing
  risk_tolerance/max_position_pct settings are not silently promoted into this policy.
- Deterministic preview converts target weights to rounded share deltas with Decimal
  arithmetic; optional stop sizing caps quantity with a new sizing receipt. Reject
  invalid/duplicate/oversell/unknown-sector/incomplete-history batches. Check the entire
  post-trade portfolio, including fees/slippage. Unfilled SELL proceeds cannot fund BUYs.
  No reduce-only exception is enabled in v1. Rejected drafts are never silently resized
  to fit cash or concentration limits, nor written into the holdings ledger.
- Dashboard holdings/single-symbol/picks use the full local account snapshot; attach
  current/proposed risk and allocation receipts to the same immutable assessment write.
  Legacy model BUY size (% cash)/SELL size (% holding) is converted explicitly at the
  adapter, not reinterpreted as a different denominator. Confidence does not size trades.
- `/api/portfolio/risk` reads last saved capture, explicit refresh persists a new one;
  `/risk-policy` GET/PUT confirms versioned preview limits. Read-time stale projection
  compares account/policy revisions; old captures remain reproducible/read-only.
  No API executes a supplied formula or makes approval eligibility true.
- Fractional shares survive holding DTO/API/repository/manual-ledger/context/UI paths.
  Manual cash remains an explicitly maintained cash balance, not a new settlement ledger.
- Tests first: PR-01…12 plus calendar holidays, cash-only/zero-equity/constant returns,
  CAS/replay/write failures/cancellation/stale account, legacy assessment reads and
  non-actionability. Browser scenarios use actual API/Mongo/provider adapters and
  synthetic external receipts; no browser-mocked risk/approval responses.
- Release requires full existing gates, new critical floors, final-image browser proof,
  curated screenshots, equal-manifest clean builds, versions/case study/indexes, protected
  implementation and shipment PRs. The live 3013 credential volume/routing must survive.

## 1. 问题和目标

[总计划](investment-decision-quality-program.md) 的 P0 数学／约束工作包。
现有 sigma 对股票子集重新归一化，不能直接标为整个账户风险；returns 丢失日期后按
长度对齐；缺数据可能缩小被评估组合；LLM confidence 不能直接决定承担多少风险。

目标：每个数字有确定定义，每个建议有交易后状态，每个风险上限都由代码执行。
不是实现一个“最优收益”黑盒，也不采用未经校准的 Kelly 或模型预测收益做自由优化。

## 2. 范围与前置

依赖 [001-A](investment-decision-policy-gates.md) 的 policy/identity；与
[004](investment-evidence-snapshots.md) 约定 dated price/return inputs。
数学 oracle 可先独立实现，接入完整证据前不允许借此开启 ready。

拟新增 `services/portfolio_risk/`、`services/portfolio_allocation/` 小模块；原调用点
保留窄 adapter。复用 derivation helpers，但公式由代码实际运行，不接受模型生成的
任意表达式。v1 仅 USD long-only、不借款；不设计跨资产复杂优化器。

## 3. PortfolioSnapshot 与时间契约

- 明确account scope/ID/revision；唯一symbol/instrument ID、quantity（保留小数）、mark、
  mark time、source、currency、cash、cost basis、policy version、`as_of`；禁止把
  fractional shares转成int，或把真实账户快照当作另一个paper账户的状态。
- 统一估值时点；已存在 `current_price` 不代表仍新鲜。过期价格必须刷新或标缺失。
- returns 输入为 `{session_date, total_return}`，记录数据和公司行动调整方法。
- 使用交易日历验证数据先后；缺失／重复 session／未来数据先拒绝或显式分类。
- v1 covariance 使用所有必需股票的共同交易日交集，不按数组长度 zip；不 forward-fill
  缺失价格制造零波动。窗口为最近 60 个完整交易 session，最少 30 个共同观测。
  这只是固定估计器，不代表覆盖长期尾部风险；改变窗口必须升级 estimator version。

## 4. 数学定义与数据缺口

设股票市值 `MV_i = q_i × P_i`，总权益 `E = cash + Σ MV_i`。

```text
account_weight_i  = MV_i / E
cash_weight       = cash / E
invested_weight_i = MV_i / Σ MV_i
account_sigma     = sqrt(w_account' × covariance_daily × w_account) × sqrt(252)
invested_sigma    = sqrt(w_invested' × covariance_daily × w_invested) × sqrt(252)
```

现金在此短窗口估计中假设波动为零，此假设必须显示；利息收益另由 paper 账本处理。
相关／协方差计算与输出 rounding 分离，不用四舍五入后的相关系数做主计算。

分别输出：

- `account_sigma_annualized` 与 `invested_sigma_annualized`，不能同名混用；
- `invested_hhi = Σ invested_weight_i²`，现金单列；单股全投资部分 HHI=1；
- 以 equity 为分母的单股、行业暴露；Unknown sector 单列，不能丢弃；
- beta exposure 是对基准的敏感度，不应解释为“总体波动大于基准”；
- data coverage（纳入 equity 比例、共同日期数、被排除的资产和原因）。

### Missing / degenerate 行为

- 空持仓、有现金：account sigma=0，invested sigma/HHI=null，cash_weight=1。
- equity=0：比率为 null，allocation blocked；禁止 NaN/Infinity。
- 必需持仓缺 mark/history：整体风险为 unavailable/partial；不把子集 sigma 叫整体 sigma。
- 缺 beta：可显示“假设 beta=1 的估计值”，但 authoritative beta=null；需要 beta gate 的
  策略不能拿估计值伪装通过。也可选择不估计，必须统一 estimator policy。
- 常数收益序列：sigma=0；相关系数 undefined/null，不伪造相关性为零的经济含义。
- v1 若 covariance 数据不完整，不能增加需要该检查的新风险；明确的减仓可走独立
  reduce-only policy，但仍须有效持仓、报价、合法数量和现金约束，且不宣称整体风险通过。

## 5. 配仓与批次检查

模型提出方向／研究理由／目标偏好；代码确定可行 target weights 和 shares。
目标权重以 E 为基准，而非“剩余 buying power 百分比”。

按顺序执行：

1. 核验政策、账户和数据快照、方向、数量、币种。
2. 形成完整 proposed batch，计算所有增减仓后的净暴露。
3. 检查单股、行业、cash floor、turnover、杠杆和所需风险指标。
4. 固定算法求可行数量；若缩减 proposal，产生新 proposal/version 与新解释和 receipts，
   不静默修改旧决策的 size。
5. 价格／lot rounding 后再次检查；通过后才交给 001。

交易型策略可使用：`shares_risk = floor(risk_dollars / abs(entry-stop))`，再受资金、
单股／行业剩余额度、流动性与交易单位约束。止损距离为零时不配仓。现金计入手续费和
保守滑点缓冲；未成交 SELL 收益不是已结算可用现金。依赖卖出融资的 paper BUY 必须
有明确依赖条件，不能把 estimated proceeds 当实际 cash。

基本面模板不强制虚构短期 stop；使用明确的目标权重和压力情景预算。
所有 sizing receipt 记录 calculator version、输入 evidence IDs、约束前后数值。

## 6. 实施切片

- [ ] 将 B04 现金口径和日期错配固化为失败测试。
- [ ] 建 dated returns adapter、snapshot quality 与 estimator DTO。
- [ ] 修空组合、缺数、fractional quantities、HHI/beta 文案。
- [ ] 建 deterministic allocation 与 whole-batch policy checks。
- [ ] 接入 holdings、single-symbol 与 picks 的拟议组合，不仅检查旧持仓。
- [ ] UI 并列展示 current/proposed 风险与缺失覆盖；解释拒绝的真实约束。

## 7. 验证矩阵

拟新增 `test_portfolio_risk_oracles.py`、`test_portfolio_allocation_policy.py`、
`test_posttrade_risk_composition.py`，保留现有 PH-007 coverage floors。

| ID | Fixture | 精确预期 |
| --- | --- | --- |
| PR-01 | returns `[-0.02,0.02]×30`；股票 1000、现金 9000 | invested sigma≈0.3202；account≈0.0320；误差≤1e-4 |
| PR-02 | 单股＋任意现金比例 | invested HHI=1；cash 单列，不说持仓高度分散 |
| PR-03 | 两个等权资产、零现金、σ=20%、相关=1 | 组合σ=20%；相关=0 则≈14.1421% |
| PR-04 | 相同收益值但日期不同／中间停牌／IPO 缺历史 | 仅共同日期参与；不足30则 unavailable，不按长度匹配 |
| PR-05 | 必需持仓缺收益／mark | full risk不可用；无假正常；排除资产及覆盖率完整 |
| PR-06 | 0.5 share × $100 | 市值$50，往返持久化不变成0 share |
| PR-07 | E=$10,000、cap=10%、已有$900、拟买$200 | 拒绝／新提案至多$100，原提案不改写 |
| PR-08 | 两笔 BUY 单笔不过限但合计破cash floor | 整批拒绝；没有部分批准 |
| PR-09 | 风险预算$100、entry=100、stop=95 | 风险上限20股；仍受现金／集中度更严上限约束 |
| PR-10 | 资金依赖尚未成交 SELL／费用后现金不足 | BUY pending/blocked，不消费虚构 proceeds |
| PR-11 | 输入顺序置换／币种错误／NaN／负cash | 顺序不改结果；其余拒绝且原因稳定 |
| PR-12 | current 合规、proposed 行业集中超限 | 交易后检查拒绝，不能只展示旧风险 |

### Playwright

拟新增 `frontend/e2e/idq-portfolio-risk.spec.ts`：

- `idq-002-cash-and-fractional`：设置合成90%现金账户和0.5股持仓，查看账户／投资部分
  两种sigma及覆盖；刷新数值不漂移。截图 `assets/idq-002/01-account-risk.png`。
- `idq-002-posttrade-rejection`：点击分析后，单股／行业越界建议明确显示 current/proposed
  和触发阈值，approve disabled，Mongo不存在approved事件。截图
  `assets/idq-002/02-posttrade-blocked.png`。

## 8. 接口、迁移与验收

- 通过独立 `/api/portfolio/risk` 与 assessment detail 增加 versioned risk payload；
  保持旧 summary 的响应兼容，避免普通列表查询隐式抓取市场历史。不混写旧
  `portfolio_sigma_annualised` 的语义；旧入口的该别名为 null 并标明 legacy definition。
- [ ] PR-01…12、真实 API browser、全部总计划质量门禁通过。
- [ ] UI/API/receipts 的单位和分母一致；计算可按保存输入独立复算。
- [ ] 缺历史和压力情景缺失时没有“风险为零”的回退。
- [ ] 用户确认新政策后才启用新配仓；回滚保持历史可读并暂停新批准，不恢复假口径。
- [ ] 截图、实现hash、component版本、changelog、双语案例和protected PR完整。

## Local Validation / Publication Pending

- Backend: 2142 passed / 27 live integrations deselected; coverage rounds to 73%.
  Black/Ruff/mypy (307 source files), Bandit, deterministic Agent eval and repository
  script tests pass. Critical floors retained and extended to new risk modules.
- Frontend: 269 tests / 28 files, production lint zero warnings, total lint budget
  unchanged at 131; type-check passes. Three source-mounted real-API scenarios pass:
  cash/fractional/date persistence, explicit post-trade rejection, and policy CAS/staleness.
- First failing regressions reproduced sigma 0.3202 vs expected ~0.03202 and rejected
  0.5 shares. Browser discovered BSON date serialization; central write-boundary fix
  has a BSON-codec regression. Calendar 4.11.3/pandas 3 incompatibility was fixed by
  pinning compatible 4.13.2, not bypassing calendar validation.
- No live model calls or investment-effectiveness test. Policy fixtures are synthetic,
  not recommended personal limits. Full strategy/PIT/approval remains pending.
- Final image-only acceptance: 3 risk + 6 safety + 4 Copilot + 6 hardening + 11 default
  scenarios pass (30 total). Backend mounts fixtures only; frontend has no source or
  dependency mounts. Both run as UID 1000.
- Two unchanged-input clean builds per component match complete dependency manifests
  (125 backend distributions / 746 frontend paths) and frontend assets: backend A/B,
  frontend B/C. Frontend A preceded the zero-cash HTML input correction and is excluded.
  [Build receipts](assets/idq-002/clean-build-validation.json) explicitly record this boundary.
- [Local receipts](assets/idq-002/local-validation.json),
  [cash/fractional risk screenshot](assets/idq-002/01-account-risk.png),
  [post-trade rejection screenshot](assets/idq-002/02-posttrade-blocked.png).
- The real localhost:3013 instance runs accepted images at 0.55.0/0.36.0. Private
  Copilot credentials and the full role map/revision 1 survived recreation. Live risk
  policy remains unconfigured; synthetic test limits were never copied to the user account.
- Hosted protected publication remains pending; local tests alone do not establish shipment.
- [Bilingual case study](../case-studies/2026-09-17-cash-is-not-missing-risk.md).

风险：60日协方差不稳定、相关性在危机中改变、止损可能跳空。v1 明示这些限制；
压力情景使用独立假设并标为 scenario，不把近60日统计等同最大损失保证。
