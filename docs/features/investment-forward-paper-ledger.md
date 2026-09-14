---
title: Forward Paper Portfolio and Reproducible Ledger
status: planning
version: n/a
last_updated: 2026-09-14
owner: maintainer
related_paths:
  - backend/src/services/pnl_service.py
  - backend/scripts/run_pnl_snapshots.py
  - backend/src/models/portfolio.py
  - backend/src/database/repositories/portfolio_order_repository.py
  - backend/src/api/portfolio/
  - frontend/src/components/portfolio/DecisionTracker.tsx
---

# IDQ-008：前瞻 Paper Portfolio 与可复算账本

## 1. 目标与边界

[总计划](investment-decision-quality-program.md) 的结果记录工作包。当前7/30/90日
方向收益有诊断价值，但SELL后下跌不等于做空收益，未成交limit也不能当作持有赚钱。
HOLD持有与WAIT空仓不是同一个counterfactual。

目标：在不可改写的决策基础上，记录**前瞻模拟**的审批、订单、成交、现金、持仓和费用，
与真实账户严格隔离；给009提供可靠收益数据。不是券商模拟到逐笔精度，更不是自动下单。

前置：001-B/002/004/005。旧建议不能自动导入成历史paper交易。

## 2. 三种记录严格分开

| 类型 | 用途 | 禁止混同 |
| --- | --- | --- |
| Legacy directional mark | 旧方向判断诊断；保留原7/30/90 calendar-day口径 | 不是实际/模拟成交PnL |
| Forecast outcome | 005定义事件和期限的预测结果 | 不是持仓收益；WAIT也能有预测 |
| Paper ledger | 明确批准后的模拟持仓与NAV | 不是用户真实交易／券商执行 |

UI必须显式显示PAPER；`filled`只在paper命名空间内表示模拟成交，不能混入真实交易表。

## 3. 实验与账户契约（拟定）

`PaperExperiment`保存experiment_id、注册时间、policy/strategy/model/pricing/calculator
versions、initial cash/currency、允许资产、horizon、benchmark、execution assumptions、
cost model、corporate-action policy、外部cashflow规则、evaluation manifest。

- 初始现金由用户明确选择并冻结；若复制当前持仓，复制为一份有时点的快照。
- 后续proposal/risk/approval必须绑定本experiment的portfolio_scope和ledger revision。
  为真实账户生成的建议不可直接塞入不同paper账户；先在paper状态下重评。真实账户
  后续手工交易不修改隔离的paper账本，也不冒充paper fill。
- 不通过浏览器打开页面自动开始实验；需明确创建/批准。
- changes产生新实验或版本，不能回填历史参数；旧run结果可读。
- 未确认费用、成交方式、基准和起始状态，实验不能进入active。

## 4. v1 成交模型：先小而明确

首发建议仅支持 **next regular-session open 的market模拟**：

1. 决策封存、门禁通过且人工批准之后，才安排严格晚于approval time的下一个正常
   session open；不允许用批准前已经知道的open成交。
2. 使用该session的未复权open及可追溯market evidence；加方向性滑点和commission。
3. 记录真实scheduled session、模拟fill time、price/quantity/cost假设；缺open数据则
   pending_data，超过预注册有效期变expired，不用日后价格悄悄补成当天成交。
4. 仅v1支持的order specification可进入模拟；limit/bracket/intraday stop明确unsupported，
   不自动转market。研究stop/target只是参考，不假装已在日内成交。
5. 未来若支持OHLC stop/target，同bar都触及时必须intrabar_unknown或固定保守政策；
   禁止总挑有利先后。该扩展不属于v1实现。
6. 成交前再验证持仓/cash/政策状态；未成交SELL的estimated proceeds不能资助BUY。
   依赖卖出的BUY必须等待资金实际进入paper cash，过期则不追溯成交。

market假设不代表真实可成交价。必须配置费用、滑点和最大参与比例；缺流动性输入时
明确不能模拟该交易，或采用预注册并显式标注的保守假设，不隐式零成本。

## 5. 事件与账本

建议事件：`experiment_created`、`decision_approved`、`order_scheduled`、`order_cancelled`、
`order_expired`、`fill_recorded`、`fee_charged`、`split_applied`、`dividend_paid`、
`valuation_recorded`。每个事件具有唯一ID、experiment/decision关联、event/effective times、
幂等键、payload hash和来源。事件不可编辑；纠错用补偿事件，不能覆盖过去成交。

使用Decimal／整数最小货币单位，并固定rounding。原始执行价格配合split/dividend事件；
不能既使用total-return adjusted prices，又把同一dividend重复加进cash。

```text
cash_after_buy = cash_before - fill_quantity * fill_price - fees
cash_after_sell = cash_before + fill_quantity * fill_price - fees
NAV = cash + Σ(quantity_i * contemporaneous_mark_i)
```

FIFO为建议的v1 realized-PnL cost basis方法；方法在创建实验时固定。外部资金流v1默认
禁止；若将来支持，必须独立记录并使用正确time-weighted returns，不能计作策略收益。

### 一致性与恢复

- 独立 `paper_experiments` / `paper_events` / read projections；不更新真实holdings/cash。
- event uniqueness + expected ledger sequence做CAS；同请求重试不重复成交/费用。
- 不假设standalone Mongo支持跨文档事务：以单一提交事件为真，projection可重建；
  prepare但未commit的操作对NAV不可见。并发两笔资金竞争最多只有合法余额的提交成功。
- startup/replay仅重建projection，不重新调用LLM、不再抽样滑点。
- cancel/approval失效与fill提交使用明确线性化点；与001的政策revision协调，不能用
  非原子的跨集合先查后写宣称防住竞态。已提交fill不能被“取消”抹掉，只能新增退出。

## 6. 估值与基准

- 每次mark记录instrument、session、observed_at、source与staleness。
- 缺mark：NAV unavailable/partial，显示覆盖率；不能把缺价持仓算作零，也不能无限沿用
  旧价却标正常。可展示last-known NAV但必须注明as_of。
- equity benchmark采用明确total-return系列或可复算的持仓/分红模型，避免口径混用。
- 现金benchmark、市场/行业benchmark和简单固定规则baseline使用同一起止时间、相同
  初始资金与明确费用假设。005预先选择适当基准，不能结束后换到最好比较的那个。
- 预测评估期限按005的units；旧calendar-day marks保持legacy，不偷偷改成trading sessions。

## 7. API/UI 与实现顺序

拟新增 `/api/portfolio/paper/experiments`（创建/列表/detail）、对应ledger/NAV只读接口。
批准复用001而非第二个绕过policy的buy按钮；默认本地、无新增认证/云服务。

- [ ] 建实验配置/schema与append-only events、unique indexes、CAS/projector。
- [ ] 建交易日历、next-open、fees/slippage计算器和corporate-action处理。
- [ ] 接001批准、002成交流前检查、004行情身份与失效处理。
- [ ] 新paper snapshot runner显式运行；先支持手动tick，不新加隐式付费定时任务。
- [ ] UI区别建议/批准/pending/filled/expired，展示NAV与费用，导出ledger manifest。
- [ ] 旧directional view改清楚标签；不迁移为真实或paper收益。

## 8. 验证矩阵

拟新增 `test_paper_ledger_accounting.py`、`test_paper_execution_calendar.py`、
`test_paper_ledger_concurrency.py`、`test_paper_portfolio_api.py`。

| ID | Fixture | Oracle |
| --- | --- | --- |
| PL-01 | $10,000；买10股，open=$100，slip=10bps，fee=$1 | fill=100.10，cash=8998；mark=100时NAV=9998 |
| PL-02 | 接PL-01；全卖，open=$110，同slip/fee | fill=109.89，final cash/NAV=$10095.90；净PnL=$95.90 |
| PL-03 | 收盘后批准／周末／节假日／半日市 | 选择严格未来合法session，无历史open成交 |
| PL-04 | 相同approve/fill请求重试100次 | 1个approval、1个fill、1次fee；NAV不变 |
| PL-05 | 同时两笔各需60%现金 | 无负cash；最多合法组合commit，另一明确拒绝/等待 |
| PL-06 | commit后projection失败/进程重启 | replay NAV与原golden一致，无新成交/LLM调用 |
| PL-07 | 2:1 split：100股@$10→200股@$5 | NAV不变，cost basis总额不变 |
| PL-08 | $1 dividend且价格相应下降$1，零税费 | cash增加与市值减少抵消，无双计收益 |
| PL-09 | 未成交limit或unsupported bracket | 不产生PnL/持仓；无隐式market转换 |
| PL-10 | SELL close_long / HOLD holding / WAIT flat | 真实paper持仓变化正确；不把SELL当short、WAIT当long |
| PL-11 | 缺open/mark、delisted或corporate-action待确认 | pending/expired/unknown可见，不静默删掉亏损样本 |
| PL-12 | 批准后policy变更、cancel和fill竞争 | stale/cancel按线性化规则生效；无双重终态 |
| PL-13 | local_holdings或另一experiment的ready决策直接批准 | account scope mismatch；必须重评，不修改任一账本 |

### Playwright

拟新增 `frontend/e2e/idq-paper-ledger.spec.ts`：

1. `idq-008-approve-then-future-fill`：真实API创建合成paper账户，批准ready决策；
   当下pending、不成交；测试clock跨到合法session后手动tick，显示PL-01金额并刷新恢复。
   截图 `assets/idq-008/01-paper-fill.png`。
2. `idq-008-costs-and-restart`：接PL-02卖出，显示费用与净收益；重启/重放projection后
   金额不变；真实holdings/transactions未改。截图 `assets/idq-008/02-paper-nav.png`。
3. `idq-008-wait-is-not-hold`：空仓等待不显示股票上涨带来的虚构盈利。

## 9. Acceptance / Rollout / Rollback

- [ ] PL-01…13、真实API/数据库browser场景及总计划质量门禁通过。
- [ ] 每份NAV能从初始状态＋events独立复算到最小货币单位。
- [ ] 历史记录、真实账户和paper实验严格隔离；无broker网络调用。
- [ ] 费用/滑点/时间/缺数/企业行动及基准假设已确认、版本化、可导出。
- [ ] 发布的是可靠测量工具，不要求paper结果正收益才算功能成功。
- [ ] 截图、版本、changelog、双语案例、protected PR和run receipts齐全。
- [ ] 回滚暂停新批准/成交，保留只读账本与重建能力；不删除坏结果或重写历史。
