# Frontend Changelog

All notable changes to the Financial Agent Frontend will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
