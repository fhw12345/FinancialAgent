# Backend Changelog

All notable changes to the Financial Agent Backend will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.22.0] - 2026-05-06

### Added
- **feat(mark-executed): 把"LLM 建议链"和"实际成交链"接上，一键 Mark Executed 同步 cash + holdings + transactions + orders 四张表** — 之前 DecisionTracker 只能看 LLM 给的 BUY/SELL 建议，但实际有没有按它做、做了多少、cash 还剩多少，跟决策本身完全脱钩。现在每条 `status="suggested"` 的 BUY/SELL order 旁边一个 `Mark Executed` 按钮，点开 modal（默认 qty 自动按 `position_size_percent * cash / entry_price` floor 算、默认 price 用 LLM 给的 `entry_price`、SELL 默认填当前 holding qty），用户改完确认。
  - 新建 `services/order_execution_service.py:mark_order_executed`，5 步带补偿回滚的编排：(1) 校验 order 存在 & status=suggested & side∈{buy,sell}；(2) 写 `user_transactions` 行（带 `portfolio_order_id` 反指针）；(3) 调 `holdings_ledger.apply_transaction` 走加权均价 BUY / 减仓 SELL；(4) `$inc` 调整 `user_settings.cash_balance`（BUY 减 / SELL 加，**允许变负数 + warning**）；(5) `portfolio_orders` 翻成 `status=filled` 带 `user_transaction_id` 正向指针。任一步失败回滚前面的步骤——单用户本地工具不上 multi-doc transaction 是有意为之，补偿模式买的简单性比 ACID 更值。
  - 新接口 `POST /api/portfolio/orders/{order_id}/mark-executed`，map service 异常到 404/409/400/500：`OrderNotFoundError` 404、`OrderAlreadyFilledError` 409、`OrderNotExecutableError`/oversell/no-cash 400
  - `models/user_transaction.py` 加 `portfolio_order_id` 字段（→ orders 反指针）
  - `models/portfolio.py:PortfolioOrder` 加 `user_transaction_id` 字段（→ transactions 正指针）
  - `database/repositories/portfolio_order_repository.py` 加 `mark_filled()` / `revert_filled()` 方法（key 在 `order_id`，不是 `alpaca_order_id`，因为这些 order 根本没经过 Alpaca）
  - `api/portfolio/decisions.py` 在响应里暴露 `filled_qty` / `filled_avg_price` / `filled_at` / `user_transaction_id`，前端可以渲染 `✓ Executed @ $X.XX` 状态 chip
- **feat(history-titles): 分析历史卡片用中文分类前缀** — 持仓分析/今日推荐 走 metadata.flow 区分，单股 Phase 2 / 个股聊天用 个股分析 兜底
  - `agent/portfolio/phase2_decisions.py:_store_portfolio_decision_message` 新增 `flow: str | None` 参数，写进 `metadata.raw_data.flow`
  - `agent/portfolio/flows.py` holdings 路径传 `flow="holdings"`、picks 路径传 `flow="picks"`
  - `api/portfolio/chats.py:get_portfolio_chat_history` 卡片 title 生成读 `flow` 字段：`holdings → 持仓分析 · ...`、`picks → 今日推荐 · ...`、单 symbol Phase 2 / non-portfolio chat → `个股分析 · ...`

### Removed
- **chore(dead-code): 删掉 `_write_summary_chat` 孤儿消息路径** — 之前每跑一次 holdings/picks 都会向一个虚拟的 `system-run-{flow}-{date}` chat_id 写一条 summary message，但**那个 chat_id 从来没在 `chats` collection 创建过**，所以这些消息是"没爹"的孤儿，sidebar 历史压根读不出来。真正写历史的是 `_store_portfolio_decision_message`（往 `Portfolio Decisions` chat 里塞 message），summary chat 完全是浪费。一并删掉 `flows.py` 里两处 `message_repo` 局部变量、`MessageRepository` / `MessageCreate` / `MessageMetadata` 三个 import。

## [0.21.4] - 2026-05-05

### Fixed
- **fix(picks-flow): `_SymbolStub` 没有 `watchlist_id` 字段，picks 流程在 Phase 1 收尾时崩** — 用户跑 today's picks 时报 `AttributeError: '_SymbolStub' object has no attribute 'watchlist_id'`。根因：`agent/portfolio/phase1_research.py:_run_phase1_research` 在 watchlist 分支收尾时无脑调 `watchlist_repo.update_last_analyzed(watchlist_item.watchlist_id, ...)`，假设入参一定是真实 `WatchlistItem`；但 picks 流程为 sector-filtered 候选股传的是 `_SymbolStub(symbol=...)` 鸭子类型对象（这些股票根本不在用户 watchlist 里，没 `watchlist_id` 可言）。改成 `wl_id = getattr(watchlist_item, "watchlist_id", None); if wl_id is not None: ...`——只在真 WatchlistItem 上戳 last-analyzed 时间戳，stub 直接跳过。

## [0.21.3] - 2026-05-05

### Changed
- **change(decisions): full_research 也走写入时预翻译，停掉点开 Full Research 时的 12 秒 LLM 等待** — 用户反馈"点开 full research 时明明已经显示中文了，还在灰色等翻译"。根因：`reasoning_zh` 上一版已经预翻译，但 `full_research`（Phase 1 给每个 symbol 的完整研究 markdown，几 KB）从来没存过中文版，前端 modal 里 `<Translated text={researchModal.text} />` 没传 `precomputed`，每次开 modal 都要现调一次 `/api/translate` 走 12-15 秒 Qwen 翻译，看到的"已经是中文"是 React Query 内存缓存命中而 `isLoading=true` 仍在挂着，所以一直灰着。
  - `agent/portfolio/flows.py:_persist_decisions` 现在同时预翻译 reasoning + full_research，但策略不同：reasoning 走原来的批量（一次 LLM 调用翻所有 symbol），full_research 因为单条几 KB 体积太大，每个 symbol **独立调用、并发跑**——一次性塞多条长 markdown 到 system+user prompt 风险高（容易超 `max_tokens=4096` 上限、JSON 数组解析容易被未转义引号搞崩、一条失败拖垮全批）。并发 + 独立成败让一个 symbol 翻失败不影响其它。
  - `services/translation_service.py:_llm_translate` 的 `max_tokens` 从 4096 提到 16384。中文 token 比英文密 ~1.5x，5-10KB 英文 markdown 翻成中文很容易超过 4096 → 之前长文本翻译其实是被静默截断的。短文（reasoning）实际消耗不到 1000 token，调高上限没成本。
  - `metadata.full_research_zh` 字段新加，`_persist_decisions` 写入时填充

## [0.21.2] - 2026-05-05

### Changed
- **change(decisions): Phase 2 写入时预翻译 `reasoning_zh`，停掉 DecisionTracker 的实时 LLM 调用** — 用户反馈"Decision Tracker 那边的翻译还是有问题：他还是第一次就是实时的 call llm 翻译，而不是直接显示已经有的翻译"。根因：`agent/portfolio/flows.py:_persist_decisions` 把 `reasoning_summary` 写进 `metadata.reasoning` 时从来没调过 `translate_for_persistence`，所以前端 `<Translated text={reasoning} />` 第一次渲染时只能现调 `/api/translate`，每条都要等一次 Qwen 翻译往返。修法跟 `chat_repository.py:title_zh` 完全一样：写入前批量喂给 `translate_for_persistence`，把 `reasoning_zh` 一起塞进 `metadata`，让前端用 `precomputed=` prop 直接显示存好的中文。`_persist_decisions` 加 `redis_cache` 参数，4 个调用点（holdings/picks 的 fallback 和 full pipeline 路径）都从 `app.state.redis` 透传进去。一次运行所有决策的 reasoning 走一次 batch 翻译，比按行触发省 LLM 调用数。注意：MongoDB 里已存的旧行没有 `reasoning_zh`，下次跑 Phase 2 之前展开旧 row 还会 fallback 到 lazy 路径，这是预期行为。

## [0.21.1] - 2026-05-05

### Changed
- **change(phase2-prompt): SELL 平多仓语义说清，reasoning 必须 cite 三个位的 anchor** — 用户反馈 MU 那条 SELL 决策的 entry $645 没在 reasoning 里点出锚点，只点了 stop $652 和 target $576。同时 SELL 平掉已有持仓时 stop_loss / take_profit 的字面语义有点拧巴（"涨破 $655 砍仓回平"在没有空仓的语境下不通），LLM 自己有时也写得含糊。`agent/portfolio/phase2_decisions.py` 的 Price Levels 章节加一段，明确 SELL=平多仓时三个价位的真实意思：`entry_price` = 挂卖单价，`stop_loss` = 价反向涨破就**撤单**别卖（不是真止损），`take_profit` = 卖单不成交时跌到这是补救 last-resort 平仓价。同时强制 reasoning_summary 必须为**三个价位都**点 anchor，不只是 stop/target。

## [0.21.0] - 2026-05-05

### Changed
- **change(technical-indicators): yfinance + pandas-ta-classic 升为主源，AV 降级 fallback** — `agent/tools/alpha_vantage/technical.py` 里 3 个 AV-direct 工具（`get_trend_indicator` SMA/EMA/VWAP、`get_momentum_indicator` RSI/MACD/STOCH、`get_volume_indicator` AD/OBV/ADX/AROON/BBANDS）现在先走本地 pandas-ta-classic 计算（基于 yfinance OHLCV 全量历史 bars），AV `TECHNICAL_INDICATOR` endpoint 只在 yfinance 失败时兜底。原因：AV free-tier 25 req/day 几次页面加载就被烤干，之前一旦超 quota 这 11 个指标全部消失，LLM 给 entry/stop/take_profit 的论据就掉一半；本地算法没 quota，跟之前 commit `1b2fee3`（"yfinance + FRED primary, Alpha Vantage demoted to fallback"）的方向一致。
  - 新建 `services/market_data/yfinance_indicators.py:compute_indicator(symbol, function, interval, time_period)`，每个 AV `function` 映射到 pandas-ta-classic 调用，输出列名重命名以匹配 `format_technical_indicator` 的契约（MACD → `MACD`/`MACD_Hist`/`MACD_Signal`；BBANDS → `Real Upper/Middle/Lower Band`；其余按 AV 风格起名）
  - `services/formatters/technical.py` 和 `services/formatters/__init__.py` 的 `format_technical_indicator(...)` 加 `data_source: str = "yfinance_local"` 参数；输出顶部那行 `Data Source: ...` 现在反映实际服务路径（happy path 显示 `yfinance_local`，AV 兜底显示 `alpha_vantage_fallback`）
  - 新依赖 `pandas-ta-classic>=0.5.44`（pandas-ta 的 numpy 2.x 兼容 fork；原版 `from numpy import NaN` 在 numpy 2.x 已删，装不上）

### Migration
- **必须 rebuild backend image**：deps 改了，`docker compose up -d --force-recreate backend` 不够，要先 `docker compose build backend` 再 up


## [0.20.6] - 2026-05-05

### Added
- **feat(decisions): Phase 2 决策三件套 entry / stop / target，且必须引用工具里的位** — `models/trading_decision.py` 的 `TradingDecision` 加三个 `float | None` 字段：`entry_price`（限价入场）、`stop_loss`（止损）、`take_profit`（止盈）。`gt=0` 校验，HOLD 必须为 None，BUY/SELL 必须填。`reasoning_summary` 同步要求"MUST cite the specific tool-derived levels you used"——光说"看好"没用，得点出 fib 0.618 / swing low / 阻力位这种工具里实际跑出来的位才行。`agent/portfolio/phase2_decisions.py` 在系统提示里加了一整节 "Price Levels (REQUIRED for BUY/SELL)"，逐条列清楚 BUY 的 stop 在 entry 下面、TP 在上面、SELL 反过来；同时给了样例 reasoning。落库走 `agent/portfolio/flows.py:_persist_decisions`：`entry_price → PortfolioOrder.limit_price`、`stop_loss → stop_price`，三个都额外塞 `metadata` 兜底（前端读 metadata 拿 take_profit，因为 PortfolioOrder 没有原生的 take_profit 列）。Phase 2 落库的 markdown 表格也从 4 列扩成 7 列：Symbol / Decision / Size % / Entry / Stop / Target / Confidence。

## [0.20.5] - 2026-05-05

### Fixed
- **fix(time): 「分析历史」卡片时间永远卡在 UTC** — `api/portfolio/chats.py` 给前端造的 `card_title` 是 `f"{symbol} · {msg_ts.strftime('%H:%M')}"`，UTC 13:49 直接拼成死字符串「`AAPL · 13:49`」，前端 i18n 救不了——它就是字面量。同一个文件的 `latest_timestamp` 也漏：Motor 默认 `tz_aware=False`，从 BSON UTC 读出来的 datetime 是 naive，`.isoformat()` 出来不带 `+00:00`，浏览器把它当**机器本地时间**解析（北京浏览器 = 北京视角），相对时间「N 分钟前」错 8 小时。这版两处都修：
  - `msg_ts.replace(tzinfo=UTC)` 兜住 naive datetime，`.isoformat()` 出来带 `+00:00`，前端 `new Date(...)` / `formatTimestamp` 能正确转 zh → Asia/Shanghai
  - `card_title` 改成嵌入完整 ISO 而不是 raw `HH:MM`：`f"{symbol} · {ts_iso}"`。前端 `ChatListItem` 配套加 `localizeTimestamps` 包装（frontend v0.15.2），把 ISO 替换为当前 locale 的 `HH:MM`

## [0.20.4] - 2026-05-05

### Fixed
- **fix(health): `/api/health` 的 `timestamp` 是死的桩字符串** — `api/health.py:65` 写死了 `"2025-01-20T00:00:00Z"`，注释说"will be auto-generated in production"，但根本没人改回来。线上每次 hit `/api/health` 都返这个 2025-01 的字符串，前端 HealthPage 拿来 `formatTimestamp` 渲染就一直是「2025-01-20」固定显示，跟实际服务状态完全脱钩。换成 `datetime.now(UTC).isoformat()`。

## [0.20.3] - 2026-05-05

### Fixed
- **fix(time): 报告生成时间和 LLM 看到的"今天"不对** — 上一版只修了**前端展示层**的 UTC+8 渲染，但**源头**还有大量 `datetime.now()`（无 tz）输出 ISO 字符串发给前端，前端 `new Date(naive_iso)` 把它当机器本地时间解析，结果中文界面下时间还是漂的。这版分两类修：
  - **写出去给前端显示的 ISO**：换成 `datetime.now(UTC).isoformat()`，输出带 `+00:00`，前端 `formatTimestamp` 看到 tz-aware 才能按 zh-CN 转 Asia/Shanghai。触达 `core/analysis/stochastic_analyzer.py`、`core/analysis/macro_analyzer.py`、`core/analysis/fibonacci/analyzer.py`（`analysis_date` 字段）；`api/analysis/technical.py`（`generation_date`）；`api/market/prices.py`（`last_updated` / `timestamp`）。
  - **塞进 prompt 给 LLM 看的"今天"**：换成 `datetime.now(ZoneInfo("Asia/Shanghai"))`。本地工具的目标用户在中国，UTC 比北京慢 8 小时，深夜跑分析时给 LLM 写"今天是昨天"。触达 `agent/llm_client.py:get_financial_agent_system_prompt()`、`agent/langgraph_react_agent.py:_today`、`agent/context.py:AgentContext.current_date/six_months_ago`（含 `from_dict` 兜底分支）、`services/formatters/base.py:current_year`（财务季度过滤）、`services/watchlist/analysis.py:end_date`（fibonacci 窗口端点）、`core/data/ticker_data_service.py:today`（缓存 TTL 判断）。
  - **不动**：`langgraph_react_agent.py:723,725` 的 `trace_id` / `thread_name`，纯字符串 ID，不渲染、不参与时间比较。

### Why
v0.15.0 (frontend) 加了 `formatTimestamp` 把 zh-CN locale 强制转 Asia/Shanghai，但前提是**输入的 ISO 字符串已经带 tz**（比如 `+00:00` 或 `Z`）。老代码大量 `datetime.now().isoformat()` 输出 naive 字符串，浏览器侧 `new Date()` 看到 naive 字符串会按浏览器本地时区当真——于是用户看到的"报告生成时间"会差一个时区偏移。源头修干净后，所有面向 UI 的时间戳都是显式 UTC，前端再统一按 locale 渲染，链路自洽。

## [0.20.2] - 2026-05-05

### Fixed
- **fix(analysis): 混合 naive/aware datetime 触发 `Tz-aware datetime.datetime cannot be converted to datetime64`** — Redis 缓存里旧的 OHLCV 条目走 `OHLCVData.from_dict()` 时 `datetime.fromisoformat()` 保留原字符串的 tz 信息（早期写入的可能是 naive），新拉的 yfinance 数据在 `DataManager._fetch_ohlcv_yfinance()` 里被强制 UTC-aware。两批拼起来时 `pd.DatetimeIndex([...])` 拒绝混合输入。把 `stochastic_analyzer.py` 和 `fibonacci/analyzer.py` 里的 `pd.DatetimeIndex(...)` 全换成 `pd.to_datetime(..., utc=True)`，这个调用会把混合列表里的所有 datetime 统一规整到 UTC-aware。`langgraph_react_agent.py` 里 `df.index >= pd.Timestamp(cutoff_date)` 比较前先 `tz_localize("UTC")`（market_service 返回的 index 可能是 naive，cutoff_date 是 tz-aware）。修完以后 SNDK/GOOGL/NVDA/CRWV 的 stochastic + fibonacci 指标都能正常算出来。

## [0.20.1] - 2026-05-05

### Fixed
- **fix(watchlist): 「等待首次分析」永远不消失** — `WatchlistAnalyzer.run_analysis_cycle()` 里 `for item in items` 循环读 `item.user_id`, 但 W5b 已经把 `user_id` 从 `WatchlistItem` 上拿掉了，每次手动触发都 `AttributeError: 'WatchlistItem' object has no attribute 'user_id'` 直接挂。把循环里几处 `item.user_id` 全删了——`analyze_symbol()` 和 `update_last_analyzed()` 自身的 `user_id` 形参都是 ignored optional，调用点不传也没事。修完以后 SNDK/GOOGL/NVDA/CRWV 的 `last_analyzed_at` 都正常落地了（finally 块兜底，单只 symbol 数据源失败不会卡住下一只）。

## [0.20.0] - 2026-05-05

### Added — 写入时翻译 (LLM 内容 zh-CN 上墙更快、Redis 1 天 TTL 不再失效)
之前 LLM 生成的英文内容（chat 消息正文 / chat 标题 / 最近一条预览）通过前端 `POST /api/translate` 按需翻译，命中 Redis 1 天 TTL；TTL 一过同一段又得重新打 LLM。这版改成写入 MongoDB **之前** 同步翻译，`<field>_zh` 持久化在 sibling 字段，前端拿到就直接渲染，不打 `/api/translate`。

- **`src/services/persistence_translator.py`** — 写路径翻译边界。包一层 `translate_batch(...)`：批量空字段短路、整批失败返 `{f"{k}_zh": None}` 不抛（前端走原本的 lazy fallback，不会破坏写入）。
- **`MessageRepository.create()`** — 构造 Message 之前对 `content` 翻一次，存到 `content_zh`。构造方法签名加 `redis_cache: RedisCache`（无 default，必传，避免静默走 lazy 路径）。
- **`ChatRepository.create()` / `update()`** — `title` 和 `last_message_preview` 同样处理。`update()` 路径有显式守卫：整批 translator 失败时（全 None）不把 `_zh` 写回 update 文档，避免一次 LLM 抖动把已有的好翻译覆成 None。`create()` 不需要这个守卫——insert 没有可覆盖的旧值。
- **`scripts/backfill_translations.py`** — 历史文档一次性回填。幂等：查询条件 `{ field: 非空 } AND { field_zh: missing/null }`，per-doc 再过滤防 race。`--dry-run` / `--collection messages|chats|all` / `--batch-size` / `--limit` 都齐了。失败的 doc 计入 `failed` 但不阻塞批次。`Makefile` 新加 `backfill-translations` target。
- **8 个调用点同步改造** — `main.py`、`chat_deps.py`、`history.py`、`portfolio/agent.py`、`portfolio/flows.py`、`watchlist/analyzer.py`、`scripts/test_repositories.py` 全部改成把 `redis_cache` 透传到 repository 构造。`PortfolioAnalysisAgent` 也加 `redis_cache` 参数。

### Tests
新加 17 个测试: `test_persistence_translator.py` (3) + `test_message_repository.py` (3) + `test_backfill_translations.py` (3) + `test_chat_repository.py` 写入时分支 (4 含 transient-failure 守卫回归)。所有 17 个全过。
现有的 29 个失败测试是 W5b user-id 移除等旧 refactor 的遗留 baseline，与本次修改无关（在父 commit 上同样失败）。

## [0.19.2] - 2026-05-05

### Changed
- **change(phase2-decisions): reasoning 不再截断 + 主表去掉 Reasoning 列** — 之前每条 decision 的 reasoning 在表格里被砍到 80 字加 `...`，关键判断丢了。把 Reasoning 列从主表里移除（长句撑表格列宽，强制横向滚动），改成表格下方 `#### Reasoning` 子段落，每条 decision 一行 `**SYMBOL (DECISION)** — 完整 reasoning`。表格保持 4 列紧凑可读，全文 reasoning 单独段落呼吸。仅影响新跑的分析；MongoDB 里已存在的旧 message 截断版本保持原样。

## [0.19.1] - 2026-05-05

### Changed
- **change(portfolio-chats): 分析历史每次跑都出独立卡片** — 之前 `/api/portfolio/chat-history` 按 chat 标题分组，所有 portfolio 分析都被塞进同一个 `Portfolio Decisions` chat，结果用户跑 N 次只看到 1 张侧边栏卡。现在改成"每条 message → 一张卡"，title 自动生成为 `Analysis · MU, AAPL, CRWV · 04:45`（symbols 截断 +N，时间精确到分）。`chat_id` 字段沿用 `message_id`，前端契约（`Chat[]` 形状）零修改。新加 `parent_chat_id` 字段方便调试。
- **change(portfolio-chats): DELETE / GET `/chats/{id}` 支持 message_id** — 路径参数以 `msg_` 开头时按 message 操作（删/读单条），其它形状沿用 chat 级行为，保留遗留删除路径不破坏。

## [0.19.0] - 2026-05-05

### Changed — yfinance / FRED 升主源，AV 退 fallback (~80% 配额释放)
Alpha Vantage 免费 25 req/day 几次页面加载就用光，导致 "Data sources are
severely rate-limited" 反复出现。把所有有免费替代源的路径全部翻转：

- **`DataManager._fetch_quote()`** 链路 `Finnhub → AV → yfinance` 改成
  `Finnhub → yfinance → AV`. yfinance 没 key、没每日上限，字段一致。
  这是单页加载里 quote 调用最密集的入口（每个 holding 都打一次）。
- **`DataManager._fetch_company_news()`** 同样：`Finnhub → AV → yfinance`
  改成 `Finnhub → yfinance → AV`. 注意 yfinance news 只有标题没有 sentiment
  打分；要打分仍会落到 AV。
- **`DataManager._fetch_ohlcv()`** 改成 yfinance 主、AV 备。新建
  `services/market_data/yfinance_bars.py` 适配器，把 yfinance Ticker.history
  的 1m/5m/15m/30m/60m/1d/1wk/1mo 映射到现有 Granularity，输出列名
  Open/High/Low/Close/Volume 跟 AV 一致，DataManager._dataframe_to_ohlcv
  零修改。验证 AAPL daily 61 bars / 1min 390 bars 全正确。
- **`DataManager._fetch_treasury()`** 改成 FRED 主、AV 备。FRED 是美联储官方
  数据源（DGS3MO/DGS2/DGS5/DGS10/DGS30），权威性高于 AV，且有现成的
  `FREDService`。FRED 不可用时回退 AV 兼容旧契约。
- **Agent quote tool** (`get_stock_quote`) 注入 DataManager，复用上面的
  Finnhub → yfinance → AV 链路。Tool schema 不变，只换实现。
- 新增 `tests/test_yfinance_adapters_parity.py` (5 项) — 验证 yfinance
  bars / quote / movers / search 的字段形状跟 AV 兼容。标记为
  `@pytest.mark.integration` 默认跳过，运行 `pytest -m integration`。
  pyproject 注册了 `integration` marker 并默认 `-m "not integration"` 。
- 修复 4 个 DataManager 单元测试 — 原本断言 AV mock 被调用，新链路下要先
  patch yfinance / FRED 失败才能断言 AV 落到。增量逻辑无回归。

仍然走 AV 的情形（无替代源）: insider transactions, earnings history,
ETF holdings, news sentiment scores. 这些都是低频 agent 工具调用，配额
释放后不再卡。

## [0.18.1] - 2026-05-05

### Fixed
- **fix(translation): research 报告开头的免责声明仍是英文** — Opus 4.7 看到 "Alpha Vantage rate-limited, but Finnhub data is sufficient..." 这种数据源元注释，会模糊地当成"非正文"保留原样不翻，导致 CRWV / AAPL 的 View Full Research 中段落混语种。强化 system prompt：明确要求"translate EVERY sentence — including disclaimers, data-source notes, error messages, and meta-commentary; no English sentence should remain"。同时加强 markdown 保护规则（headers / tables / lists 逐字保留，不合并不重排）。所有已污染的 zh-CN 缓存已清空，会按新 prompt 重新生成。

## [0.18.0] - 2026-05-05

### Added — i18n 翻译层 (Prompt 全英 + 展示前翻译)
- **新增 `POST /api/translate`** — body `{texts: string[], target_lang: "zh-CN"}` → `{translations: string[]}`. 同长度同顺序，永不 5xx（任何后端故障返回原英文）。
- **`services/translation_service.py`** — 用现有 `llm_factory.get_llm("verdict")`（claude-opus-4.7-xhigh）走批量翻译，sha1(text) → Redis 缓存，TTL 1 天。一次请求里：先并发查 Redis 拿命中，再把 miss 全部塞一次 LLM 调用，最后写回 Redis。设计上 prompt 系统不变，模型输出在前端展示前才翻译。
- **System prompt 规则**：保留 ticker / 数字 / 货币 / 百分比 / 日期原样，使用大陆财经术语，输出 JSON 数组。fence/extra prose 都能解析。
- **测试 13 条**（`test_translation_service.py`）：全命中跳过 LLM、全 miss 调一次 LLM 并缓存、混合命中只 miss 走 LLM 且顺序保留、LLM 错误回落原文不污染缓存、长度不匹配回落、markdown fence JSON 容错、英文 locale 短路、batch 上限 422、空数组 200、不支持的 lang 422。
- **实测**：第一次 NVDA + TSLA 翻译耗时 ~3s 真调 LLM；重复请求 87ms 命中缓存 0 LLM 调用。

## [0.17.3] - 2026-05-05

### Added
- **feat(symbol-search): yfinance 兜底，能查到本地 CSV + AV 都没有的票（如 CRWV）** — 用户搜 CRWV (CoreWeave，2025-03 IPO) 自动补全空的，因为本地 `sector_universe.csv` 只有 S&P 500 + Nasdaq 100 共 515 只，AV `SYMBOL_SEARCH` 又被 25 次/天的免费配额卡死。新增 `services/market_data/yfinance_search.py`：精确 ticker 走 `yf.Ticker(q).info`，模糊查询走 `yf.Search(q)`，结果过滤只留美股交易所（NMS/NYQ/PCX 等，不带点号），输出 `SymbolSearchResult` 形状直接复用前端契约。`/api/market/search` 现在三级链路 CSV → AV → yfinance，AV 抛错被吞，最终返空也不再 500。

## [0.17.2] - 2026-05-05

### Changed
- **feat(market-movers): yfinance 升为主源，Alpha Vantage 退到 fallback** — Alpha Vantage 免费 API key 每日 25 次配额几次页面加载就用完，导致 `加载市场行情失败 / 500`。yfinance (`yf.screen("day_gainers"/"day_losers"/"most_actives")`) 无 key、无每日上限、字段全。新加 `services/market_data/yfinance_movers.py` 适配器把 yfinance quote dict 映射成 AV 的 `{ticker, price, change_amount, change_percentage, volume}` 形状，前端零改动。`/api/market/market-movers` 路由现在先 yfinance；失败才回落 AV；都失败返 503（不是 500，因为不是我们崩了）。响应里加 `source` 字段标识本次数据来源。

## [0.17.1] - 2026-05-05

### Fixed
- **fix(holdings): cascade-delete user_transactions when a holding is deleted** — previously deleting a holding via the Holdings UI left orphan rows in `user_transactions`. The next attempt to delete those orphans called `apply_transaction(sign=-1)` which tried to SELL from a holding that no longer existed → `NoHoldingToSellError` → 409. Now `DELETE /api/portfolio/holdings/{id}` first removes all `user_transactions` for that symbol, then deletes the holding, keeping the ledger and holdings collection in sync. New `UserTransactionRepository.delete_by_symbol()` plus a regression test in `test_holdings_crud.py::TestDeleteHolding::test_cascades_transactions_for_symbol`.

## [0.17.0] - 2026-05-04

### Added — manual transactions ledger
- New `user_transactions` collection — separate from `portfolio_orders` (which now strictly carries AI decision rows). The user-entered ledger of "I really bought/sold this" with auto-sync to holdings.
- `POST/GET/PATCH/DELETE /api/portfolio/user-transactions` with reverse-and-forward holdings sync. Edit/delete reverse-applies the old version, then forward-applies the new one; oversell raises 400, holdings-state-changed mid-edit raises 409.
- `+ Add Transaction` button on Portfolio Holdings card header (next to Refresh / Add Holding).
- New `AddTransactionModal` (symbol + side + qty + price + total + executed_at + notes), uses shared `SymbolSearch` autocomplete.
- `RecentTransactions` rewritten — now shows ONLY user-entered transactions (not AI decision rows). Inline edit + delete buttons per row. Holdings auto-sync via the backend on every mutation.

### Fixed
- fix(holding-modal): mouse-drag to select numeric value triggered `onWheel→blur()` and killed the selection. Switched to `onWheelCapture={e.preventDefault()}` which stops scroll-wheel value changes without disturbing focus/selection.

## [0.16.1] - 2026-05-04

### Fixed (the v0.16.0 known issue is now resolved)
- **fix(react-agent): system prompt was a callable returning a string** — `create_react_agent(prompt=<callable>)` in newer langgraph expects either a string or a callable returning `list[BaseMessage]`. We were passing `(state) -> str`. langgraph silently treated the returned string as a user-role utterance, so the actual financial-analyst system prompt **never reached the LLM**. Result: every Phase 1 invocation returned generic "I'm ready to help" with `tool_executions=0`. Fixed by passing a static prompt string built at agent init. Date drift over a 24h cycle is acceptable (agent restarts on deploy).
- **fix(timeout): `react_agent` LLM timeout 30s → 180s** — Claude with 24 tool schemas needs ≥30s/step; 30s caused `APITimeoutError` swallowed by langgraph and surfaced as a zero-tool response.

### Changed — model assignments to top-tier per vendor
- `react_agent` → **claude-opus-4.7-1m-internal** (935k context — needed for 24 tools + history headroom)
- `deep_planner`, `portfolio_decisions`, `verdict` → **claude-opus-4.7-xhigh** (extra reasoning budget)
- `sub_technical` → **claude-opus-4.7**
- `sub_news`, `summary` → **gemini-3.1-pro-preview** (was -3-flash; now Gemini's flagship)
- `sub_debater` → **gemini-3.1-pro-preview** (unchanged — still cross-vendor for debate diversity)
- `sub_financial`, `portfolio_research` → **gpt-5.5** (unchanged — OpenAI flagship)
- `simple_chat` → **claude-haiku-4.5** (unchanged — fast cheap chat doesn't need flagship)
- All overrides removed from `.env.development` so per-vendor flagships flow through from `.env.base`.

### Verified
- Holdings flow on 3 holdings: ~90s end-to-end. Each symbol triggered 5-8 real tool calls (`tool_executions=5,8,8`), produced 1500+ char Chinese research reports citing concrete prices, RSI levels, news ("芯片股 4 月飙升 70%+"). For unknown OTC tickers (CRWCY) the agent transparently tried `get_stock_quote`, `get_company_overview`, `search_ticker("crown holdings")` and reported the data gap.

## [0.16.0] - 2026-05-04

### Changed — full Phase 1+2 pipeline behind both dashboard buttons
- **Analyze My Holdings** and **Today's Picks** no longer use the simplified single-LLM-call shortcut. Both now route through the existing `PortfolioAnalysisAgent`'s real Phase 1 (ReAct + 118 MCP tools per symbol) → Phase 2 (structured `PortfolioDecisionList`) pipeline, with Phase 3 deliberately skipped (no order optimization needed).
- Picks: universe → risk-adaptive filter to 50 → **capped at 20** for Phase 1 (`PICKS_PHASE1_CAP`) to keep runtime ≈5-15min instead of 25-75min. Phase 2 still picks Top 5 BUYs from those 20.
- Per-symbol research is **not** persisted as separate chats (no chat-list pollution). Instead the full Phase 1 markdown text rides on `portfolio_orders.metadata.full_research`. Deletion of the decision deletes the research with it.
- One **aggregated summary chat** per run is written to `messages` with `chat_id="system-run-{flow}-{date}"`, listing each symbol with its action / confidence / short reasoning. Replaces N per-symbol chats from the cron path.

### Added
- `phase1_research.py:_run_phase1_research(...suppress_chat=True)` and `_analyze_symbol(...suppress_chat=True)` — gates the per-symbol chat write so the dashboard flow can suppress chat-list pollution. Backward-compatible (default False).
- `flows.py` graceful fallback to the old simplified path when `app.state.portfolio_agent` is unavailable.
- `app.state.portfolio_agent` singleton built at startup (single LangGraph instance, not re-created per click).
- DecisionTracker frontend: per-row `[📄 View Full Research]` button in the expand pane → modal renders the full Phase 1 markdown text. Pure client-side state.

### Known issue (tracked separately)
- The ReAct agent currently returns generic "I'm ready to help" responses for some Phase 1 prompts, with `tool_executions=0` even after the built-in retry-with-nudge. Pipeline wiring is correct; the failure is inside `react_agent.ainvoke()` tool-binding under the cross-vendor llm_factory routing. Tracked as a follow-up.

## [0.15.6] - 2026-05-04

### Added
- feat(decisions): expandable reasoning row in DecisionTracker. AI's full reasoning text + suggested position size are now visible (was already in DB and API response, just never rendered). Added a confidence column (`Conf` 0-10). Click any row with reasoning to expand a blue-highlighted detail row underneath.

## [0.15.5] - 2026-05-04

### Fixed
- fix(transactions): "Recent Transactions" panel was showing HOLD signals as SELL orders. RecentTransactions.tsx:182 hardcoded `isBuy = side === "buy"`, so the new `side="hold"` rows fell through to the SELL branch (red icon, "SELL" badge). Compounded by the fact that HOLD signals shouldn't appear in a *transactions* panel at all (they're recommendations, not trades). Fix: `GET /api/portfolio/transactions` now filters out `decision_type="signal"` rows server-side. Real BUY/SELL orders (decision_type="order" or legacy null) still appear normally.

## [0.15.4] - 2026-05-04

### Added
- feat(holdings): on-demand price refresh — solves the "I just added AAPL but it shows $0" surprise.
  - `POST /api/portfolio/holdings/refresh-prices` — concurrent (sem=8) DataManager.get_quote per holding, persists via `repo.update_price`. Same logic as the nightly cron.
  - `[Refresh Prices]` button in the Portfolio Holdings card header (next to Add Holding). Uses `useRefreshHoldingPrices` mutation that invalidates holdings + summary queries.
  - `_enrich_with_quote()` now optionally `persist=True` writes the fetched price back to mongo. Wired so `POST /holdings` (Add and merge) saves the live price immediately, not just in the response.

## [0.15.3] - 2026-05-04

### Fixed
- fix(search): `GET /api/market/search` returned empty results because Alpha Vantage rate-limited the container's outbound IP (25/day on free tier; the same IP was already exhausted by other AV calls earlier in the session). Made search local-first: query the committed `sector_universe.csv` (515 large-caps) before falling back to AV. Result: instant exact/prefix/name matches for the bulk of common symbols, zero network. AV is only consulted when the local universe has no hit (rare ADRs, tiny caps).
- This is the same root-cause family as v0.13.1 + v0.15.1: code calling AV directly without DataManager fallback. Long-term cleanup wave still pending.

## [0.15.2] - 2026-05-04

### Changed
- feat(ui): added autocomplete to all symbol inputs by reusing the existing `<SymbolSearch>` primitive (already production-grade in ChartPanel).
  - **HoldingFormModal** (Add Holding modal): replaced plain `<input {...register("symbol")}>` with `<SymbolSearch>` wired through `setValue` + hidden register input. Edit mode keeps the locked plain input since symbol is the row identity.
  - **WatchlistPanel** (Add to watchlist): replaced plain symbol input with `<SymbolSearch>`; selection sets `newSymbol` state, form submit stays the same.
  - DecisionTracker symbol filter intentionally unchanged — it's a client-side filter over already-loaded rows, not a new symbol submission.
  - Backend already had `GET /api/market/search?q=` (Alpaca asset list, sub-100ms fuzzy match); zero backend changes needed.

## [0.15.1] - 2026-05-04

### Fixed
- fix(watchlist): adding symbols Alpha Vantage doesn't know (recent IPOs like CRWV, also any symbol when AV is rate-limited) failed with "Symbol not found in market" 400. Watchlist validation went straight to AV and didn't fall back. Added DataManager fallback (Finnhub → AV → yfinance) as a third validation layer in `backend/src/api/watchlist.py:add_to_watchlist`. CRWV now validates via Finnhub at $128.20 and saves successfully.

## [0.15.0] - 2026-05-04

### Added — Two-button portfolio analysis
- feat(analysis): two new dashboard buttons that trigger LLM-driven portfolio analysis
  - **Analyze My Holdings** — runs Phase 2 LLM on every existing position; returns BUY (add) / SELL (trim/exit) / HOLD per symbol
  - **Today's Picks** — sector-filtered Top 5 BUY recommendations from S&P 500 + Nasdaq 100 universe (no holdings overlap by design)
- New `user_settings` mongo collection: `cash_balance`, `risk_tolerance` (conservative/moderate/aggressive), `max_position_pct` (5-30). All three required (no defaults); buttons disabled until saved.
- New endpoints under `/api/admin/portfolio/`:
  - `GET/PUT settings` — round-trip with strict 422 on missing fields
  - `POST trigger-analysis?flow=holdings|picks` — fires `BackgroundTasks`; per-button idempotent (re-click during running returns existing run)
  - `GET status/{run_id}` — polled by frontend every 3s while pending/running
  - `GET universe/sectors` — derived from CSV, 11 yfinance sectors
- `recommendation_source` field added to `PortfolioOrder`; new `?source=holdings|picks` filter on `GET /api/portfolio/decisions`
- Risk-adaptive coarse universe filter: conservative→top 50 by market cap, aggressive→top 50 by 30d momentum, moderate→union of top 25 each (`backend/src/agent/portfolio/universe_filter.py`)
- `backend/data/sector_universe.csv` — 515 rows committed (S&P 500 + Nasdaq 100, sector + industry + market_cap_b)
- `backend/scripts/build_sector_universe.py` — one-time scraper with rotating UA, retry+backoff, jitter; failure-tolerant (1/516 missing)
- Frontend: `SettingsPanel`, `AnalysisButtons`, DecisionTracker source-tab toggle (All / Holdings / Today's Picks)

### E2E verification (real LLM calls)
- Holdings flow: 13s end-to-end on 3 holdings → AAPL=HOLD, NVDA=BUY, TSLA=SELL persisted
- Picks flow: 30s on Technology sector (25 finalists) → Top 5 = NVDA/AVGO/MSFT/ANET/LRCX, all BUY conf 7-9, position_size_pct=15 (= max_position_pct)
- Empty holdings short-circuit: status=done immediately, message "Add holdings first", zero LLM calls
- Empty sectors short-circuit: same pattern, message "No sectors selected — pick at least one."

### Notes
- Cron container's `run_portfolio_analysis.py` reference is still dead (script not created); to be addressed in a follow-up. The new flows run via the trigger endpoint, not the cron loop.

## [0.14.1] - 2026-05-04

### Added
- feat(holdings): nightly cron `scripts/refresh_holding_prices.py` walks every holding, calls `DataManager.get_quote` (Finnhub → AV → yfinance fallback), writes `current_price` + `market_value` + `unrealized_pl` back via `repo.update_price`. Wired into `portfolio-cron` loop alongside `run_portfolio_analysis.py` and `run_pnl_snapshots.py`. Closes the gap where `POST /holdings` enriched the response but never persisted to mongo, so subsequent GETs showed `current_price=null` until edited.
- E2E verified: insert 3 holdings → GET shows curr=null → run script → GET shows live prices + P&L for all three.

## [0.14.0] - 2026-05-04

### Added — Holdings CRUD
- feat(holdings): POST/PATCH/DELETE endpoints for direct holdings management
  - `POST /api/portfolio/holdings` — create new row, OR merge into existing same-symbol row using weighted-average cost: `new_avg = (q1*p1 + q2*p2) / (q1+q2)`. Returns enriched response with live `current_price` / `market_value` / `unrealized_pl` from `DataManager.get_quote` (3s timeout, gracefully nulls on failure)
  - `PATCH /api/portfolio/holdings/{id}` — partial update on quantity / avg_price; `cost_basis` recalculated in repo. Returns 404 if id unknown, 422 if both fields omitted
  - `DELETE /api/portfolio/holdings/{id}` — hard delete; returns 204 / 404
- Frontend: `HoldingFormModal` (react-hook-form + zod first usage in repo) wired into `PortfolioSummaryTable` — Add Holding button in header, Edit/Delete icons per row, inline `window.confirm` for delete
- 13 new backend tests covering POST happy/merge/422/uppercase, PATCH happy/404/empty, DELETE happy/404, quote enrichment success + failure paths

### Fixed
- fix(holdings): pre-existing repo crash on `HoldingCreate.avg_price=None` is now defended at the API layer with explicit 422
- The frontend already shipped `useAddHolding` / `useUpdateHolding` / `useDeleteHolding` mutation hooks calling these paths; the backend was the missing piece

## [0.13.1] - 2026-05-04

### Fixed (decision tracking E2E surfaced 4 bugs)
- fix(data-manager): `get_price_on_date` always returned None when Alpha Vantage was rate-limited (it only walked AV; Finnhub free tier has no historical bars). Now falls back to yfinance for the historical lookup path; also handles weekend horizons + market-still-open edge case via 4-day forward + 3-day backward scan window.
- fix(repo): `idx_alpaca_order` was unique+sparse, but `sparse=True` doesn't help when pydantic writes `alpaca_order_id` as null (field exists, just is null). Switched to `partialFilterExpression={"alpaca_order_id": {"$type": "string"}}` so the unique constraint only applies to documents that actually have a broker id. Without this fix, the second HOLD signal in any portfolio analysis run would fail with `DuplicateKeyError`.
- fix(pnl-service): `snapshot_decision` crashed with "can't compare offset-naive and offset-aware datetimes" when reading PortfolioOrder from mongo (pymongo returns naive datetimes by default). Coerce `created_at` to UTC-aware before the horizon comparison.
- fix(yfinance-fallback): the previous `_price_on_date_yfinance` window was too narrow (`-2d ... +max_forward+1d`) and used inefficient row-by-row dataframe filtering; rewrote as a `dict[date_str → close]` lookup with a 4-day pre-pad, and added backward fallback for the "horizon ends on a weekend or today before market close" case.

### Added
- All four bugs above were caught by an actual end-to-end run (insert 3 fake aged decisions → run cron → verify pnl_snapshots in mongo → hit /api/decisions). Documented in the cross-layer case study.

## [0.13.0] - 2026-05-04

### Added — Decision Tracking Dashboard
- feat(decisions): persist every AI decision (BUY/SELL/HOLD/Deep ReAct verdict) with the price at decision time, then mark to market at 7d/30d/90d horizons via cron
  - `PortfolioOrder` gains `decision_price`, `decision_type` ('order'|'signal'), `pnl_snapshots` dict (mongo migration-free; defaults handled at model level)
  - `OrderExecutor` now writes `OptimizedOrder.estimated_price` into `decision_price` (was being dropped)
  - `Phase3ExecutionMixin._persist_hold_signals` writes HOLD decisions as `decision_type="signal"` rows; uses `react_agent.data_manager.get_quote()` for the anchor price
  - `DeepReActAgent` accepts `order_repo` + `data_manager`; `verdict_node` parses `**Action**: Buy/Hold/Sell` and persists as `decision_type="signal"`
  - `DataManager.get_price_on_date(symbol, target_dt, max_forward_days=5)` — point-in-time close lookup with weekend/holiday forward-scan
  - New `services/pnl_service.py` — pure compute_pnl_pct + run_pnl_snapshot_job; sign-aware (SELL flips), idempotent
  - New `scripts/run_pnl_snapshots.py` — wired into the `portfolio-cron` daily loop
  - New `GET /api/portfolio/decisions?symbol=&decision_type=&limit=` returning decisions enriched with snapshots
  - Frontend: new `DecisionTracker` component (table + per-symbol Recharts line chart of P&L across horizons), mounted on `PortfolioDashboard`
  - Recharts ^2.12.0 added to `frontend/package.json` for the chart
  - 13 new pnl_service tests

### Changed
- `DataManager.__init__` is now `(redis_cache, alpha_vantage_service, finnhub_service=None)` — `finnhub_service` already defaulted to None in v0.12.0 so existing callers unaffected; documenting here for completeness

## [0.12.1] - 2026-05-04

### Fixed
- fix(gitignore): `backend/.env.example` was silently gitignored
  - Root `.env.example` was tracked (predates the rule), but any subdirectory `.env.example` was caught by `.gitignore:3:.env.*` with no escape clause
  - Added `!.env.example` and `!**/.env.example` exceptions; `.env.development` and other `.env.*` files remain ignored to protect local secrets
  - Force-added `backend/.env.example` to the repo so new clones see all the optional keys (Alpha Vantage / FRED / Exa / Finnhub / Langfuse) and the cross-vendor model defaults

### Changed
- chore(env-template): synced `backend/.env.example` model IDs with the v0.11.1 cross-vendor defaults (`claude-opus-4.7` / `gpt-5.5` / `gemini-3.1-pro-preview`, etc.) — were stuck on the pre-W8 short-hyphen Claude-only naming

## [0.12.0] - 2026-05-04

### Added
- feat(market-data): Finnhub as third provider with three-tier fallback chain
  - New `FinnhubService` (`backend/src/services/finnhub/`) — 60/min free tier, no daily cap
  - Three new LangChain tools: `finnhub_quote`, `finnhub_news`, `finnhub_insider_trades` (categorized into `news` and `financial` sub-agent groups)
  - Provider chain: Finnhub (primary) → Alpha Vantage → yfinance for quote / company news / insider trades
  - All three tools route through `DataManager`, never call `FinnhubService` directly — establishes the pattern future tools should follow
  - Tools register unconditionally; when `FINNHUB_API_KEY` is empty, `DataManager` silently starts at AV
  - 19 new tests (`test_finnhub_service.py` + `test_data_manager_fallback.py`) covering all 5 fallback states per method

### Fixed
- fix(data-manager): broken AV→yfinance fallback that was claimed in comments but never implemented
  - `_fetch_quote` previously caught all exceptions and re-raised `DataFetchError("alpha_vantage")` — there was no fallback branch
  - Now correctly routes to yfinance when both Finnhub and AV fail; only raises `DataFetchError("all_providers")` when all three providers fail

### Added — config
- `finnhub_api_key: str = ""` in `Settings` (declared in `core/config.py`)
- New cache key generators: `CacheKeys.company_news`, `CacheKeys.insider_trades`

### Added — interview docs
- `docs/interview/2026-05-04-finnhub-fallback-chain.md` — case study covering the integration plus the "stale comment lying about a runtime branch" pattern (third entry in the running interview-prep series)

## [0.11.2] - 2026-05-04

### Fixed
- fix(token-utils): `extract_token_usage_from_messages` always returned 0
  - Root cause: code used `getattr(msg.usage_metadata, "input_tokens", 0)` but LangChain's `usage_metadata` is a `TypedDict`, not an object — `getattr` always hit the default
  - Affected all vendors (Claude / GPT / Gemini), pre-existed before the cross-vendor refactor; surfaced while investigating `input_tokens=0 output_tokens=0` in Deep ReAct logs
  - Tests passed because they used `Mock(input_tokens=...)` (object) instead of real dict — fixed 6 test fixtures to use real dicts
  - Verified live: Claude/GPT/Gemini all now report non-zero token counts via `extract_token_usage_from_messages`

### Added
- `docs/interview/` — case-study notes for non-trivial bugs (context, reasoning, root cause, fix, takeaways) for interview prep. First two entries: ghost compose project + token getattr-on-dict bug.

## [0.11.1] - 2026-05-04

### Changed
- refactor(llm): cross-vendor per-role model assignments via Agent Maestro
  - Previously all roles routed to Claude (opus-4-7 / sonnet-4-6 / haiku-4-5)
  - Now mixed across three vendors for diversity and task fit:
    - **Claude** (opus-4.7): `deep_planner`, `portfolio_decisions`, `verdict`
    - **Claude** (sonnet-4.6): `sub_technical`
    - **Claude** (haiku-4.5): `simple_chat`
    - **GPT** (gpt-5.5): `react_agent`, `sub_financial`, `portfolio_research`
    - **Gemini** (3.1-pro-preview): `sub_debater` — cross-vendor debate so adversarial views aren't self-correlated
    - **Gemini** (3-flash-preview): `sub_news`, `summary`
  - Model IDs normalized to Maestro's native dotted format (e.g. `claude-opus-4.7`); short-hyphen aliases (`claude-opus-4-7`) still resolved by Maestro
- All vendors reach FinancialAgent through Maestro's Anthropic-compatible endpoint (`/api/anthropic`); single `ChatAnthropic` wrapper continues to work because Maestro performs vendor protocol translation server-side

### Added
- `backend/tests/smoke_cross_vendor.py` — per-role chat + tool-calling smoke test
- `backend/tests/e2e_deep_react.py` — full Deep ReAct flow driver (sub-agents → debate → verdict) for cross-vendor verification

## [0.11.0] - 2026-02-23

### Added
- feat(deep-agent): Debate quality improvement with independent verification
  - New yfinance news tool (`fetch_yfinance_news`) for independent market data
  - New Exa web search tool (`search_web_exa`) for independent news verification
  - Debater sub-agent rewritten with independent tools (yfinance + Exa, NOT Alpha Vantage)
  - Structured JSON concern/rebuttal parsing (`debate_types.py`)
  - Programmatic fact merging with `<system-reminder>` injection into verdict prompt
  - Symmetric debate topology: defense always responds before verdict
  - New graph: main_agent → debate → should_continue → verdict
  - Extended SSE event schemas (`deep_rebuttal_start`, `deep_rebuttal_result`)
  - 15 integration tests for full debate flow verification
  - `exa_api_key` config setting for debater independent verification

### Changed
- Refactored `deep_react_agent.py` orchestrator for symmetric debate protocol
  - Merged `research_node` + `rebuttal_node` into unified `main_agent_node`
  - `debate_node` now parses structured JSON via `parse_debater_output()`
  - `verdict_node` merges all concerns + rebuttals into verified facts reminder
- Updated debater SKILL.md files for independent tool usage

## [0.10.1] - 2026-01-11

### Added
- fix(agent): add historical prices tool to prevent date/price hallucination


## [0.10.0] - 2025-12-31

### Added
- feat(agent): Story 2.8 - Reusable Put/Call Ratio (PCR) Service with AI Tool
  - New `get_put_call_ratio` AI tool for per-symbol options sentiment analysis
  - Shared `DataManager.get_symbol_pcr()` with Redis caching (1-hour TTL)
  - ATM Dollar-Weighted methodology: ±15% price zone, $0.50 min premium, 500 OI
  - Rich markdown output with sentiment emoji indicators
  - Performance: Cache HIT 3ms vs Cache MISS 2528ms (843x improvement)
  - AI Sector Risk metric refactored to reuse cached PCR calculations
- Replace yield_curve with market_liquidity metric using FRED API (Story 2.7)


## [0.9.0] - 2025-12-30

### Added
- feat(insights): Story 2.6 - Options Put/Call Ratio metric with ATM Dollar-Weighted methodology
  - New OptionsMixin for Alpha Vantage HISTORICAL_OPTIONS endpoint
  - DML support for quotes and options data with caching
  - Contrarian scoring: Low PCR = High bubble risk (euphoria)
- feat(insights): Story 2.7 - Market Liquidity metric using FRED API data
  - New FREDService for SOFR, EFFR, and RRP Balance data
  - Replaces yield_curve metric with actual liquidity measures
  - Theory: "Bubbles require abundant capital to form"
- AI Sector Risk now has 7 metrics (was 6):
  1. AI Price Anomaly (17%)
  2. News Sentiment (17%)
  3. Smart Money Flow (17%)
  4. Options Put/Call Ratio (15%) - NEW
  5. IPO Heat (9%)
  6. Market Liquidity (13%) - REPLACED yield_curve
  7. Fed Expectations (12%)

### Changed
- Rebalanced composite weights for 7 metrics totaling 100%
- Updated all insights tests to expect 7 metrics

## [0.8.10] - 2025-12-30

### Added
- fix: Apply split adjustment to all OHLC prices for daily/weekly/monthly bars


## [0.8.10] - 2025-12-29

### Added
- fix(insights): increase cache TTL from 30min to 24hrs for instant page loads


## [0.8.9] - 2025-12-23

### Added
- Enable Redis caching for AI Sector Risk agent tools (30min TTL)


## [0.8.8] - 2025-12-14

### Added
- feat: add context compaction to chat API to prevent context window overflow

### Changed
- refactor(api): restructure API layer into modular packages
  - `analysis.py` → `analysis/` (fibonacci, technical, fundamentals, macro, news, history)
  - `chat.py` → `chat/` (endpoints, helpers, streaming/)
  - `feedback.py` → `feedback/` (crud, admin, comments, upload)
  - `portfolio.py` → `portfolio/` (holdings, orders, transactions, chats, history)
  - `market_data.py` → `market/` (prices, search, fundamentals, status)
- refactor(agent): modularize agent and tools architecture
  - Portfolio agent split into phase1_research, phase2_decisions, phase3_execution
  - Order optimizer split into base, plan_builder, executor, order_helpers
  - Alpha Vantage tools split into quotes, fundamentals, technical, news
- refactor(services): modularize service layer components
  - Alpaca service split into base, orders, positions, helpers, service
  - Response formatters split into base, fundamentals, market, technical
  - Watchlist analyzer split into analyzer, analysis, chat_manager, context_handler, order_handler
- refactor(shared): add centralized shared utilities module
  - New `backend/src/shared/` with formatters.py and sanitizers.py
  - Extracted formatting utilities from stock_analyzer.py
  - Consolidated sanitization logic from multiple modules

### Removed
- Deprecated monolithic API files (analysis.py, chat.py, feedback.py, portfolio.py)
  - All functionality migrated to new modular structure
  - Original files deleted after migration verified


## [0.8.7] - 2025-12-13

### Added
- feat: add get_stock_quote tool with market status API support


## [0.8.6] - 2025-12-10

### Added
- feat(compaction): Persist summary messages and delete old messages during context compaction
  - Added `is_summary` and `summarized_message_count` fields to `MessageMetadata`
  - Added `delete_old_messages_keep_recent()` method to `MessageRepository`
  - Compaction now persists summary to DB and cleans up old messages (keeps last N = `tail_messages_keep`)
  - Summary messages marked with `is_summary: true` are never deleted
- fix(portfolio): initialize OptimizedOrder priority to valid value to prevent ValidationError


## [0.8.5] - 2025-12-02

### Added
- feat(portfolio): Short position handling in order optimizer
  - Added `is_cover` field to `OptimizedOrder` model to identify cover orders
  - Automatic detection of short positions (negative quantity)
  - SELL decisions on short positions converted to BUY-to-cover orders
  - Cover orders execute with highest priority (risk reduction first)
  - Clear logging for short position conversions

### Changed
- refactor(portfolio): 3-phase architecture for portfolio analysis
  - Phase 1: Pure symbol research (concurrent, independent)
  - Phase 2: Single holistic decision call via `PortfolioDecisionList`
  - Phase 3: Programmatic order optimization (no additional LLM call)
  - Reduced LLM calls from N+1 to N+1 (research) + 1 (decision)
  - `SymbolAnalysisResult` no longer contains `decision` field
  - Added `PortfolioDecisionList` model for batch decisions
- refactor(config): Adjusted context window thresholds
  - `compact_threshold_ratio`: 0.5 → 0.75 (trigger at 75% instead of 50%)
  - `compact_target_ratio`: 0.1 → 0.25 (compress to 25% instead of 10%)

## [0.8.4] - 2025-11-29

### Added
- feat(portfolio): Failed order persistence with error tracking
  - Added `error_message` field to `PortfolioOrder` model for storing raw API error messages
  - Failed orders now saved to MongoDB with status="failed" and error details
  - Batch persistence using `create_many()` for failed orders
- feat(api): New `/api/portfolio/transactions` endpoint with filtering and pagination
  - Supports `limit`, `offset` pagination parameters
  - Supports `status` filter: "success" | "failed" | all
  - Returns `has_more` flag for UI "Show All" functionality
  - Query handles both plain status ("filled") and enum format ("OrderStatus.FILLED")

### Fixed
- fix(db): MongoDB sparse index for nullable `alpaca_order_id` field
  - Added `sparse=True` to allow multiple NULL values (failed orders have no Alpaca ID)
  - Fixes duplicate key error when persisting multiple failed orders

## [0.8.3] - 2025-11-28

### Added
- feat(portfolio): Structured output and order aggregation for portfolio analysis
  - Two-phase analysis with aggregation hook: Phase 1 (symbol analysis) → Phase 2 (order optimization) → Phase 3 (execution)
  - New Pydantic models: `TradingDecision`, `OptimizedOrder`, `OrderExecutionPlan`, `SymbolAnalysisResult`
  - `ainvoke_structured()` method in ReAct agent for reliable structured output extraction
  - Order optimizer module (`order_optimizer.py`) extracted from portfolio analysis agent
  - SELLs execute before BUYs to maximize buying power
  - Proportional scaling (Option A) when insufficient funds for all BUY orders
  - Eliminates unreliable regex parsing of LLM text responses

### Changed
- Refactored `portfolio_analysis_agent.py` to use structured output instead of regex parsing
- Extracted order aggregation/execution logic to separate `OrderOptimizer` class

## [0.8.2] - 2025-11-27

### Added
- feat(chat): auto-inject selected symbol from UI to agent context


## [0.8.1] - 2025-11-27

### Fixed
- **Watchlist Symbol Validation**: Enhanced validation with multi-layer fallback strategies
  - Primary: Exact symbol match in SYMBOL_SEARCH results
  - Fallback 1: High-confidence match (score >= 0.9)
  - Fallback 2: GLOBAL_QUOTE API direct validation
  - Added debug logging for troubleshooting validation failures
  - Fixes Bug #4: TSLA, AAPL, and other valid symbols now successfully validate

## [0.8.0] - 2025-11-26

### Added
- feat(portfolio): Unified portfolio-aware analysis prompt for holistic position management
  - Single prompt replacing 3 separate prompts (holdings, watchlist, market_movers)
  - Dynamic portfolio context injection (equity, buying_power, cash, all positions)
  - SWAP decision type for portfolio rebalancing recommendations
  - English-only prompt with language instruction placeholder
  - Position sizing suggestions based on total equity percentage

### Changed
- Enhanced portfolio analysis with full portfolio context awareness
- Improved decision recommendations considering liquidity and diversification
- Value opportunity detection for market panic situations

## [0.7.1] - 2025-11-19

### Added
- feat: add OSS presigned download URLs for feedback images
- feat: dual authentication mode for OSSService (static credentials + STS)
- Add 15-min delayed intraday data, GLOBAL_QUOTE endpoint, fix error messages

### Performance
- Batch chunk streaming: Reduce SSE events by 90% (CHUNK_SIZE=10 chars/event vs 1 char/event)
- Reduces typical 1300-char response from 1300 events to 130 events

### Reliability
- Add circuit breaker for tool event queue (MAX_QUEUE_SIZE=100) to prevent memory exhaustion
- Fix deadlock in background streaming loop - check agent completion in timeout handler
- Fix generator early exit bug preventing final answer streaming

### Bug Fixes
- Fix feedback images not displaying in private bucket (presigned download URLs)
- Fix tool progress message injection causing assistant message displacement
- Add agent completion check in asyncio.TimeoutError handler
- Ensure streaming completes gracefully when agent finishes

## [0.7.0] - 2025-11-15

### Added
- feat(agent): add real-time tool execution streaming with SSE callbacks and strategic prompt engineering


## [0.6.2] - 2025-11-14

### Added
- perf: add 30-minute Redis caching to market movers endpoint to reduce API calls


## [0.6.1] - 2025-11-14

### Added
- fix(data): Complete AlphaVantage integration across all TickerDataService instantiations


## [0.6.1] - 2025-11-14

### Added
- fix(k8s): add namespace env var and RBAC permissions for metrics API


## [0.5.20] - 2025-11-12

### Added
- Skip deprecated yfinance tests pending Alpha Vantage implementation


## [0.5.18] - 2025-11-12

### Added
- Replace yfinance with hybrid Alpaca + Polygon.io for market data to fix ACK rate limiting


## [0.5.15] - 2025-11-11

### Added
- Fix exact symbol search bug - direct ticker validation now runs when Search returns empty results


## [0.5.13] - 2025-11-06

### Added
- Fixed portfolio chart timeout (asyncio.to_thread), order persistence (PortfolioOrderRepository), agent recursion limit (25→50)


## [0.5.12] - 2025-10-31

### Added
- fix(oss): Use HTTPS for presigned URLs to fix mixed content error


## [0.5.11] - 2025-10-31

### Added
- feat(feedback): Add image upload with OSS integration


## [0.5.9] - 2025-10-26

### Added
- feat: Add consistent system prompt to v3 (Agent mode) for unified UX


## [0.5.8] - 2025-10-26

### Added
- fix: Credit system integration for v2 (Copilot) and v3 (Agent) modes with token extraction


## [0.5.5] - 2025-10-24

### Added
- fix(database): Change chat list query to use updated_at sorting for Cosmos DB compatibility


## [0.5.5] - 2025-10-23

### Added
- Add production Langfuse observability configuration


## [0.5.4] - 2025-10-14

### Added
- Fix MongoDB index name conflict causing backend startup failure


## [0.5.3] - 2025-10-13

### Added
- Complete type safety - Resolve 107 mypy errors with comprehensive type annotations


## [0.5.0] - 2025-10-10

### Added
- Add admin health dashboard with database statistics monitoring, implement admin role-based access control


## [0.4.10] - 2025-10-09

### Added
- Remove 500+ lines of deprecated session management code, simplify ChatAgent to direct LLM wrapper, eliminate SessionManager bridge pattern


## [0.4.9] - 2025-10-09

### Added
- Security: Implement atomic token rotation using MongoDB transactions to prevent race conditions during refresh token renewal. Falls back to best-effort on standalone MongoDB.


## [0.4.8] - 2025-10-08

### Added
- feat(agent): Context-adaptive LLM response style (structured for initial analysis, conversational for follow-ups)
- feat(agent): Instruction for LLM to match formatting style from conversation history
- feat(agent): Simplified system prompt with less over-instruction

### Changed
- Removed mandatory rigid structure ("The Verdict", "The Evidence") for all responses
- Split instructions into "Initial Analysis" vs "Follow-Up Questions" patterns

## [0.4.7] - 2025-10-08

### Added
- security: Implement dual-token JWT authentication (access + refresh tokens)


## [0.4.6] - 2025-10-08

### Added
- Add RefreshToken models and repository for JWT token refresh mechanism


## [0.4.5] - 2025-10-08

### Added
- security: Add comprehensive security contexts and fix K8s linting


## [0.4.3] - 2025-10-08

### Added
- Add DELETE /api/chat/chats/{chat_id} endpoint for chat deletion


## [0.4.1] - 2025-10-07

### Fixed
- **MongoDB Database Name Parsing** (Critical)
  - Fixed database name extraction to strip query parameters from Cosmos DB URLs
  - Bug: `mongodb://host/dbname?ssl=true` was parsed as `dbname?ssl=true` instead of `dbname`
  - Added validation to detect invalid characters in database names
  - Fixed in both `config.py` and `mongodb.py`
  - Hidden locally because local MongoDB doesn't use query parameters

### Added
- **Custom Exception Hierarchy**
  - Added `ConfigurationError` for configuration validation failures
  - Added `DatabaseError` for database connection/operation failures
  - Proper error categorization (400=user error, 500=database, 503=external service)

### Changed
- **Enhanced MongoDB Logging**
  - Log parsed vs raw database name when query parameters present
  - Log validation errors with detailed context (raw value, parsed value, invalid chars)
  - Added `error_type` field to all error logs for better debugging
  - Connection verification logged with `connection_verified=True`

## [0.4.0] - 2025-10-07

### Added
- **Authentication System**
  - Username/password registration with email verification
  - Email verification code system (6-digit codes, 5-min expiry)
  - Password-based login with JWT tokens
  - Forgot password flow with email verification
  - Bcrypt password hashing for security
  - Tencent Cloud SES integration for email delivery


### Planned
- LangChain agent integration
- Conversation history persistence
- AI chart interpretation with Qwen-VL
- User authentication system

---

## [0.1.0] - 2025-10-04

**Initial Release** - Walking Skeleton Complete

### Added
- **Core Infrastructure**
  - FastAPI application with health monitoring
  - MongoDB integration for data persistence
  - Redis caching for market data
  - Docker containerization
  - Kubernetes deployment configuration

- **Market Data Integration**
  - yfinance integration for stock data
  - Symbol search with validation
  - Price history retrieval (1d/1h/5m intervals)
  - Caching layer for market data (6-month expiry)

- **Financial Analysis Features**
  - Fibonacci retracement analysis with confidence scoring
  - Fundamental analysis (P/E, P/B, dividend yield, market cap)
  - Stochastic oscillator indicator (K%/D% calculations)
  - Support/resistance level detection
  - Price trend analysis

- **API Endpoints**
  - `GET /api/health` - Health check with database/cache status
  - `GET /api/market/search` - Symbol search with suggestions
  - `GET /api/market/price/{symbol}` - Historical price data
  - `POST /api/analysis/fibonacci` - Fibonacci analysis
  - `GET /api/analysis/fundamentals/{symbol}` - Fundamental analysis
  - `POST /api/analysis/stochastic` - Stochastic oscillator

- **Data Models**
  - Pydantic models for request/response validation
  - Type-safe API contracts
  - Comprehensive error handling

- **Testing**
  - Unit tests for analysis modules (100% coverage on stochastic)
  - Integration tests for API endpoints
  - Pytest configuration with coverage reporting

- **Code Quality**
  - Black formatting
  - Ruff linting
  - MyPy type checking
  - Pre-commit hooks

### Fixed
- **Dividend Yield Validation** (Critical Bug)
  - Smart detection for yfinance format inconsistencies
  - Handle both decimal (0.025) and percentage (0.71) formats
  - Cap at 25% to reject unrealistic data
  - Affected symbols: MSFT and others with inconsistent API responses

- **Symbol Validation**
  - Verify price data availability before suggesting symbols
  - Return only symbols with valid 5-day history
  - Prevent 422 errors from invalid symbol suggestions

### Changed
- **Error Handling**
  - Improved error messages for validation failures
  - Detailed 422 error responses with field-level errors
  - Graceful fallback for missing financial metrics

### Infrastructure
- **Deployment**
  - Azure Container Registry integration
  - Azure Kubernetes Service deployment
  - External Secrets Operator for secure configuration
  - Health probes (temporarily disabled for debugging)

- **Environment**
  - Development environment with hot reload
  - Staging environment on AKS dev namespace
  - CORS configuration for cross-origin requests

### Dependencies
- Python 3.12
- FastAPI 0.115.6
- Motor (async MongoDB) 3.6.0
- Redis 5.2.1
- yfinance 0.2.50
- Pandas 2.2.3
- NumPy 2.2.2
- Pydantic 2.10.6

### Breaking Changes
None - Initial release

### Migration Guide
No migration required - fresh installation.

### Known Issues
- Health check endpoint returns 400 (probes disabled temporarily)
- No authentication system (planned for v0.2.0)
- Manual deployment process (CI/CD planned for future)

### Security
- CORS configured for development (`["*"]`)
- TrustedHostMiddleware disabled in development
- Secrets managed via Azure Key Vault + External Secrets

---

## Version History

- **v0.1.0** (2025-10-04): Initial release - Walking skeleton complete
- **v0.2.0** (Planned): LangChain agent integration
- **v1.0.0** (Future): Production-ready release with authentication
