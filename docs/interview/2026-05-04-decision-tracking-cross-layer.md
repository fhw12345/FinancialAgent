# 决策追踪：跨多个层的 instrumentation + "我在调谁？"端口陷阱

> Date: 2026-05-04
> Component: 端到端 decision tracking（model + repo + cron + API + frontend）
> Severity: 🟢 中等（功能扩展，零回归；又一个端口/容器混淆陷阱）

## 1. 背景 / Context

产品现状：AI 给 BUY/SELL/HOLD 决策，但**没人验证决策对不对**。HOLD 直接被丢弃，订单价格 anchor 也不存。需要一套"事后 P&L 评估"系统：捕捉决策时的价格 → 7d/30d/90d 后查实际价 → 算 hypothetical 收益 → 前端可视化。

跨 5 层改动：mongo schema → repo → cron service → API → frontend。

## 2. 思考过程 / Reasoning

### 决策 1：fallback 链放哪？

PRD 阶段就纠结过：每个 tool 自己写 try/except vs DataManager 统一管。最终选 DataManager（在 Finnhub 集成时已经这样做了），`get_price_on_date` 只是给它加个 helper，自动免费获得 Finnhub→AV→yfinance 三层 fallback。

### 决策 2：HOLD 存哪？

PRD 选了 "塞回 portfolio_orders 同表，加 `decision_type` 字段区分"。理由：单用户工具，分两个表纯粹是为了拆而拆，三种决策共用 90% 字段，cron 处理逻辑也共用。代价：现有 `RecentTransactions` 列表会突然多 HOLD 行，需要前端层面 filter（暂时没改，作为后续优化）。

### 决策 3：HOLD 价格 anchor 哪里来？

`TradingDecision` schema **不带 price**——LLM 只输出 symbol + 决策 + 仓位百分比。三个候选：
1. 让 LLM 把 price 也吐出来 → 改 schema、改 prompt，LLM 看到的价不一定是当前真价（污染）
2. portfolio_context 里推算 → 已有的 positions 只有 market_value/quantity，新标的无价
3. **实时调 quote** → 准确、单一来源、免费走 fallback chain

选 3。但 portfolio agent 不持有 DataManager，要从 `react_agent.data_manager` 借——这是个临时 hack，应该直接给 portfolio agent 注入 DataManager。算技术债，记下。

### 决策 4：Deep ReAct verdict 持久化的边界问题

verdict_node 输出是**纯文本**（`### Final Verdict\n- **Action**: Buy`），没结构化 schema。三选项：
1. 改 LLM prompt 强制结构化输出 → 影响现有用户体验，verdict 文本是给人读的
2. **regex 解析**已生成的文本 → 简单、零 LLM 改动、但脆弱（LLM 哪天换格式就坏）
3. 让 verdict 走两次：第一次自由文本给前端、第二次结构化只为持久化 → 双倍成本

选 2 + 加 try/except 兜底（解析不出就跳过，不报错）。脆弱但务实。case study 里诚实记录这个 trade-off。

### 调试踩到的最大坑：端口陷阱

写完 endpoint 后 `curl http://localhost:8000/api/portfolio/decisions` → 404。看 `/openapi.json` 列出的路径**完全是另一个项目**的（dca-plans / funds / quarterly-report / tplus1）。

第一反应：我的 router 没注册成功。docker compose exec 进去 `python -c "from src.main import app"` 检查路由列表 → **完整 routes 都在！包括 `/api/portfolio/decisions`！**

那 OpenAPI 怎么是别的内容？查 `docker ps`：

```
financialagent-backend-1   0.0.0.0:8001->8000/tcp
fundagent-backend-1        0.0.0.0:8000->8000/tcp
```

**8000 端口被另一个项目（FundAgent）占了，FinancialAgent 在 8001。** docker-compose.override.yml 的端口改写早就告诉过我，但我习惯性 curl 8000，把 FundAgent 的 OpenAPI 当成了 FinancialAgent 的，看到完全陌生的路径反而开始怀疑自己代码。

这是这个 session 第二次类似的"我以为是 X 其实是 Y"——上次是 ghost compose project 同名容器互撞（见 [2026-05-04-ghost-compose-project.md](2026-05-04-ghost-compose-project.md)）。同一个 root cause 模式：**多 repo 并存的 dev 环境，命名/端口空间隔离不严，会让"我在跟谁说话"这个最基础的假设悄悄出错**。

## 3. 根因 / Root cause

### 主任务的"根因"（多层 instrumentation 完整性）
- `OptimizedOrder.estimated_price` 已经存在但 `OrderExecutor` 写 mongo 时**主动丢掉**了——这是字段级的"信息有但被截断"
- `plan_builder.py:66-72` 把 HOLD 显式 filter 掉——这是行级的"决策有但不持久化"
- 两处都是"前一个 wave（W5a 移除 Alpaca）做完后**没有人补上观测面**"——重构时砍掉执行没问题，但同时砍掉了观测能力

### 调试坑的根因（端口混淆）
- 项目 root `docker-compose.override.yml` 把 backend 端口改成了 8001 是**为了让多个 fork 并存**
- 但开发者（我）的肌肉记忆是"localhost:8000 = backend"
- Curl 8000 拿到的是邻居项目（fundagent）的 OpenAPI，路径完全不一样反而触发了"自己代码错了"的错误归因
- 跟上次 ghost compose project 是同一个 root cause 家族：**多 repo 并存 + 命名空间共享**

## 4. 解决方案 / Fix

### 主任务（commit 待定）
新建/改 16 个文件横跨 5 层：
- `models/portfolio.py` — 加 3 个字段，零 migration
- `repositories/portfolio_order_repository.py` — `list_pending_pnl_snapshots` + `update_pnl_snapshot` + `list_decisions`
- `services/data_manager/manager.py` — `get_price_on_date(symbol, target_dt, max_forward_days=5)`，weekday 跳天兜底
- `services/pnl_service.py`（新）— 纯函数 + 主循环，sign-aware（SELL 取负），idempotent（重复跑不会覆盖已有 snapshot）
- `scripts/run_pnl_snapshots.py`（新）+ `docker-compose.yml` 加进 cron loop
- `agent/optimizer/executor.py` — 写 `decision_price=order.estimated_price`
- `agent/portfolio/phase3_execution.py` — `_persist_hold_signals` helper
- `agent/deep_react_agent.py` — `_persist_verdict_decision` helper（regex 解析 + try/except 兜底）
- `api/portfolio/decisions.py`（新）+ wire 到 router
- `api/dependencies/chat_deps.py` — 注入 `mongodb` + 构造 `order_repo` 给 deep agent
- `frontend/hooks/useDecisions.ts`（新）
- `frontend/components/portfolio/DecisionTracker.tsx`（新）— 表格 + Recharts 线图，颜色按正负
- `frontend/pages/PortfolioDashboard.tsx` — 挂 component
- `frontend/package.json` — 加 recharts

### 端口陷阱（即时 workaround）
直接 curl `http://localhost:8001/...` 拿到正确的 FinancialAgent API，count: 0（db 为空，符合预期）。

### 端口陷阱（长期 fix，待办）
- **方案 A**：在每个项目的 README 顶部加 "this project runs on port 8001 not 8000" 提示
- **方案 B**：每个 repo 的 docker-compose.override.yml 用项目特定端口（FinancialAgent 8001、FundAgent 8002...），消除冲突可能
- **方案 C**：写个 `make smoke` 脚本，开头自检 "本 repo 的 backend 在哪个 port"，避免人为 curl 错误

## 5. 教训 / Takeaways

1. **重构时砍执行不能砍观测面**。W5a 移除 Alpaca 是对的，但同时丢失了"AI 决策有没有被记录"的能力。砍代码前问一句"这条数据流上谁在看？"
2. **schema 字段被悄悄丢弃 = 银行家最讨厌的 bug**。`OptimizedOrder.estimated_price` 在内存里有、写入时被丢、看代码完全合法。这种"信息有但被截断"的 bug 不会报错，只会让某天的需求"为什么我们没有这个数据"无解。
3. **Mock 测试覆盖率 != 集成正确性**。我写 13 个 unit test 全过，但对 portfolio agent 实际不持有 DataManager 这种集成事实毫无觉察——只是借了 `react_agent.data_manager`。要靠真实 cron 跑一轮才会暴露的"borrow chain"在测试里看不到。
4. **regex 解析 LLM 输出是技术债，但有时是正确的债**。强制结构化会牺牲用户可读性、改 prompt 影响其他维度。务实选 regex + try/except 兜底，把脆弱性局部化、记录下来，等下次 verdict prompt 大改时一并升级。
5. **多 repo 并存的开发环境，端口/命名空间是隐藏地雷**。这是这个 session 第二次踩同类坑（ghost compose 是第一次）。同一个 root cause 家族重复出现说明**这不是开发者的失误，是环境本身的设计漏洞**——值得做一次性根治（统一端口分配 / 项目自检脚本），不是每次出问题人肉绕过。
6. **debug 时检查"我在调谁"应该早于检查"我的代码错了哪里"**。`docker ps` 看端口归属、`docker inspect` 看挂载源、`curl /openapi.json` 看响应是不是你期望的服务的 OpenAPI 模型——这些 1 分钟的检查能救你 30 分钟的代码 bug 排查。

## 相关
- [2026-05-04-ghost-compose-project.md](2026-05-04-ghost-compose-project.md) — 同一个"多 repo 命名空间冲突"家族，上次是容器名互撞，这次是端口
- [2026-05-04-finnhub-fallback-chain.md](2026-05-04-finnhub-fallback-chain.md) — 同一个"DataManager 是 single source of truth"模式的延续；本次复用了 fallback chain

## 后记：E2E 跑出来的 4 个 bug（这才是真正的"发布前"）

写完代码、unit test 13 个全过、`/api/decisions` 返 `count:0` 我就准备 commit 了。然后被问"改完之后有 E2E 测过吗"——没有。补跑后**4 个 bug 一个都不被 unit test 抓到**：

| # | Bug | 单测为什么没抓到 |
|---|------|-----------------|
| 1 | `get_price_on_date` 全返回 None（AV 限流后没 fallback）| 我 mock 了 `get_price_on_date` 直接返回 110.0；从不真调 |
| 2 | mongo `idx_alpaca_order` `sparse=True` 没保护 null（第二个 HOLD 写入就 DuplicateKeyError）| 我 mock 了 repo 的 `update_pnl_snapshot`；从不真写 |
| 3 | `created_at` naive vs `utcnow()` aware 比较挂 | 我 fixture 里 `created_at=datetime.now(UTC)` 是 aware 的，prod 走 mongo 是 naive |
| 4 | yfinance window 太窄 + horizon 落周末 + 当天 close 未出 | mock 直接返回价；从不真走 yfinance |

这 4 个 bug 全都是**"假数据 vs 真数据形状不一致"**——同一个家族，跟之前 [token-extraction-getattr-on-dict](2026-05-04-token-extraction-getattr-on-dict.md) 里的 `Mock(input_tokens=100)` 遮蔽 dict 形状是同根问题。

**通用教训**：mock 测试只验证"代码路径不崩"，不验证"代码路径在 prod 数据形状下做对"。fallback chain、外部 API、mongo 序列化、时区处理——这四类全是单测的盲区。**端到端测试不是"加分项"，是 "fallback / 兜底 / 边界" 类代码的唯一可信验证。**

本次 4 个 bug + commit `2bf73d4` 时遇到的 mock 假数据救场（assertion 期望 281 实际拿到真实 280.14），构成同一个反模式的连续四次出现。下次类似工作的纪律：
1. 写完直接跑一次 E2E，**插假老数据 + 真跑 cron + 看 db 真值**
2. 任何带"fallback to X" / "网络外部依赖" 的代码，单测必须 mock 出 X 也失败的路径
3. mongo 写入路径的测试必须真写到 mongomock 或 testcontainers，而不是 mock repo
4. 涉及时区的 datetime 比较，要造一个 naive 一个 aware 的 fixture 验证
