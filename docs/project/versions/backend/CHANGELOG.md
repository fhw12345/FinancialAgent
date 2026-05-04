# Backend Changelog

All notable changes to the Financial Agent Backend will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
