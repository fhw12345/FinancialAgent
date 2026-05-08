# Backend Changelog

All notable changes to the Financial Agent Backend will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.27.16] - 2026-05-09

### Added — Wave 3 (W3.8 SEC EDGAR Form 4 atom feed fetcher)

- **W3.8 `Form4Client` async EDGAR client** — new module `src/agent/tools/sec_edgar/form4.py` adds a self-contained httpx-based fetcher for the Form 4 atom feed (insider transaction filings). Public surface: `Form4Client(user_agent=..., rate_per_sec=..., transport=..., timeout_sec=10.0)` async context manager exposing `lookup_cik(symbol) → str | None` and `fetch_form4_atom(symbol, count=40) → str | None`. Scope is deliberately limited to "fetch the bytes EDGAR served us" — parsing the per-filing 10b5-1 plan markers / transaction codes / post-transaction holdings is W3.9; the schema upgrade is W3.10. Decoupling those layers makes each separately testable and keeps W3.8 small enough to ship in one commit.
- **D4 default User-Agent `ffffhhhww@qq.com`** — `get_user_agent()` reads `SEC_EDGAR_USER_AGENT` env var, treats empty / whitespace-only values as missing, and falls back to the PRD-D4 default. Per D4 the fetcher MUST NOT fail-fast when the env var is unset — SEC gives a soft "please identify yourself" warning rather than refusing service. Every request sends `User-Agent: ffffhhhww@qq.com` plus `Accept: application/atom+xml,application/xml,text/xml,*/*` so SEC's nginx layer accepts the response.
- **PRD AC #5 rate limit (under 10 req/s)** — `_TokenBucket` is a tiny in-process token bucket guarded by a single asyncio.Lock so concurrent `await client.fetch(...)` calls cannot consume tokens out of order. Default `rate_per_sec=8.0` (not 10) — the bucket starts full so the first burst can fire `capacity` requests with no delay; using 8 leaves comfortable headroom for the initial burst plus the next-second refill to stay under SEC's documented 10/s ceiling. Tests can override with `rate_per_sec=1000.0` to keep wall-clock fast.
- **CIK lookup via `https://www.sec.gov/files/company_tickers.json`** — once-per-process cached map of `ticker → 10-digit zero-padded CIK`. Second `lookup_cik()` call does NOT re-hit the endpoint (covered by a dedicated test); SEC's tickers JSON is ~30k rows so re-fetching for every Form 4 query would burn the rate-limit budget on metadata alone. Symbol matching is case-insensitive (`aapl` → `0000320193`). Unknown symbols (private, delisted, foreign) return `None` with a single structured warning log per miss.
- **`fetch_form4_atom(symbol, count)` returns raw XML text** — URL template is the `cgi-bin/browse-edgar` atom variant (`type=4&output=atom`) with the 10-digit CIK and a count clamped into `[1, 100]` to match SEC's documented limits. The response body is returned verbatim so W3.9's parser can choose its XML library without coupling to httpx response objects. HTTP errors propagate (`raise_for_status()`) — the caller decides retry vs. fall-through to the existing AV/Finnhub insider tools.
- **17 unit tests** in `tests/test_form4_fetcher.py` cover: env-fallback (default + override + whitespace), CIK lookup (zero-padded 10-digit, case-insensitive, unknown→None, single ticker-map fetch via call counting), User-Agent header (default value, explicit override), atom fetch (raw body, URL templating with padded CIK + count, count clamping at both ends, unknown-symbol short-circuit, no atom call when CIK lookup fails), the URL-template constant (pin path / `type=4` / `output=atom` / placeholders), rate limit (50 sequential calls measured under 10 req/s with the production rate, 20 calls in <1s with rate=1000 to confirm the override works), HTTP error propagation (`HTTPStatusError` on 503). All tests use `httpx.MockTransport` — zero real-SEC traffic; the live integration test is W3.13 (`@pytest.mark.integration`).

Bumps backend 0.27.15 → 0.27.16.

## [0.27.15] - 2026-05-09

### Added — Wave 3 (W3.6 Phase2 prompt cites source IDs)

- **W3.6 thesis bullets must end with the matching source-ID token** — every Phase2 BUY/SELL decision passing through `Phase2DecisionsMixin._make_portfolio_decisions` is now told that each `thesis` bullet which names "a number, ratio, growth rate, transaction, headline, or insider event MUST end with the matching source-ID token in square brackets" — the same `[FH-Q-AAPL-2026-05-09]` / `[AV-OV-NVDA-2025-09-30]` / `[YF-CF-MSFT-2025-12-31]` / `[FH-N-AMZN-2026-05-08]` / `[FH-INS-TSLA-2026-05-07]` tokens that the W3.2 / W3.3 / W3.4 / W3.5 tool wrappers append in their `Source: <provider> [<ID>] asof <iso>` footnotes. Pure qualitative-judgement bullets ("the cohort is rate-sensitive") may skip the citation — we don't want to push the LLM toward fabricating fake IDs to satisfy a blanket rule.
- **Worked-example demonstration** — the BUY worked example in the same prompt now shows three thesis bullets each carrying a different family of source-ID token (`[FH-N-…]` for a news-derived guide, `[AV-OV-…]` for an overview-derived margin, `[FH-N-…]` for a buyback announcement). LLMs follow concrete demonstrations more reliably than imperative rules — we learned this on the W2.10 base-rate citation rollout.
- **Strong language** — uncited thesis bullets are framed as "research malpractice" with a forward reference to a future consistency_gate check + dashboard "uncited" warning chip. The same phrasing the W2.10 scenario-probability rule used; the LLM took it seriously there.
- **5 source-inspection unit tests** in `tests/test_phase2_thesis_source_ids.py`: rule presence (whitespace-collapsed match because the rule wraps across multiple source lines), each Wave-3 wrapper family represented in the example list, "research malpractice" strong-language guard, qualitative-bullet escape hatch present, worked-example thesis carries ≥3 bracketed source-ID tokens. Existing 6 tests in `test_phase2_required_research_blocks.py` continue to pass — the W3.6 wording does not regress any of W2.7's required-block framing.

Bumps backend 0.27.14 → 0.27.15.

## [0.27.14] - 2026-05-09

### Added — Wave 3 (W3.5 insider-tool Source-wrap)

- **W3.5 `finnhub_insider_trades` emits a Source-style footnote** — the Finnhub-backed insider tool used by the Phase1 ReAct agent now ends its successful return with `Source: finnhub [FH-INS-AAPL-2026-05-09] asof 2026-05-09T00:00Z`, matching the W3.2 / W3.3 / W3.4 shape. Field code is `INS`, same as the AV-side `get_insider_activity` footnote shipped in W3.3 (commit 815f233) — both insider tools now carry citation handles, so the Phase2 prompt's W3.6 source-ID rule will cover insider claims regardless of which tool the agent picked.
- **Provider attribution defaults to "finnhub"** — the actual chain in `DataManager._fetch_insider_trades` is Finnhub primary → Alpha Vantage premium (often 403s) → yfinance fallback. The footnote labels the *primary* provider; finer post-fallback attribution is a follow-up (same trade-off as W3.4).
- **`asof` = newest transaction date, NOT `now()`** — same rationale as W3.4 news: the freshness of an insider bucket is meaningfully different from when the tool ran. A 6-week-old "last insider sale" cited tomorrow should still read as 6 weeks stale in its footnote, so the wrapper computes `asof` from the latest row across the returned list. The helper `_insider_latest_asof()` walks each row, looks up the date under any of `transactionDate` / `filingDate` / `Date` / `Start Date` (the same fallback chain the existing line renderer used), parses the string with `_parse_row_date()` (Finnhub `YYYY-MM-DD`, AV ISO with seconds, yfinance `DataFrame.to_dict()` shape), and skips malformed entries — a single bad row never kills the footnote.
- **No footnote on empty / failed paths** — same back-pressure behaviour as W3.4: if `data_manager.get_insider_trades` returns an empty list, the tool returns "No recent insider transactions" without a footnote; if it raises, the tool returns "Failed to fetch insider trades" without a footnote. The W1.10 consistency_gate would otherwise accept a thesis citation that points to a "source" we never actually fetched from.
- **`_insider_source_id(provider, symbol, asof)` helper** lives in `tools/finnhub/insider.py` next to its primary user, with the same `{PREFIX}-INS-{SYMBOL}-{YYYY-MM-DD}` shape as the W3.3 `get_insider_activity` footnote. Provider prefixes match across all Wave-3 wraps (`finnhub→FH`, `alphavantage→AV`, `yfinance→YF`).
- **13 unit tests** in `tests/test_insider_tool_source_wrap.py` — 4 for `_insider_source_id` (each prefix variant + unknown-provider fallback), 2 for `_row_date_str` / `_parse_row_date` (multi-shape date keys + multi-format parsing including the trailing-Z ISO yfinance produces), 3 for `_insider_latest_asof` (newest pick / malformed-row skip / empty-or-all-bad → None), 4 for the tool itself via `tool.ainvoke()` with stubbed `DataManager` (footnote with truthful asof, no footnote when empty, no footnote on provider failure, yfinance-shape rows still parsed correctly). Wave-3 source-wrap suite (`test_insider_tool_source_wrap` + `test_news_tool_source_wrap` + `test_quote_tool_source_wrap` + `test_fundamentals_source_wrap` + `test_fundamentals_fallback` + `test_source`) is 70/70 green.

Bumps backend 0.27.13 → 0.27.14.

## [0.27.13] - 2026-05-09

### Added — Wave 3 (W3.4 news-tool Source-wrap)

- **W3.4 both news tools emit Source-style footnotes** — `finnhub_news` (DataManager-backed; primary provider in the Finnhub→AV→yfinance chain is finnhub) and `get_news_sentiment` (AlphaVantage-only) each now end their successful return with one line in the W3.2/W3.3 shape: `Source: finnhub [FH-N-AAPL-2026-05-09] asof 2026-05-09T14:30Z` / `Source: alphavantage [AV-N-AAPL-2026-05-09] asof 2026-05-09T14:30Z`. The bracketed token is the citation handle the W3.6 Phase2 prompt will require thesis bullets to reference; field code is `N` for news.
- **`asof` = newest headline timestamp, NOT `now()`** — news is unique among the W3.x source-wrapped tools because the freshness of a news bucket is meaningfully different from when the tool ran. A 5-day-old news bucket cited tomorrow should still be visibly 5 days stale in its footnote, so each tool computes `asof` from the latest item it actually returned: `finnhub_news` does `max(n.date for n in items)` over the `NewsData` list; `get_news_sentiment` parses AV's `time_published` (`YYYYMMDDTHHMMSS`) across `data["feed"]` and picks the maximum, skipping malformed / empty entries rather than throwing.
- **No footnote on empty / failed paths** — `finnhub_news` returns "No recent news found" without a footnote when the provider chain returned an empty list, and "Failed to fetch news" without a footnote when `DataManager.get_company_news` raised. `get_news_sentiment` returns "No news sentiment data available" without a footnote when `feed` is empty. This prevents the W1.10 consistency_gate from accepting a thesis citation that points to a "source" we never actually fetched from.
- **Provider attribution after fallback** — `NewsData.source` is the per-headline publisher ("Reuters", "Bloomberg") not the API provider; the footnote attribution defaults to the tool's primary provider (`finnhub_news → finnhub`, `get_news_sentiment → alphavantage`). Finer post-fallback attribution (e.g., yfinance label when the Finnhub primary in `DataManager._fetch_company_news` falls through to yfinance) is a follow-up — not blocking thesis citation since the footnote ID alone is what the prompt requires.
- **`_news_source_id(provider, symbol, asof)` helper** lives in `tools/finnhub/news.py` next to its primary user, with the same `{PREFIX}-N-{SYMBOL}-{YYYY-MM-DD}` shape as the W3.3 fundamentals helper. Provider prefixes match W3.3: `finnhub→FH`, `alphavantage→AV`, `yfinance→YF`; unknown providers fall back to upper-cased source name. `_av_news_latest_asof(data)` lives in `tools/alpha_vantage/news.py` and is exported for direct unit testing.
- **11 unit tests** in `tests/test_news_tool_source_wrap.py` cover the helpers (3 prefix variants, latest-headline pick, malformed-entry skip, empty-feed → None) plus each tool through `tool.ainvoke()` with stubbed `DataManager` / AV service: footnote emission with truthful asof, no footnote when items / feed empty, no footnote on provider failure for `finnhub_news`. Wave-3 source-wrap suite (`test_news_tool_source_wrap` + `test_quote_tool_source_wrap` + `test_fundamentals_source_wrap` + `test_fundamentals_fallback` + `test_source`) is 57/57 green.

Bumps backend 0.27.12 → 0.27.13.

## [0.27.12] - 2026-05-09

### Added — Wave 3 (W3.3 fundamentals-tool Source-wrap)

- **W3.3 fundamentals tools each emit a Source-style footnote** — every successful return from `get_company_overview`, `get_financial_statements` (cash_flow + balance_sheet branches), `get_company_earnings`, and `get_insider_activity` now ends with a single line in the same shape the W3.2 quote tool uses: `Source: alphavantage [AV-OV-AAPL-2025-09-30] asof 2025-09-30T00:00Z`. The bracketed token is the citation handle the W3.6 Phase2 prompt will require thesis bullets to reference. Field codes: `OV` = company_overview, `CF` = cash_flow, `BS` = balance_sheet, `EAR` = earnings, `INS` = insider. The wrapper knows which provider it actually used (AV happy path vs. yfinance fallback) without re-parsing the markdown body, so the source label is truthful even when the AV branch threw and W1.4 `_yf_fallback.py` rescued.
- **Truthful asof per data type** — instead of stamping `now()` for every fundamentals fact, each tool extracts the per-source timestamp the upstream actually returned: `OVERVIEW.LatestQuarter` (overview), `quarterlyReports[0].fiscalDateEnding` / `annualReports[0].fiscalDateEnding` (statements, picked according to the caller's `period` arg), `quarterlyEarnings[0].reportedDate` with `fiscalDateEnding` fallback (earnings), `data[0].transaction_date` (insider). When that field is missing or malformed, the helpers fall back to `now(UTC)` so a single rotten cell doesn't kill the footnote line. yfinance fallback path uses `now(UTC)` because the helpers don't surface a structured asof — the existing `_yf_fallback.SOURCE_BANNER` already prints a date in the markdown body for the reader's benefit.
- **No formatter or `_yf_fallback.py` changes** — the source line is appended at the tool-wrapper layer, not inside `services/formatters/fundamentals.py`. This keeps the Wave-1 W1.10 consistency_gate's pattern matching on the existing markdown body untouched, and the formatter remains a single-purpose markdown renderer with no provenance concerns.
- **14 new unit tests** in `tests/test_fundamentals_source_wrap.py` cover the helpers (`_parse_av_date`, `_statement_asof`, `_fundamentals_source_id`) directly and exercise each tool through `tool.ainvoke()` with stubbed AV service + formatter and `patch()`-ed yfinance fallback. Each tool gets both an AV-happy-path test (truthful asof from upstream field) and a yfinance-fallback-path test (yfinance label even though AV was attempted first).
- **W1.5–W1.8 regression tests adapted** — 7 tests in `tests/test_fundamentals_fallback.py` that asserted exact-string equality on the tool return (e.g., `assert result == "YF banner overview"`) now use `result.startswith(...)` plus an explicit assertion that the new `Source: ... [...]` footnote also appears. The semantic check (which provider was called, which mock was invoked) is unchanged. The `unavailable_message` paths intentionally do NOT get the source footnote appended — Wave-1's consistency_gate pattern-matches that string exactly to refuse downstream valuation claims, so we leave it alone.

Bumps backend 0.27.11 → 0.27.12.

## [0.27.11] - 2026-05-09

### Added — Wave 3 (W3.2 quote-tool Source-wrap)

- **W3.2 quote tool emits a stable provenance footnote** — the AlphaVantage `get_stock_quote` tool used by the Phase1 ReAct agent now appends a single line at the bottom of the markdown it returns: `Source: yfinance [YF-Q-AAPL-2026-05-09] asof 2026-05-09T18:35Z`. The bracketed token is what the W3.6 Phase2 prompt will require thesis bullets to cite, and what the W3.7 frontend ReportRenderer will resolve into a footnote chip. Footnote ID format is `{PREFIX}-Q-{SYMBOL}-{YYYY-MM-DD}` with the prefix taken from a small registered table (`finnhub→FH`, `yfinance→YF`, `alphavantage→AV`); a yet-to-be-registered provider falls back to upper-cased source name so we never crash. The `asof` is rendered minute-precision UTC so the consistency_gate can parse staleness back out of the markdown if it ever needs to. Legacy cached `QuoteData` rows (written before this change) carry `source=None` / `asof=None` and the tool silently omits the footnote line for them rather than rendering `Source: None [...]`.
- **`QuoteData.source` + `QuoteData.asof` fields** — `services/data_manager/types.py` extends the dataclass with two optional fields. `to_dict()`/`from_dict()` round-trip the new fields through redis cache and from-cache reconstruction. The Wave-1 staleness gate already lives at the `flows.py:Phase1→Phase2` boundary, so providing `asof` here makes a future "reject if quote >24h" check cheap. Each provider stamps its own value: Finnhub uses `body.t` (epoch seconds from the upstream API), yfinance + AlphaVantage use `datetime.now(UTC)` since neither endpoint returns a server-side timestamp finer than a trading-day string.
- **9 unit tests** in `tests/test_quote_tool_source_wrap.py`: 5 cover `_quote_source_id` (yfinance / finnhub / alphavantage prefixes, unknown-provider fallback, missing-source-and-asof legacy path), 4 cover the tool itself end-to-end via `tool.ainvoke()` with a stubbed `DataManager` (yfinance / finnhub / alphavantage emit footnote, legacy-row path emits *no* footnote and no malformed `Source: None` line). Full regression sweep across `test_market_data_quotes.py` + `test_data_manager.py` + `test_data_manager_types.py` (114 existing tests) green — adding the new fields is back-compatible.

Bumps backend 0.27.10 → 0.27.11.

## [0.27.10] - 2026-05-09

### Added — Stock Agent Upgrade Wave 3 starts (PRD docs/prd/STOCK_AGENT_UPGRADE_PRD.md)

- **W3.1 `Source` provenance model** — new `models/source.py` adds the envelope every Wave-3 tool wrapper will use to attribute the numbers and strings it returns. `Source = {value: Any, source: str, asof: datetime, url: str | None, id: str | None}`; `value` is intentionally polymorphic so quote prices stay floats, fundamentals tables stay strings, and news / Form-4 records can pack the whole record in. `source` is normalized to lower-snake-case at construction time so the consistency_gate can match it as an exact string ("alphavantage" / "yfinance" / "sec_edgar_form4"). `url` is validated as `http(s)://` only — empty strings normalize to `None` so the frontend can't render a broken footnote. `asof` is the timestamp of the underlying datum (not when the tool ran) so the Wave-1 staleness gate has a useful comparison anchor. `short_label()` is the helper the W3.7 ReportRenderer will pull for footnote chips, falling back to `source` when `id` is unset. 12 unit tests cover float/string/dict values, source-name normalization (whitespace, capitalisation, empty rejection), URL scheme validation, blank-URL → None coercion, optional `id` + label fallback, and `model_dump(mode="json")` round-trip (Phase2's persistence path uses json mode, so `asof` must serialize cleanly without losing tz info — covered by `test_model_dump_json_mode_roundtrips`).

## [0.27.9] - 2026-05-08

### Changed

- **W2.2 reroute (closes deferred Wave-2 follow-up + bug #5)** — `POST /api/watchlist/analyze?symbol=X` now invokes the W2.1 unified `flows.run_single_symbol` flow (Phase1 ReAct + Phase2 structured-decision + consistency_gate + risk_calc) and persists a row to `portfolio_orders` with `recommendation_source="single_symbol"`, instead of the legacy `WatchlistAnalyzer.analyze_symbol` path. After persistence the endpoint stamps `watchlist_items.last_analyzed_at` so the WatchlistPanel still advances. The all-symbols batch path (no `symbol` param) keeps the legacy code for now because the dormant 5-minute cron — `WatchlistAnalyzer.start()` exists but is never called from `main.py` — could in theory be reawakened, and the bulk sweep hasn't been ported. The per-row "Analyze Now" button no longer hits the legacy code at all. Side effect: this also kills bug #5 (legacy `analysis.py:259` parsed free-text `DECISION:` lines with `[0]` indexing — IndexError → return False; the new path uses Pydantic-structured output and can't fail that way). Verified via real-LLM e2e on 2026-05-08T16:49Z: clicking "Analyze Now" on the CRWV watchlist row writes a `single_symbol` row tagged with thesis=Y, valuation_n=2, scenarios populated.
- **e2e harness `e2e_w2_full_flow.py`** updated: step 3 expects a fresh `single_symbol` row in `portfolio_orders`, and the research-block fill counter now reads `r["metadata"][k]` instead of `r[k]` (W2.7+ blocks live under `metadata`, not the top level — earlier fill-rate readouts of all-zeros were a counting bug, not a data-population bug).

## [0.27.8] - 2026-05-08

### Fixed

- **W2 structured research blocks now actually populate (bug #1)** — Wave-2 schema (thesis / valuation / scenarios / catalysts / risks / derivations) had been defined, validated, surfaced into mongo, rendered by `ResearchPanel.tsx`, and locked down by 21 unit tests in `test_decision_research_blocks.py`, but **76/76 production decisions had every field = null**. Two layered bugs:
  1. `phase2_decisions.py` framed the blocks as **"optional for back-compat with older runs"** and warned that validators would reject malformed payloads. The combination strongly disincentivized the LLM from populating them — emitting `null` was always safe, populating risked rejection. Rewrote that section: blocks are now REQUIRED for BUY/SELL, RECOMMENDED for HOLD, with a worked example showing all six blocks populated for a BUY decision so the LLM has a concrete schema target. Added explicit escape hatch ("downgrade to HOLD if Phase 1 lacks the inputs") so the LLM can't claim "optional fields" as a get-out-of-jail card.
  2. `flows.py:_phase2_for_symbols` (the dashboard-button two-flow path used by holdings + picks) built its persistence dict from only 5 fields (symbol/decision/position_size_percent/confidence/reasoning_summary). Even if the LLM populated thesis/valuation/scenarios/catalysts/risks/derivations/intent/entry/stop/take, this fallback dropped them all on the floor before `_persist_decisions` could write them. Closed the leak by mirroring the full set of fields that the Phase 1→2 path's `_trading_decisions_to_dicts` already passes through.

  Verified end-to-end with a real LLM holdings run on 2026-05-08T16:22Z: 6 holdings analyzed → 2 SELL decisions (MU, CRWV) both ship `thesis_n=3`, `valuation_n=2`, `scenarios={bull,base,bear}` with `prob_sum=1.0`, `catalysts_n=2`, `risks_n=3`, `entry_derivation` + `stop_derivation` populated. The 4 HOLDs leave the blocks empty, which is the prompt's allowed behavior for HOLD.
- **Phase2 prompt f-string regression guard** — embedding a JSON worked-example inside the `f"""..."""` decision_prompt template surfaced an obvious-in-hindsight class of bug: every `{` and `}` in the example needed to be doubled to `{{` `}}` or Python's f-string formatter raised `ValueError: Invalid format specifier ...` at request time, killing the whole flow. First holdings run after the prompt rewrite caught it. Doubled all braces in the worked example and added `test_prompt_actually_builds_without_format_error` to `test_phase2_required_research_blocks.py` — it builds the real prompt against an `AsyncMock`-wrapped LLM stub and only succeeds if the f-string evaluation doesn't raise. Two regressions impossible to ship together going forward: (1) prompt source must say `REQUIRED for BUY/SELL` and not `optional for back-compat`, (2) prompt must f-string-build without raising.

## [0.27.7] - 2026-05-08

### Fixed

- **Watchlist analyze catch-all now logs full traceback (bug #2)** — `services/watchlist/analysis.py::AnalysisEngine.analyze_symbol`'s outer `except Exception` previously logged only `error=str(e)` and `error_type=type(e).__name__`, so production failures were undebuggable: no file:line, no exception chain. Switched to structlog with `exc_info=True` while keeping the existing structured fields (symbol, error, error_type) and `return False` behaviour, so the failure signal callers see is unchanged but the log line now carries the full Python traceback. No other behaviour change in this PR — the catch-all body and `return False` are preserved; the legacy synchronous route still answers in-line and the 5-min cron path is untouched. The async rewire is W2.2's job.

## [0.27.6] - 2026-05-08

### Fixed

- **reasoning_summary 500→1000 chars** — 2026-05-08 04:42 UTC holdings run produced 0 persisted decisions despite Phase2 succeeding. Root cause: W2.6/W2.10 enriched the Phase2 prompt (risk block + 5 schema blocks), so the LLM's per-decision `reasoning_summary` started running ~530 chars on detailed SELL legs. Pydantic `max_length=500` raised on `decisions.3.reasoning_summary`, and because the validator runs over the whole `PortfolioDecisionList`, **all 4 holdings were dropped**, not just the offending one. Bumped the cap to 1000 in `models/trading_decision.py`; matched the truncation slice in `flows.py` (translation prefetch + PortfolioOrder.metadata.reasoning) so we don't quietly truncate again downstream. 31 model regression tests still green.
- **Pre-market price now flows end-to-end** — Refresh Prices button was returning regular-session quotes during US pre-market (04:00–09:30 ET). Multiple stacked bugs: (1) `holdings.py:_refresh_one` dropped the `session` param when calling `update_price`; (2) `_extended_hours_price` helper in `data_manager/manager.py` rejected yfinance's zero-volume but priced bars typical during thin pre-market — loosened to accept bars where Close differs from previous_close; (3) Finnhub `/quote` hardcodes `session="regular"` and was the primary provider — reordered `_fetch_quote` so yfinance is preferred when `get_market_session(now_utc) in {"pre","post"}`; (4) 5-min Redis quote cache made the refresh button a no-op against fresh data — added `DataManager.invalidate_quote(symbol)` and call it in both the refresh endpoint and watchlist `analysis.py` before each prompt build. Verified by `e2e_refresh_premarket.py` (real Playwright, no mocks) — at least one holding now persists `last_session="pre"` and a SessionBadge[data-session="pre"] renders in the DOM.
- **Pre-market labels reach the LLM** — even with correct prices, the Phase2 prompt was rendering positions as "PRICE: 250.31" with no session context, so the LLM happily anchored stop_loss on extended-hours bar lows. Added a Session column to the positions table in `phase2_decisions.py`, propagated `last_session` from `Holding` → `context_builder` → positions dict, and surfaced `Session: pre (extended-hours; volume thin, treat as indicative)` in both Finnhub and Alpha Vantage `quote` tool outputs so single-symbol/watchlist agents get the same warning. `flows.py` also stores `decision_session` into `PortfolioOrder.metadata` for ex-post traceability.
- **Stuck holdings analysis (status: pending forever)** — `/api/admin/portfolio/trigger-analysis?flow=holdings` would create an `analysis_runs` doc and never advance past `pending`. Root cause: `models/trading_decision.py:619` referenced `Any` (added with the W2 `consistency_violations` field) without `Any` being in the typing import. The `NameError` killed `SymbolAnalysisResult` definition at import time → `PortfolioAnalysisAgent` failed to instantiate at backend startup → `app.state.portfolio_agent = None` → the holdings `BackgroundTask` raised `AttributeError` and FastAPI silently swallowed it. Added `Any` to `from typing import Any, Literal`. Backend log now shows `PortfolioAnalysisAgent initialized for dashboard flows`, and a re-triggered run advances pending → running within ~2s.

## [0.27.5] - 2026-05-08

### Added — Stock Agent Upgrade Wave 2 (PRD docs/prd/STOCK_AGENT_UPGRADE_PRD.md)

11 sub-tasks shipped (W2.1, W2.3, W2.5–W2.12); 3 deferred with rationale (W2.2, W2.4, W2.13–14 close).

- **W2.5 risk_calculator** — pure async function `compute_portfolio_risk()` produces sector_exposure / beta_weighted / cash_pct / HHI / 60d correlation / annualised σ. DI for meta + returns fetchers; 16 unit tests, all hand-computed math within 1e-6 tolerance.
- **W2.6 wire risk into Phase2 prompt** — _fetch_symbol_meta_for_risk + _fetch_symbol_returns_for_risk wrap yfinance.Ticker.info / .history; render_risk_block_for_prompt injects "## Portfolio Risk" before symbol research. Also rewrote SELL geometry semantics in the same prompt to match the W1.1 validator (long-side stop_loss < entry < take_profit) — without this, every SELL out of Phase2 would have raised ValidationError.
- **W2.7 + W2.8 schema extension** — TradingDecision gains 5 optional structured-research blocks: thesis (3 bullets), valuation (≥2 ValuationMethods), price_target (PriceTarget), scenarios (bull/base/bear ScenarioSet, prob sum 1.0±0.02), catalysts (list[Catalyst]), risks (3 ranked). All optional → back-compat with old payloads. 21 unit tests pin the contract.
- **W2.9 numeric derivation** — new `models/derivations.py` with `Derivation {value, formula, inputs}` + `atr_stop()` and `vol_adjusted_size()` helpers. TradingDecision gains entry/stop/target/size_derivation. Cross-validator: derivation.value must match its corresponding price within 0.5%. 16 unit tests.
- **W2.10 prompt teaches new schema + derivation rules** — Phase2 prompt now describes every new field, requires each `scenarios.*.probability` rationale to cite a base rate or historical frequency, and tells the LLM to attach Derivation to concrete numbers (or use a qualitative band instead). Also moved derivations.py from `agent/portfolio/` to `models/` to break a circular import.
- **W2.1 single-symbol unified flow** — `flows.run_single_symbol(app, symbol)` runs Phase1+Phase2 (degenerate single-symbol mode) + consistency_gate + risk_block + persists with `recommendation_source="single_symbol"`. New `/api/admin/portfolio/trigger-analysis?flow=single_symbol&symbol=X` endpoint; AnalysisRun.run_id widened from Literal to str so per-symbol run keys (`single_AAPL`) work. End-to-end HTTP 200 verified.
- **W2.3 Phase1 prompt language switch** — `PHASE1_PROMPT_LANG=en` env (default zh) flips the LANGUAGE REQUIREMENT directive to English. 5 unit tests on `_phase1_language_directive()` cover both modes + fallback. W2.4 A/B is a manual ops follow-up: user runs the env override for 1-2 days and compares Phase2 scenarios + PT vs zh baseline before flipping default.
- **W2.11 persist + render structured blocks** — `_trading_decisions_to_dicts` pulls every W2.7+ field via Pydantic model_dump; `_persist_decisions` writes them under PortfolioOrder.metadata + intent at the top. Frontend `ResearchPanel.tsx` renders each present block (thesis/valuation/scenarios with prob-warning/catalysts/risks) plus derivation chips with hover-tooltip `formula(inputs) = value`. e2e on FULL/BAD_PROB/BARE rows: PASS.
- **W2.12 risk_calculator integration test** — 4-position portfolio fixture with mocked yfinance fetchers covers the full async path including correlation matrix + portfolio σ + render_risk_block_for_prompt. 2 tests, all green.

### Deferred (tracked in PROGRESS.md)

- **W2.2** legacy `WatchlistAnalyzer.analyze_symbol → 410` — current 5-minute cron still uses it; new flow lives at `/trigger-analysis?flow=single_symbol`. Cron switches over before legacy removal.
- **W2.4** A/B 5 historical runs zh vs en — manual ops, not CI-automatable. User runs `PHASE1_PROMPT_LANG=en` for 1-2 days and flips default after parity confirmed.

Test counts: Wave 2 added ~70 unit + 5 e2e + 1 integration; full Wave 1 + Wave 2 regression suite green.

## [0.27.4] - 2026-05-08

### Added — Stock Agent Upgrade Wave 1 (PRD docs/prd/STOCK_AGENT_UPGRADE_PRD.md)

13 sub-tasks delivered (W1.1 – W1.13) addressing the two highest-severity findings from the 2026-05-07 PM/quant + sell-side analyst review:

- **W1.1 OrderIntent enum + geometry validator** (`models/trading_decision.py`) — TradingDecision now requires direction-aware intent. `close_long` mandates `stop_loss < entry < take_profit`; `open_short` mandates the reverse. The CRWV-style payload that shipped 2026-05-07 (entry=$138 stop=$142 target=$122) now raises ValidationError before reaching mongo. 11 unit tests + 4 integration tests (W1.13).
- **W1.2 Mongo migration** (`scripts/migrate_order_intent.py`) — backfilled `intent` on 60/60 historical PortfolioOrder docs (37 hold / 8 open_long / 15 close_long), flagged 8 with `legacy_short_geometry`. Idempotent dry-run + `--apply`.
- **W1.3 IntentBadge UI + W1-E1 e2e** — DecisionTracker shows 平多/做空/⚠几何 chips next to SideBadge.
- **W1.4 yfinance fallback helper** (`agent/tools/_yf_fallback.py`) — 5 async helpers wrapping `yfinance.Ticker.info / cashflow / balance_sheet / earnings_dates / insider_transactions`. Output carries explicit source banner ("⚠️ Data source: yfinance"). 7 integration tests against live yfinance.
- **W1.5–W1.8 fundamentals tools wired to fallback** (`agent/tools/alpha_vantage/fundamentals.py`) — 4 `@tool` wrappers (`get_company_overview` / `get_financial_statements` / `get_company_earnings` / `get_insider_activity`) now retry via yfinance when AV returns empty or raises, return `unavailable_message` when both fail. Direct fix for the 4/4 holdings analysis blackout from 2026-05-07. 11 mock unit tests.
- **W1.9 Fibonacci sanity gate** (`agent/langgraph_react_agent.py`) — fibonacci tool computes `range_position` (above_range / in_range / below_range); when breakout >5% emits `STALE FIB SWING` warning. Phase1 prompt rule forbids citing stale levels as support/resistance. 5 unit tests including the AAPL reviewer scenario.
- **W1.10 Consistency LLM gate** (`agent/portfolio/consistency_gate.py`) — between Phase1 and Phase2, runs cheap LLM (haiku) only when degraded fields detected by regex. Returns `{passed, violations}`; results annotated on Phase1 attributes. Cost ≤$0.05/run per PRD D1. Fail-open. 11 unit tests.
- **W1.11 Disclaimer + UI watermark** — Phase2 message footer + global App.tsx footer add "🤖 AI-generated · Not investment advice". W1-E2 e2e PASS on Portfolio + Chat tabs.
- **W1.12 data_quality UI tag** — `_build_data_quality_map()` translates consistency-gate annotations to PortfolioOrder.metadata.data_quality. DecisionTracker renders 📉 数据降级 chip with hover tooltip listing degraded fields. W1-E3 e2e PASS.

Frontend bumped to 0.22.4 (W1.3 + W1.11 + W1.12 visual changes).

Wave 2 (architectural upgrades) and Wave 3 (provenance + insider depth) remain gated on user signoff per PRD; tracked in `docs/prd/STOCK_AGENT_UPGRADE_PROGRESS.md`.

## [0.27.3] - 2026-05-07

### Fixed
- **fix(watchlist): 间歇性"有些有价有些没有" — 超时调到 10s + quote snapshot 持久化** — 之前 `_enrich_with_live_quote` 每次 GET 实时拉每个 symbol 的 quote，6s 超时，单 symbol 失败就 swallow + log warning，那行 `current_price` 留空，前端 `item.current_price != null` 判定失败 → 该行不渲染价。开盘前后 yfinance 拥堵，6s 不够，log 实测 13:44–14:10 ET 共 27 次 `watchlist_quote_enrichment_failed error_type=TimeoutError`，每次不同 subset 中招（INTC/TSLA/MSFT/GOOGL/SNDK/BE/CRWV 都中过）。
  - **A. 超时 6s → 10s**（`backend/src/api/watchlist.py:28`）。多数 timeout 立刻消失；cache hit 仍 ~5ms。
  - **B. quote snapshot 持久化**：`WatchlistItem` 的 `current_price` / `last_price_update` / `last_session` / `day_change_percent` 4 个字段从 transient 改为持久化字段（`backend/src/models/watchlist.py:42-67`），enrich 成功后写回 mongo（新增 `WatchlistRepository.update_quote_snapshot()`，`backend/src/database/repositories/watchlist_repository.py:109-134`）。下次 endpoint 命中 timeout 时，item 已经从 mongo 带着上次成功的快照返回，前端直接渲染那个值，不再空白。
  - log 增强：fail 路径多输出 `fallback_age_seconds`，让"这个 stale 多老"一眼可见。
  - 配套前端 v0.22.3：价格 > 5 分钟未更新时旁边加灰色 "Xm ago" 指示。

## [0.27.2] - 2026-05-07

### Fixed
- **fix(translation): 持仓分析显示英文 — separator 协议替换 JSON parse + fallback 不再伪装翻译** — Portfolio 分析历史里近两次"持仓分析"chat modal 显示英文（5/7 13:33、5/6 15:34）。根因不是 dashscope 断网，是 `_parse_llm_output` 用 `json.loads` 严格解析 LLM 返回的 JSON 数组，而 LLM 把 markdown 翻译里的真实换行直接写进 JSON string（违反 spec），`json.loads` 抛 `Invalid control character` → parser 返回 None → `translate_batch:175-179` 把英文原文当 "translated" 写进 out → `translate_for_persistence` 把英文原文写进 `Message.content_zh` → 前端 `useTranslated` 拿到非空 precomputed 直接返回 → 用户看到英文。Mongo 实测 13 条文档（2 messages + 11 portfolio_orders.full_research_zh）的 `_zh` 字段字面等于 `content`/`full_research`。
  - **Prompt 协议从 JSON 数组换成 separator-delimited 纯文本**：`_SYSTEM_PROMPT` rule 6 + Example 改为用 `<<<TRANSLATION_SEPARATOR>>>` 分隔多段译文。彻底消除 escape 地狱。
  - **`_parse_llm_output` 重写为 split + strip**：28 行，零 JSON 解析。
  - **`translate_batch` LLM/parse fail 时返回 `None` 元素**（不再回填英文原文）。返回类型从 `list[str]` 改为 `list[str | None]`。
  - **`/api/translate` HTTP route**（`backend/src/api/translate.py`）适配：None 槽 echo 英文原文（不破坏现场翻译契约；持久化路径才需要 None 触发前端兜底）。
  - **`translate_for_persistence` 透传 None**（`out: dict[str, str | None]` 已合法，无需改动）。
  - **`translation_parse_failed` log 增强**：`error_type` + `repr(e)` + raw_preview 上限 2000 字。
  - **新增 `backend/scripts/cleanup_dirty_translations.py`** —— 扫 `messages` / `chats` / `portfolio_orders.metadata` 把 `<field>_zh == <field>` 的脏数据置 null。dry-run 默认，`--apply` 才动数据。本次清掉 13 条；前端 `useTranslated` 拿到 None 后走 `/api/translate` 兜底，新 separator parser 解析中文成功落地（实测 1924 字英文 → 1086 字中文，0.56× ratio 正常）。
  - 新增 28 cases `tests/test_translation_service.py`（separator 解析正/反例 + batch None 传播）+ 6 cases `tests/test_cleanup_dirty_translations.py`（query 形状、dry-run/apply、嵌套 metadata）。
  - **Follow-up（不在本 wave）**：`frontend/src/hooks/usePortfolioChats.ts:70-78` 把 backend chat 转前端 Chat 时丢 `title_zh` / `last_message_preview_zh`，preview 用 `.content` 而不是 `.content_zh`，导致 sidebar 反而靠"丢字段 + 现场 translate"绕过脏数据 —— 脆弱。

## [0.27.1] - 2026-05-07

### Fixed
- **fix(quote): 盘前/盘后时段返回真实延伸时段价** — `yfinance.fast_info.last_price` 只在 regular session 更新，盘前/盘后期间它一直停在前一日 RTH close 附近，导致 holdings/watchlist 的 `price` 字段在 09:00-09:30 ET 实测显示 287.51（≈昨收 287.40），而真实盘前价已经走到 289.35（+0.65% 被吞掉）。
  - 抽出 `_extended_hours_price(hist, session, fallback)` helper（`backend/src/services/data_manager/manager.py`），先过滤 `Volume > 0` 行，pre/post session 时返回 1m prepost bar 的最后 Close，否则回退到 `fast_info.last_price`
  - 重排 `_fetch_quote_yfinance`：先取 1m prepost hist + derive session，再让 helper 决定 price，最后算 change/change_percent（`previous_close` 仍锚定 RTH close，change% 才有意义）
  - 同样的 helper 接到 `_yf_quote_sync`（`backend/src/services/market_data/quotes.py`），fallback 路径行为保持一致
  - **修一个连带 bug**：`_yf_quote_sync` 原来取 `prev_close = hist["Close"].iloc[-2]`，但 `period="2d", prepost=True` 下 hist[-2] 本身就是另一根 prepost bar（不是昨日 RTH close）。改成优先 `info["regularMarketPreviousClose"] / previousClose`，`hist[-2]` 仅作两都缺时的兜底，避免盘前期 change% 用错基准
  - 边界处理：hist 为 None / 空 / 全零 volume / yfinance 异常 → 全部回退 `fast_info.last_price`，不抛
  - 新增 `tests/test_extended_hours_price.py`（19 cases），覆盖 helper 的 pre/regular/post/closed/None/空/全零、两条报价路径的 4 种 session、yfinance 异常回退、prev_close 不被 prepost bar 污染的回归测试

## [0.27.0] - 2026-05-07

### Added
- **feat(holdings/watchlist): 今日涨幅 (day_change_percent)** — 两表都暴露今日 vs 昨收 % 改变。复用 QuoteData.change_percent（三个 provider 都已经返回过来），enrich 阶段写到 transient 字段
  - `Holding.day_change_percent: float | None`（不入 mongo）
  - `WatchlistItem.day_change_percent: float | None`（不入 mongo）
  - `HoldingResponse.day_change_percent` API 透出
  - **GET /api/portfolio/holdings 现在并发 enrich 每行**（persist=False，不 mutate mongo 避免 last_price_update 抖动）。之前只在 POST/PATCH/refresh 时才有 current_price/day%，dashboard 一进去看到的是 mongo 里上次 enrich 时存的"过期价"
  - AV 路径返回 change_percent 是 str ("0.4232")，yfinance/finnhub 是 float — `_enrich_with_quote` 加 coercion fallback

## [0.26.0] - 2026-05-07

### Removed
- **change(portfolio-chart): 删掉 Robinhood 风格的 portfolio value 时间序列图表** — Alpaca 移除后没办法算真实历史净值。v0.25.1 用"当前持仓 × 历史价"回放出来一条线，但今天才买的股票被当作 1 年前就持有，昨天卖掉的根本不出现，这条线长得漂亮但**信息错的**，比空着还误导。
  - 删 `backend/src/api/portfolio/history.py`、移除 router 注册
  - 删 `PortfolioHistoryDataPoint` / `AnalysisMarker` / `OrderMarker` / `PortfolioHistoryResponse` schema 类
  - holdings 表自己有 current_value、P/L、market_value，决策走 DecisionTracker，时间序列回放等真做 portfolio_snapshots 表 + SPY 基准时再加

## [0.25.2] - 2026-05-06

### Fixed
- **fix(watchlist-time): added_at / last_analyzed_at 带 UTC 后缀** — Mongo Motor 反序列化 BSON UTC 成 naive datetime，Pydantic 输出无 `Z` 的 ISO，前端 `new Date(iso)` 当本地时间解析 → "上次分析" 显示偏 8 小时。`_enrich_with_live_quote` 顺手把这俩字段补上 `tzinfo=UTC`。同 v0.23.0 holdings 的修法。
- **fix(watchlist-prices): quote 超时从 3s 调到 6s** — 9 路并发但首次 cold-cache yfinance 往返常超过 3s（实测 9 行有 7 行 timeout）。改 6s 后 9 行 enrich 8 行成功（MU 之前看不到价现在 $660.74）。redis cache hit 还是 ~5ms，调高 timeout 不影响热路径

## [0.25.1] - 2026-05-06

### Fixed
- **fix(portfolio-chart): 图表恢复显示** — `/api/portfolio/history` 之前 W5a Alpaca 移除后**有意返回空 data_points**，前端图表区一直白板。现在用本地 holdings × yfinance OHLCV 回放出 portfolio value 时间序列：
  - 1D → 5min bars (今日)
  - 1M → daily bars (~30 天)
  - 1Y → daily bars (~12 月)
  - All → weekly bars (~5 年)
  - 多 symbol 并发拉（最多 8）+ outer-join 时间索引 + ffill 防 halt 抖动
  - 单 symbol 拉失败只 warning 不阻断
  - **简化假设**：用当前持仓数量回算历史，忽略仓位变更（今天才买的 NVDA 在 1Y 视图里被当成全年都持有）。本地工具够用；要精确得 replay user_transactions

## [0.25.0] - 2026-05-06

### Added
- **feat(watchlist): GET /api/watchlist 现在并发拉实时报价 enrich 每行** — `WatchlistItem` model 加 transient 字段 `current_price` / `last_price_update` / `last_session`（**不**写 mongo，纯 response-only）。GET 时通过 DataManager 并发拉 quote（最多 8 路并发，每个 quote 3s 超时），失败行静默跳过保留无 price 状态。借力 DataManager 自带的 redis 30s quote cache，重复 GET 不会真的撞到上游
- **feat(watchlist): POST /api/watchlist/analyze?symbol=BE 单股分析分支** — 没传 symbol 时还是批量（force=True，跳已持仓），传 symbol 时调 `analyze_symbol(sym)` 直接跑那一只。rate limit 从 2/min 抬到 10/min（per-row 按钮场景需要）。symbol 校验 `[A-Z0-9.]{1,10}` 防注入

### Notes
- watchlist 字段是 transient 的（model 默认 None，mongo 里没列）—— 不破老数据，不需要 migration
- DataManager.get_quote 有 redis 30s cache，watchlist 9 行的话首次 GET ~9 个 quote 调用、之后 30s 内重复 GET 几乎全 cache HIT

## [0.24.2] - 2026-05-06

### Changed
- **change(watchlist-analysis): "立即分析"自动跳过已经在 holdings 里的 symbol** — `WatchlistAnalyzer.run_analysis_cycle` (force=True 路径) 在拿到 watchlist items 后，先 query mongo `holdings` collection 把已持仓的 symbol 集中起来，从待分析列表里 filter 掉。这些股票走"持仓分析"那条线就行，watchlist 这边再跑一遍是浪费 quote + LLM 调用。Mongo 读用 `watchlist_repo.collection.database["holdings"]`，零新注入点。读失败时只打 warning 不阻断（保守 fallback：宁可分析重也不能跑不出来）

## [0.24.1] - 2026-05-06

### Fixed
- **fix(symbol-search): 热门股 BE / PLTR / HOOD / RIVN / SOFI 等搜不到** — `_search_local_universe` 之前只查 `sector_universe.csv`（515 只大盘），命中前缀/名字匹配就直接返回，**不再走 yfinance fallback**。结果用户搜 `BE` 拿到 BEN/BBY/BDX 但永远看不到 Bloom Energy 本身（不在 515 大盘里）。

### Added
- 新增 **`backend/data/tickers_directory.csv`**（6868 只活跃 US ticker）— 来自 Nasdaq Trader 公开发布的 `nasdaqlisted.txt` + `otherlisted.txt`，过滤 Test Issue / ETF / Rights / Warrants / Units。Schema 窄：`symbol,name,exchange`，专门给 search endpoint 用，跟 `sector_universe.csv`（带 sector/market_cap 富数据，picks 流程用）严格分离
- 新增 `backend/scripts/build_tickers_directory.py` 拉取 + 过滤 + 去重，`docker compose exec backend python scripts/build_tickers_directory.py` 重新生成（Nasdaq Trader 每日发布，手动刷新即可）
- 新增 `backend/src/data/tickers_directory.py` loader，`@lru_cache` 单例读

### Changed
- `_search_local_universe` 改成两表 union：sector_universe 优先（保留 sector 富数据），同 symbol 时 directory 表跳过避免重复。Ranking 逻辑不变（exact > prefix > name-prefix > fuzzy）

### Notes
- 没动 sector_universe.csv —— picks/portfolio 决策流程读它的 sector + market_cap 字段，不能污染
- yfinance fallback 仍然保留（v0.17.3 加的），现在主要兜底"非 US 上市"或"超新 IPO 还没进 Nasdaq Trader 列表"的边缘场景

## [0.24.0] - 2026-05-06

### Added
- **feat(quotes): 引入盘前/盘后 (extended-hours) 报价支持** — 之前所有 holding 的 `current_price` 永远是上一根 RTH bar；财报后开盘前那段大幅波动看不到。现在 yfinance 路径用 `prepost=True` 取最新延长时段成交，按 yfinance 的 bar 顺序天然就是 `iloc[-1]` 胜出，匹配 Robinhood/Yahoo 主页行为。
  - `QuoteData` 加 `session: Literal["pre","regular","post","closed"] = "regular"`；`to_dict`/`from_dict` 透传，旧缓存读出来默认 `regular`，零迁移
  - `yfinance_bars.get_bars` 加 `prepost: bool = False` 参数；`yfinance_indicators.compute_indicator` 显式 `prepost=False` 锁意图（指标永远 RTH-only，避免 prepost bar 污染 SMA/EMA 等）
  - `quotes._yf_quote_sync` + `DataManager._fetch_quote_yfinance` 都用 prepost 拿 last bar timestamp，调 `get_market_session(last_ts)` 推 session
  - `Holding` 加 `last_session: str | None`；`HoldingResponse.last_session` 透出；`HoldingRepository.update_price(session=None)` 支持持久化（None 时不动旧值）
  - `_enrich_with_quote` 把 quote.session 写到 `holding.last_session` + `repo.update_price(session=)`；`scripts/refresh_holding_prices.py` cron 同步
  - **Phase 2 portfolio 决策 prompt 在非 regular 时段插「市场时段提示」** —— 警告 LLM 延长时段流动性薄、可能跳空，建议延后下单或调整 entry。warn-not-block，不阻断决策

### Notes
- **Finnhub `/quote` 和 Alpha Vantage `GLOBAL_QUOTE` 都做不到** —— 都是 RTH-only 接口，硬编码 `session="regular"` + docstring 说明限制。**只有 yfinance 路径**能产出 `pre`/`post`/`closed` 标签
- 老 holdings 行没 `last_session` 字段 → 类型 `Optional[str]`，前端 null 时不显示 chip。零数据迁移
- 循环导入用函数级 `from . import get_market_session` 规避（market_data.__init__ 反向 import quotes/manager 链路）
- `current_price` / `market_value` / `unrealized_pl` 全部按"最新成交"算 —— 即使是稀薄的盘后偏离价。"prefer latest"是有意为之

### Tests
- `test_market_session_boundaries.py` — 14 case 覆盖 pre/regular/post/closed 切换 + 周末 + 时区转换
- `test_phase2_session_stanza.py` — source-inspection 验 Phase 2 prompt 注入点 + 三个中文标签 + warn-not-block 约束

## [0.23.0] - 2026-05-06

### Fixed
- **fix(portfolio-schema): `last_price_update` / `created_at` / `updated_at` 在 `HoldingResponse` 里现在带 UTC 时区后缀** — Mongo Motor 把 BSON UTC datetime 反序列化成 naive `datetime`，Pydantic 默认输出 ISO `2026-05-06T03:37:37.780000` 不带 `Z`。前端 `new Date(str)` 把 naive ISO 当本地时间解析（按 ECMA-262），导致 zh-CN UI 显示 UTC 时间而不是北京时间。`portfolio_models.py:from_holding` 现在用 `_as_utc(dt)` 给 naive 字段补上 `tzinfo=UTC`，输出变成 `...+00:00`，前端能正确换算成 Asia/Shanghai。

### Added
- **feat(holdings): PATCH `/holdings/{id}` 现在也走 `_enrich_with_quote(persist=True)`** — 之前只有 POST/refresh-prices 会更新 `last_price_update`，PATCH 改持仓只动 `updated_at`、不刷价，导致"最后更新"显示和实际行情脱钩。现在编辑数量/均价后也会同步抓一次实时价、写回 mongo。

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
