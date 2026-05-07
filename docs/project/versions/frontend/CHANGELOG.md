# Frontend Changelog

All notable changes to the Financial Agent Frontend will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.22.1] - 2026-05-07

### Added
- **feat(holdings/watchlist): 价格旁显示"盘前 / 盘后 / 已收盘"标签** — 配套 backend v0.27.1，让用户一眼看出当前显示的不是 RTH 实时价。
  - 新增 `frontend/src/components/common/SessionBadge.tsx`：根据 `last_session` 渲染小号 pill —— `pre` → 琥珀色"盘前"，`post` → 靛紫色"盘后"，`closed` → 板岩灰"已收盘"，`regular` / null → 不渲染
  - PortfolioSummaryTable 表头 latest chip 和 Current 列价格旁、WatchlistPanel 价格旁全部改用 SessionBadge，移除原先散落的 inline 翻译逻辑
  - zh-CN portfolio.json：closed 文案 `休市` → `已收盘`，与新 badge 文案统一
  - DTO 复用现有 `last_session: "pre" | "regular" | "post" | "closed" | null`（v0.20.0 已加），SessionBadge 的 prop 仍叫 `session`，调用方传 `item.last_session` 解耦命名
  - 新增 `e2e_session_badge.py`（Playwright），用 `page.route` 拦截 holdings/watchlist API mock 4 种 session，断言对应 zh 文本与 `[data-testid=session-badge][data-session=X]` 出现/缺席

## [0.22.0] - 2026-05-07

### Added
- **feat(holdings/watchlist): 显示今日涨幅** — 配套 backend v0.27.0：
  - `Holding` / `WatchlistItem` 类型都加 `day_change_percent: number | null`
  - PortfolioSummaryTable 在 Current 和 Market Value 之间多一列 "Day %"，正数绿色 +X.XX%、负数红色 -X.XX%、null 灰色 -
  - WatchlistPanel 行同上，紧挨价格显示，不占额外行高
  - tfoot colSpan 从 4 调到 5（Symbol/Qty/Avg/Current/**Day%** = 5 列归 TOTAL）

## [0.21.0] - 2026-05-07

### Removed
- **change(portfolio-chart): PortfolioChart 组件 + 1D/1M/1Y/All 时段按钮 + Refresh 按钮 + 分析 marker modal 全删** — 配套 backend v0.26.0。Dashboard 主区现在是：portfolio value header → holdings 表 → settings/analysis → watchlist。屏幕利用率高了一档，holdings 表自己就够看
  - 删 `PortfolioChart.tsx`、`usePortfolioHistory` hook、`getPortfolioHistory` API、`PortfolioHistoryResponse`/`PortfolioHistoryDataPoint`/`AnalysisMarker`/`OrderMarker` 类型
  - `currentValue` 现在直接读 `summary.total_market_value`（之前 fallback 链优先 `historyData.current_value`）

## [0.20.0] - 2026-05-06

### Added
- **feat(watchlist): 每行显示现价 + session chip + 单股"分析"按钮**：
  - WatchlistItem 类型加 `current_price` / `last_price_update` / `last_session` (依赖 backend v0.25.0 enrichment)
  - 行渲染：`SYMBOL  $XXX.XX  [盘后]` 一行展示，session 非 regular 才显示橙色 chip
  - 每行 "Analyze Now" 按钮 — `useTriggerWatchlistAnalysis(symbol)` 透传，调 `POST /api/watchlist/analyze?symbol=BE` 跑单股；`analyzingSymbol` 本地 state 让只有当前行显示 spinner，批量按钮也复用

### Changed
- **change(refresh-prices): "Refresh Prices" 顺手 invalidate watchlist** — 之前只刷 holdings + summary 两张缓存。Watchlist 行的 enrichment 走 backend GET，invalidate 强制重抓让两张表的价显示对得上

## [0.19.0] - 2026-05-06

### Added
- **feat(ui): 持仓表头部加 session chip** — "Last updated: HH:MM · N ago" 后面跟一个橙色小标签：`盘前` / `盘后` / `休市`。RTH 时段和老数据（`last_session=null`）都不显示。提醒用户当前看到的 `current_price` / P/L 来自延长交易时段的成交，可能跟开盘价跳空。
  - `Holding` 类型加 `last_session: "pre"|"regular"|"post"|"closed"|null`
  - `pickLatestPriceUpdate` 现在返回 `{date, session}`（取 max-timestamp 那一行的 session 一起带出来，保证 chip 显示的 session 跟时间戳是同一行）
  - 新增 i18n keys `portfolio:session.{pre,post,closed}`（intentionally 没有 `regular` 键，因为 RTH 不显示）

### Notes
- 数据来源依赖 backend v0.24.0 — 老 backend 不会返回 `last_session` 字段，前端 `?? null` 兜底，chip 隐藏

## [0.18.1] - 2026-05-06

### Changed
- **chore(default-tab): App 启动后直接落到"投资组合"** — 之前默认 Market Insights，但日常使用主路径就是 PortfolioDashboard，每次手动切一下太啰嗦。e2e 脚本同步去掉 nav 点击步骤。

### Added
- `e2e_resize_columns.py` — Playwright 验证左右两列可拖拽 + 宽度持久化到 localStorage。

## [0.18.0] - 2026-05-06

### Added
- **feat(portfolio): 持仓表头部新增 "Last updated: HH:MM · N ago" 全局时间戳** — 取所有 holding 的 `last_price_update` 最大值，按 zh-CN 走 Asia/Shanghai 渲染绝对时间，旁边再带相对老化（s/m/h/d ago）。每分钟 tick 一次自动刷新相对时间，不需要重新拉数据。
- **feat(portfolio): 触发拉股价的两个动作完成后，自动刷新持仓 + 时间戳**：
  - **(A) Phase 2 持仓分析跑完** → `onRunComplete` 现在除了 invalidate `decisions` 还顺手 `refreshHoldingPrices.mutate()`，把所有 holding 的 `current_price` / `last_price_update` 重抓一遍写回 mongo。**重点**：`onRunComplete` 必须 `useCallback` 包起来 + 把 `refreshMut.mutate` 提到稳定引用，否则 `AnalysisButtons` 里的 `useEffect([..., onRunComplete])` 会被每次重渲染时新生成的 inline closure 触发 → mutate → isPending 变化 → 父组件再渲 → 新闭包 → 无限循环（`Maximum update depth exceeded`）。React Query v5 的 `mutate()` 函数引用是稳定的，但包它的 mutation 对象不稳定，所以必须从 mutation 里把 `mutate` 解构出来作为 useCallback 依赖。
  - **(C) PATCH /holdings/{id}** 编辑数量或均价 → 后端走 `_enrich_with_quote(persist=True)`，前端直接看到新的 `current_price` 和 `last_updated` 时间。

### Fixed
- **fix(holdings-time): 时间戳显示从 UTC 改回北京时间** — 之前 `formatTime` 接到的 `new Date(iso)` 因为后端 ISO 不带时区后缀，被 JS 当本地时间解析（看着像没换算）。后端 v0.23.0 修了序列化加 `Z` 后缀，前端这边不需要改代码，直接 `formatTime(date, i18n.language, {hour:'2-digit', minute:'2-digit'})` 就能拿到 `11:40` 而不是 `03:40`。

## [0.17.0] - 2026-05-06

### Added
- **feat(decision-tracker): Mark Executed UI——把 LLM 建议链跟实际成交链接通** — DecisionTracker 表格右侧多一列 `Action`，逻辑分三态：(1) `status=suggested` 的 BUY/SELL → 蓝色 `Mark Executed` 按钮；(2) `status=filled` → 绿色 `✓ @ $X.XX` chip 带 `Executed YYYY-MM-DD HH:MM` tooltip；(3) HOLD/signal 类的行 → 不显示按钮（HOLD 没东西可执行，per PRD spec）。点 `Mark Executed` 弹 modal：
  - **默认 qty**：BUY 走 `floor(cash_balance * position_size_percent / 100 / entry_price)`、SELL 走当前 holding qty（找不到就 fallback 到 1）
  - **默认 price**：LLM 给的 `metadata.entry_price`，没有时退回 `decision_price`
  - **Total 行实时计算**：显示成交金额 + 提示 cash 会增减多少
  - **错误展示**：mutation 报错时 modal 内 inline 红框显示，比 toast 容易和操作上下文对齐
  - **cash_warning 弹 alert**：如果 BUY 后 cash_balance 变负数，后端返 `cash_warning`，前端用 `window.alert` 提示（per PRD：允许负数但显眼提醒）
  - 模态背景 `onMouseDown + e.target===e.currentTarget` 关闭，避免拖选文本不小心关 modal（沿用 v0.11.7 AddTransactionModal 的约定）
- **feat(history-titles): 分析历史卡片中文分类前缀** — 后端 `chat-history` 返回的 title 现在直接带 `持仓分析` / `今日推荐` / `个股分析` 前缀，前端不需要任何改动就能展示。同一时间段内一眼能区分三种来源，之前所有卡片都是 `Analysis · symbols · time` 没法分

### Added (hooks)
- `useMarkOrderExecuted()`（`hooks/useDecisions.ts`）：包 `POST /api/portfolio/orders/{id}/mark-executed`，成功后级联 invalidate `["decisions"]` / `["portfolio-settings"]` / `["holdings"]` / `["user-transactions"]` 四张缓存，让 DecisionTracker、SettingsPanel cash 显示、Holdings 表三处自动刷新
- `DecisionRow` 接口扩展 `filled_qty` / `filled_avg_price` / `filled_at` / `user_transaction_id` 四个字段，用来渲染状态 chip 和点回 transaction 详情（后续）

## [0.16.4] - 2026-05-06

### Fixed
- **fix(vite): Windows Docker 下 HMR 失效** — `vite.config.ts` 的 `server.watch` 加 `usePolling: true` + `interval: 1000`。根因：Windows 主机 + Docker bind mount 下，主机端文件改动不会在容器里触发 inotify 事件——文件**内容是同步过来的**（容器 grep 立刻能看到新内容），但 Vite 的 chokidar watcher 收不到事件，于是 HMR 默默失效，每次改前端代码都要手动 `docker compose restart frontend`。开 polling 让 watcher 每秒 stat 一次文件，绕过 inotify。代价：watcher 进程持续占 ~2-3% CPU。表象记录：v0.16.3 改完 `<ResearchBody>` 之后浏览器还在显示 raw markdown，因为 Vite 完全没察觉文件变了——bundle 还是旧的。

## [0.16.3] - 2026-05-05

### Fixed
- **fix(decision-tracker): Full Research 弹窗按 markdown 渲染，不再显示 raw `#` `**` `-` 字符** — 之前 modal body 用 `<Translated text={...} as="div">` 配合 `whitespace-pre-wrap`，等于把 markdown 当纯文本贴出来，所有标题/列表/粗体/表格全是源码字符。新增内联 `<ResearchBody>` 组件，把 `useTranslated` hook 的输出（precomputed 中文 → 直出，否则走 `/api/translate` 兜底）喂给 `react-markdown` + `remark-gfm`，components map 抄 `ChatMessages.tsx` 的精简版（h1-h3、p、ul/ol/li、strong/em、code/pre、blockquote、table/th/td、hr、a）。modal 容器去掉 `whitespace-pre-wrap`/`font-sans`（会跟 markdown 渲染冲突），保留 `leading-relaxed` 让段落有呼吸感。翻译进行中 `opacity 0.7` 的 loading 提示从 `<Translated>` 迁到 `<ResearchBody>` 内层 div 上，行为一致。

## [0.16.2] - 2026-05-05

### Changed
- **change(decision-tracker): Full Research 弹窗也走 `precomputed=` 通道** — 配套 backend v0.21.3：`hooks/useDecisions.ts` 的 `DecisionMetadata` 加 `full_research_zh?: string | null`；`components/portfolio/DecisionTracker.tsx` 的 `ResearchModalState` 加 `text_zh` 字段，"View Full Research" 按钮 `onClick` 把 `d.metadata?.full_research_zh` 一起带进 modal state，modal 里 `<Translated text={researchModal.text} as="div" precomputed={researchModal.text_zh ?? null} />` 直接用后端写入时存好的中文，停掉 zh-CN 模式下 12-15 秒的 `/api/translate` 实时调用和灰色 loading 状态。后端没写 `full_research_zh`（旧行/翻译失败）时 fallback 到 lazy 翻译路径，行为兼容。

## [0.16.1] - 2026-05-05

### Changed
- **change(decision-tracker): reasoning 走 `precomputed=` 通道，不再现调 `/api/translate`** — 配套 backend v0.21.2：`hooks/useDecisions.ts` 的 `DecisionMetadata` 加 `reasoning_zh?: string | null`；`components/portfolio/DecisionTracker.tsx` 把 `<Translated text={reasoning} />` 换成 `<Translated text={reasoning} precomputed={(d.metadata?.reasoning_zh as string | null) ?? null} />`，AI Reasoning 展开行第一次渲染就直接拿后端写入时存好的中文，省掉 zh-CN locale 下的实时 LLM 翻译。后端没写 `reasoning_zh`（旧行/翻译失败）时 `precomputed=null`，回落到原有的 lazy 翻译路径，行为兼容。

## [0.16.0] - 2026-05-05

### Added
- **feat(decision-tracker): Entry / Stop / Target 三列上桌** — 配套 backend v0.20.6：`hooks/useDecisions.ts` 的 `DecisionMetadata` 加 `entry_price` / `stop_loss` / `take_profit` 三个 `number | null` 字段。`components/portfolio/DecisionTracker.tsx` 表头从 10 列扩到 13 列，新加 Entry / Stop / Target 三列：Entry 中性灰、Stop 红字（止损=亏，配色暗示）、Target 绿字（止盈=赢），数字用 `font-mono text-xs` 保证对齐。展开 reasoning 行的 `colSpan` 从 9 跟着升到 12，"show earlier decisions" 按钮的 `colSpan` 也同步。空值显示 `—` 而不是 `$NaN`。

## [0.15.2] - 2026-05-05

### Fixed
- **fix(time): 「分析历史」卡片标题时间按语言渲染** — 配套 backend v0.20.5：后端 `card_title` 现在嵌入完整 ISO 而不是 raw `HH:MM`，前端 `ChatListItem` 用 `Translated` 的 `render` prop 包一层 `localizeTimestamps`，把 ISO 替换为当前 locale 的 `HH:MM`（zh → Asia/Shanghai 24h；其它 → 浏览器本地）。`localizeTimestamps` 加 `options?: Intl.DateTimeFormatOptions` 第三参数让调用方控制输出粒度（这里只要时分，不要日期）。
- 新加 1 个 `localizeTimestamps` options 测试，245/245 vitest 全过

## [0.15.1] - 2026-05-05

### Fixed
- **fix(time): 聊天 markdown 里的 ISO 时间戳按 UI 语言渲染** — v0.20.3 把后端写出去的 ISO 都改成了 tz-aware（带 `+00:00`），前端组件级别用 `formatTimestamp` 也已经按 locale 转时区。但**报告 markdown 文本里直接拼的 ISO**（后端 `services/formatters/base.py` 的 `**Invoked:** {iso}`、`market.py` 的 `*Data Source: ... | Invoked: {iso}*`、`insights_tools.py` 的 `*Last updated: {iso}*`，以及前端 `analysisFormatters.ts` 自己拼的 `*Last Updated: ...*`）走 ReactMarkdown 渲染时是死字符串，formatTimestamp 救不了——用户在中文界面下看到的还是 UTC 时分。这版加 `localizeTimestamps(text, locale)`：扫描整段 markdown，把每个 ISO 8601（必须带 tz，naive 故意不匹配防误转）替换成当前 locale 对应的友好格式（zh-* → Asia/Shanghai；其它 → 浏览器本地）。`ChatMessages` 在喂 ReactMarkdown 前过一遍。配套把 `analysisFormatters.ts` 里 `formatFundamentalsResponse` / `formatStochasticResponse` / `formatMarketMoversResponse` 三个 hard-coded `new Date().toLocaleDateString("en-US", ...)` 也改成接 `locale` 参数走 `formatDate` / `formatTimestamp`，调用方 `useAnalysis.ts` 传 `i18n.language`。
  - **正则**：`/\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})\b/g` —— 量词全有界；naive ISO（无 tz）故意不匹配，免得对真·机器本地时间二次错转
  - **不触达**：`ChatListItem` 的相对时间（"3 分钟前"）、`WatchlistPanel` 的 `formatTimeAgo` —— 走自己的相对时间逻辑，不需要走 ISO 替换路径

### Tests
- 新加 4 个 `localizeTimestamps` 测试：markdown 整段替换 zh-CN 把 04:00 UTC 翻成 12:00、纯文本不动、naive ISO 不动、空串短路；244/244 vitest 全过

## [0.15.0] - 2026-05-05

### Added
- **feat(i18n-time): 中文界面时间统一按 UTC+8 (Asia/Shanghai) 渲染** — 后端 `datetime.now(UTC).isoformat()` 写出来的全是 UTC ISO，前端原来散在 11 个组件里直接 `new Date(iso).toLocaleString("en-US", ...)` / `.toLocaleDateString()`，UI 是中文但日期/时分按浏览器本地时区算（比如美国用户跑这个本地 fork，看到的就是美东时间 + 中文文案）。新加 `src/utils/timeFormatter.ts` 一层薄包装，导出 `formatTimestamp(iso, locale, options?)` / `formatDate` / `formatTime`：locale 以 `zh` 开头时把 `timeZone` 强制成 `Asia/Shanghai`，否则交给浏览器默认。`null/undefined/""` 直接短路返空串，`Number.isNaN(date.getTime())` 兜住非法字符串。日历类常量 (`ChatSidebar` 的 `selectedDate` 是 `YYYY-MM-DD`) 显式 `timeZone: "UTC"` 防 TZ rollover。
  - **触达组件**：`ToolMessageWrapper` (tool 调用时间), `ChatMessages` (消息时间), `ChatListItem` / `ChatSidebar` (chat 列表 + 日历 picker), `PortfolioDashboard` (analysis timestamps), `HealthPage` ("Last updated"), `InsightsPage` (category last_updated), `WatchlistPanel` (added_at), `DecisionTracker` (decision created_at — 通过 `locale` prop 传到 `DecisionRows`), `RecentTransactions` (transaction executed_at), `MarketMovers` (lastUpdated)
  - **不触达**：chart 轴标签 / candle tooltip (`useChart.ts`, `ExpandedTrendChart.tsx`) — 走自己的 chart 时间语义，不强加 zh-CN 默认时区；LLM 输出的 markdown 字符串 (`analysisFormatters.ts`) — 由 markdown 翻译管道处理，是另一条路径

### Tests
- 新加 `timeFormatter.test.ts` (7 tests)：UTC 04:00 → 北京 12:00、`timeZone` override 优先于 locale 默认、`null/undefined/""/invalid` 全部空串短路、`Date` 对象直接接受、`formatDate` 跨 UTC midnight 正确翻到北京次日；240/240 vitest 全过

## [0.14.1] - 2026-05-05

### Fixed
- **fix(watchlist): WatchlistPanel「立即分析」按钮 422** — 按钮原来打 `/api/admin/portfolio/trigger-analysis`（Nov 2025 那次重构留下的），但 backend v0.15.0 把这个 endpoint 拆成 `?flow=holdings|picks` 两个流，无 `flow` 参数 422 "Field required"，而且这俩 flow 都不分析 watchlist——holdings 只看持仓，picks 从 S&P/Nasdaq universe 里挑。改回去打专门的 `/api/watchlist/analyze`，名副其实，202 Accepted，后台跑 `WatchlistAnalyzer.run_analysis_cycle(force=True)`。配套更新 `watchlistApi.test.ts` 的 endpoint 断言, 233/233 vitest 全过。

## [0.14.0] - 2026-05-05

### Added — 写入时翻译消费 (UI 不再二次打 `/api/translate`)
后端 v0.20.0 把 `_zh` 翻译做成写入时的 sibling 字段。前端这边消费它：

- **`hooks/useTranslated.ts`** — 新加 `Options.precomputed?: string | null`。当前语言是 zh-CN 且传入了非空 `precomputed` 时，hook 直接同步返回 `{text: precomputed, isLoading: false, isTranslated: true}`，**不发 `/api/translate` 请求、不查 Redis**。precomputed 缺失（null/空）时退回原来的 lazy fetch 路径。
- **`components/Translated.tsx`** — 透传 `precomputed` 给 hook。
- **`types/api.ts`** — `Message`、`ChatMessage` 加 `content_zh?: string | null`；`Chat` 加 `title_zh?: string | null`、`last_message_preview_zh?: string | null`。
- **`ChatMessages.tsx`** — assistant 消息的整段 markdown 翻译现在以 `content_zh` 为 precomputed source；首次渲染零等待。
- **`ChatListItem.tsx`** — `chat.title` 和 `chat.last_message_preview` 现在用 `<Translated>` 包裹（之前直接 raw 渲染，zh-CN 下侧栏全英），分别拿 `title_zh` / `last_message_preview_zh` 做 precomputed。

### Tests
`useTranslated.test.ts` 新加 3 个 case 覆盖 precomputed 分支（zh-CN + 有 precomputed → 不打网络；zh-CN + null precomputed → 走 fetch；en + 任意 precomputed → 直返原文）。233/233 vitest 测试通过。

## [0.13.0] - 2026-05-05

### Added — Decision Tracker 升级
四件事一起做了:

- **KPI 汇总行** — 表格顶部新增 8 项指标: scored 数、7d/30d/90d 命中率 (BUY 涨/SELL 跌/HOLD ±2% 内为"对")、对应平均 P&L、置信度校准 (≥7 vs ≤5 的命中率对比)。颜色档: ≥60% 绿、45-59% 黄、<45% 红。一眼看出 AI 这段时间到底准不准。Tab/symbol 过滤直接 scope 这一行的统计。
- **按 symbol 折叠历史** — 表格主体改成 `groupBySymbol()`: 同一 symbol 默认只显示最新一条决策, 下方一行 `▶ Show N earlier decisions for SYMBOL` 按钮按需展开整段历史 (newest-first, 视觉缩进 + 浅灰背景)。Reasoning 展开和历史展开是两个独立状态 (`expandedReasoning` vs `expandedHistory`), 互不干扰。能一眼看出"AI 对 NVDA 5 月 BUY → 7 月 HOLD → 9 月 SELL"这种观点演变。
- **SELL P&L 颜色翻转** — 之前 PnlCell 一律绿正红负, 但 SELL 的"跌"才是 AI 对。新加 `decisionWasRight(side, pct)` 三态返回, PnlCell 接收 `side` 后按"决策好坏"上色: SELL -8% 现在显示绿色 (AI 对了), BUY -3% 显示红色 (AI 错了), HOLD ±2% 内显示绿色。tooltip 也明确写 "AI was right/wrong/neutral"。数字本身保留原符号方便看价格方向。
- **Research modal backdrop 拖选不关** — 跟 AddTransactionModal v0.11.7 同款 bug。改 `onClick` 为 `onMouseDown` + `e.target === e.currentTarget`, 拖选超出 modal 边界释放鼠标不再误关。

230/230 vitest 测试通过, 无回归。

## [0.12.1] - 2026-05-05

### Added
- **feat(i18n): 聊天里 LLM 整段 markdown 也走翻译** — Phase 2 的 "📊 Portfolio Trading Decisions" 整段 markdown（标题 + 表格 + 决策说明）原本不经过 `<Translated>`，所以中文 UI 下全英。`ChatMessages.MessageBubble` 现在对 `role === "assistant"` 的整段 `mainContent` 调 `useTranslated`，翻译后再交给 ReactMarkdown 渲染。表格、emoji、ticker、百分比通过 system prompt 规则保留。等待中给容器加 `opacity: 0.7`，无 spinner 不撑布局。

## [0.12.0] - 2026-05-05

### Added — LLM 内容自动翻译
- **`hooks/useTranslated.ts`** — 单段文本翻译 hook。i18n 当前语言以 `en` 开头时直接返回原文不打网络；`zh-CN` 时调 `/api/translate`，TanStack Query 缓存（`staleTime: Infinity`，因为同一段英文翻译永远不变），失败回落原文。返回 `{text, isLoading, isTranslated}`。
- **`components/Translated.tsx`** — 轻包装：`<Translated text={...} as="div" />`。`isLoading` 时给原文加 `opacity: 0.7` 提示，不出 spinner，不撑列表布局。
- **接入点**：
  - `DecisionTracker` 的 AI Reasoning 行内文本 + Full Research modal 正文
  - `ExpandableText`（被 SubAgentSection / DebateSection 复用）— 在组件内部直接调 `useTranslated`，所以 SubAgent resultSummary、Debate Concerns、Defense Summary 三处全部覆盖，零接入面变更
- **测试 5 条**（`hooks/__tests__/useTranslated.test.ts`）：英文 locale 立返不打 API、null/undefined 返空、zh-CN 真调 API 显译文、API 错落回原文、不支持的 locale 不打 API。
- 230/230 frontend 测试全过，无回归。

## [0.11.7] - 2026-05-05

### Fixed
- **fix(AddTransactionModal): 鼠标拖选输入框内容时 modal 误关 + 高亮消失** — Symbol / Quantity / Price 三个框都中招。两个独立的根因叠在一起：
  1. **真凶**：backdrop 用的是 `onClick={onClose}`，拖选时鼠标释放在 modal 外的暗色背景上 → 触发 click → 关掉整个 modal。`stopPropagation` 只挡了内部 click，挡不住"从内部开始、在外部松手"这种跨边界拖动。改成 `onMouseDown` 并要求 `e.target === e.currentTarget`，只有起点和终点都在 backdrop 才关闭。
  2. **附带**：modal 顶层用 `watch("quantity")` / `watch("price")`，每次任意字段输入都触发整个 modal re-render。改用 `useWatch({ control })` 让订阅只影响 effect 内部消费者，父组件不再 re-render，输入手感更稳。同时移除写死为 `false` 的死代码 `totalDirty`。

## [0.11.5] - 2025-12-29

### Fixed
- fix(insights): Smart tooltip positioning in ExpandedTrendChart
  - Tooltip now shows below data point when point is in top 40% of chart area
  - Tooltip shows above data point when in lower 60% of chart area
  - Added `overflow: visible` to SVG element to prevent clipping
  - Added `overflow-visible` class to chart containers in CompositeScoreCard and MetricCard
  - Fixes tooltip cutoff issue when hovering high-score data points

## [0.11.4] - 2025-12-11

### Added
- feat(portfolio): Analysis Type Filter for Portfolio Chat History
  - Dropdown filter with 3 options: All Types, Individual Analysis, Portfolio Decisions
  - Filters chat history between Phase 1 (individual symbol research) and Phase 2 (portfolio decisions)
  - Created `AnalysisTypeFilter` component with i18n support (EN/ZH-CN)
  - Integrated filter into `ChatSidebar` component for portfolio mode
  - Added i18n keys: `allTypes`, `individual`, `portfolio` in portfolio.json

## [0.11.3] - 2025-12-10

### Added
- feat(portfolio): Sort toggle for analysis history in Portfolio Chat Sidebar
  - Toggle button to switch between "Newest First" and "Oldest First"
  - Messages sorted using `useMemo` for performance
  - Default: Newest first (most recent analyses at top)
  - Added i18n keys: `sortBy`, `newestFirst`, `oldestFirst` (EN/ZH-CN)
- feat(ui): Add ICP registration footer (苏ICP备2025219095号-1) for China compliance

## [0.11.1] - 2025-11-29

### Added
- feat(portfolio): Enhanced RecentTransactions component
  - Status filter dropdown (All/Success/Failed)
  - "Show All" / "Show Less" toggle with scrollable container (max 100 items)
  - Visual distinction for failed orders (red background, alert icon)
  - Error message display for failed orders in styled red box
  - Uses new `/api/portfolio/transactions` endpoint with filtering

### Changed
- Migrated from `/api/portfolio/orders` to `/api/portfolio/transactions` endpoint
- Added i18n translation keys: `filterAll`, `filterSuccess`, `filterFailed`, `showAll`, `showLess`

## [0.11.0] - 2025-11-27

### Fixed
- **Symbol Search Input Sync**: Search input now correctly syncs when switching between chats (Bug #2)
  - Made SymbolSearch a controlled component with `value` prop
  - Input automatically updates to show current chat's symbol
- **Font Size Balance**: Reduced chat message font size for better visual consistency (Bug #9)
  - Changed paragraph and list text from `text-base` to `text-sm`
  - Improves readability and balances with chart panel
- **Help Button Position**: Moved help button from bottom-right to bottom-left (Bug #10)
  - Reduces content obstruction, especially on smaller screens
- **Market Movers Styling**: Removed non-functional hyperlink styling from stock symbols (Bug #11)
  - Symbols now display as plain text to avoid false affordance
  - Fixes user confusion about clickable elements

## [0.10.1] - 2025-11-16

### UX Improvements
- Tool progress cards now flow inline with messages (removed separate stacked area)
- Assistant response always appears after tool execution completes
- Request deduplication: Prevent concurrent agent invocations from rapid button clicks

### Bug Fixes
- Fix assistant message placeholder displacement when tool events inserted
- Add isPending check to prevent duplicate chat submissions

## [0.10.0] - 2025-11-15

### Added
- feat(chat): add real-time tool execution progress display with animated UI components


## [0.8.15] - 2025-11-12

### Fixed
- fix(frontend): standardize API URL env var to VITE_API_URL for ACK deployment
  - Replaced VITE_API_BASE_URL with VITE_API_URL in 5 files
  - Fixes CORS errors for portfolio chat, orders, and watchlist features in ACK
  - Ensures consistent environment variable usage across frontend

## [0.8.14] - 2025-10-31

### Added
- feat(feedback): Add image upload widget with drag & drop


## [0.8.11] - 2025-10-26

### Added
- feat: Agent mode toggle UI (v2 Copilot vs v3 Agent)


## [0.8.0] - 2025-10-10

### Added
- Add admin health dashboard page with database statistics, implement admin-only navigation


## [0.7.7] - 2025-10-08

### Added
- feat(ux): Assistant responses now fill full chat width (removed max-w-3xl and mr-8)
- feat(ux): Consistent, prominent display for analysis content (mimics Gemini layout)

## [0.7.6] - 2025-10-08

### Added
- feat(ux): NEUTRAL Stochastic signal uses yellow text (rgb(255, 215, 0)) on white background
- feat(ux): Completed dynamic color implementation for all signal types (OVERBOUGHT/OVERSOLD/NEUTRAL)

## [0.7.5] - 2025-10-08

### Added
- feat(ux): Stochastic signals now show color indicators (🔴 OVERBOUGHT, 🟢 OVERSOLD, 🟡 NEUTRAL)
- feat(ux): Stochastic signals display meaning in table (e.g., "OVERBOUGHT (Potential Sell Zone)")
- feat(ux): Recent signals show color emojis (🟢 BUY, 🔴 SELL) on independent lines
- feat(ux): Fibonacci analysis uses flexible lists instead of rigid tables
- feat(ux): Fibonacci levels are now collapsible (click to expand) - starts collapsed
- feat(ux): Key trends shown as numbered list (top 3 if available)

## [0.7.4] - 2025-10-08

### Fixed
- fix(ux): Tables now render properly with borders and styling (added table components to ReactMarkdown)
- fix(ux): Removed redundant Summary section from Stochastic analysis (duplicated table data)

## [0.7.3] - 2025-10-08

### Fixed
- fix(ux): Auto-scroll now scrolls to latest user message (like Gemini chat) instead of bottom

## [0.7.2] - 2025-10-08

### Added
- feat(ux): User messages for quick analysis button clicks (shows "Start X analysis for symbol...")
- feat(ux): Table-based analysis formatting for better readability
- feat(ux): Removed redundant explanatory text from analysis outputs

## [0.7.1] - 2025-10-08

### Added
- feat(ux): Auto-scroll to chat messages when new messages arrive
- feat(ux): BLUF-formatted analysis output (Bottom Line Up Front principle)

## [0.7.0] - 2025-10-08

### Added
- feat(auth): Frontend dual-token JWT authentication with auto-refresh


## [0.6.1] - 2025-10-08

### Added
- fix: Update nginx to listen on port 8080 for non-root compatibility


## [0.4.5] - 2025-10-08

### Added
- Add chat delete UI with optimistic updates and confirmation dialog


## [0.4.1] - 2025-10-07

### Fixed
- **API URL Fallback to Localhost** (Critical)
  - Fixed `VITE_API_URL` fallback logic treating empty string as falsy
  - Bug: `const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000"`
  - Empty string is falsy in JavaScript, so fallback to localhost:8000 was triggered
  - Browser tried to connect to user's local machine instead of relative API URLs
  - Changed fallback to empty string for proper relative URL behavior
  - File: `frontend/src/services/authService.ts`

### Architecture
- **Clarified Pod Architecture**
  - Frontend and backend run in **separate pods** (not same pod)
  - Frontend pod serves static files via nginx
  - React JavaScript runs in **user's browser**, not in pod
  - Ingress routes: `/api/*` → backend pod, `/*` → frontend pod
  - Browser needs relative URLs to reach backend via ingress

## [0.4.0] - 2025-10-07

### Added
- **Authentication UI**
  - Login page with email/password fields
  - Registration flow: email → verification code → username/password
  - Forgot password flow with email verification
  - JWT token storage in localStorage
  - Auto-login after successful registration/password reset
  - Error handling and validation messages


### Planned
- Advanced charting with TradingView integration
- User authentication and session management
- Chat history persistence
- Mobile responsive design improvements

---

## [0.1.0] - 2025-10-04

**Initial Release** - Walking Skeleton Complete

### Added
- **Core UI Components**
  - Chat interface for conversational analysis
  - Message input with analysis parsing
  - Response display with formatted results
  - Loading states and error handling

- **Market Data Features**
  - Stock symbol search with autocomplete
  - Interval selection (1d/1h/5m)
  - Period selection (1mo/3mo/6mo/1y/2y)
  - Price chart visualization (placeholder)

- **Analysis Integration**
  - Fibonacci retracement analysis display
  - Fundamental analysis cards
  - Stochastic oscillator visualization
  - React Query for API state management

- **Infrastructure**
  - React 18 with TypeScript 5
  - Vite build system
  - TailwindCSS styling
  - Nginx production server
  - Docker multi-stage builds
  - Kubernetes deployment

- **API Client**
  - Axios-based API client with error handling
  - Environment-aware baseURL configuration
  - Request/response type definitions
  - Health check integration

### Fixed
- **Frontend BaseURL Hardcoded** (Critical Bug)
  - Smart baseURL detection for production vs development
  - Use relative URLs in production for nginx proxy
  - Prevents CORS errors in deployed environment

### Changed
- **Message Parsing**
  - Extract symbol from user messages
  - Parse interval and period preferences
  - Default to sensible values (1d, 3mo)

### Infrastructure
- **Deployment**
  - Azure Container Registry integration
  - Azure Kubernetes Service deployment
  - Nginx reverse proxy for API calls
  - Production-optimized builds

- **Development**
  - Hot module replacement (HMR)
  - ESLint and Prettier configuration
  - TypeScript strict mode

### Dependencies
- React 18.3.1
- TypeScript 5.7.3
- Vite 6.0.7
- TailwindCSS 3.4.17
- React Query (TanStack Query) 5.64.2
- Axios 1.7.9

### Breaking Changes
None - Initial release

### Known Issues
- No chart visualization (placeholder only)
- No conversation history persistence
- No user authentication
- Mobile UI needs optimization

---

## Version History

- **v0.1.0** (2025-10-04): Initial release - Walking skeleton complete
- **v0.2.0** (Planned): Advanced charting and UI improvements
- **v1.0.0** (Future): Production-ready with auth and full features
