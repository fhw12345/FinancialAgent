# Stock Agent Upgrade — Progress Tracker

**PRD:** [STOCK_AGENT_UPGRADE_PRD.md](./STOCK_AGENT_UPGRADE_PRD.md) (frozen 2026-05-08)
**Started:** 2026-05-08
**Owner:** orchestrator

> Each sub-task = one commit. Mark ✅ when committed. Include commit hash + UTC timestamp.
> If interrupted, resume from the first ⏳ task. Read PRD section + this row to recover context.

---

## Wave 1 — Hard bugs + data fallback

Status: **DONE** (15/15 sub-tasks; awaiting user signoff to start Wave 2)

| ID | Task | Status | Commit | Notes |
|---|---|---|---|---|
| W1.1 | `OrderIntent` enum + Pydantic validator + unit test | ✅ | 41966dd | Reject CRWV-style payload (stop > limit on close_long). 11 tests pass. |
| W1.2 | Migration script `migrate_order_intent.py` dry-run + apply | ✅ | f161bf3 | Backfilled 60/60 docs (37 hold / 8 open_long / 15 close_long), 8 flagged `legacy_short_geometry` |
| W1.3 | Frontend OrderPreview intent badge + W1-E1 e2e | ✅ | 80e7134 | IntentBadge component + DecisionTracker integration + legacy_short_geometry warning chip. Backend PortfolioOrder model + decisions endpoint passthrough intent. e2e PASS: 3 badges + 1 legacy chip rendered correctly. |
| W1.4 | yfinance fallback helper `_yf_fallback.py` | ✅ | 1654f1e | 5 helpers (overview/cash_flow/balance_sheet/earnings/insider) + unavailable_message. All return formatted markdown with visible source banner. 7 integration tests pass against live yfinance. |
| W1.5 | `get_company_overview` connect fallback + unit test | ✅ | 24c229d | 4 paths: AV ok / AV empty → yf / AV raise → yf / both fail → unavailable_message. Unit test 4/4. |
| W1.6 | `get_financial_statements` connect fallback + unit test | ✅ | 24c229d | cash_flow + balance_sheet branches both wired. Unit test 3/3. |
| W1.7 | `get_earnings` connect fallback + unit test | ✅ | 24c229d | Unit test 2/2. |
| W1.8 | `get_insider_activity` connect fallback + unit test | ✅ | 24c229d | Unit test 2/2. (Form 4 plan_type detection deferred to W3.8/W3.9.) |
| W1.9 | Fibonacci tool `current_price_position` + Phase1 prompt rule + unit test | ✅ | 1b10f4d | range_position field {above_range/in_range/below_range} + STALE FIB SWING warning when breakout >5%. Phase1 prompt: "DO NOT cite stale levels" + parallel rule for unsubstantiated fundamental data. 5 unit tests pass. |
| W1.10 | Consistency checker LLM gate + unit test | ✅ | d99ba20 | consistency_gate.py: regex detects degraded fields → cheap LLM (haiku) checks if thesis cites them → returns {passed, violations}. Wired into flows.py Phase1→Phase2 boundary for both holdings + picks. Cost: 1 call/symbol when degraded fields present, 0 when clean. Fail-open. 11 unit tests. |
| W1.11 | Global disclaimer footer + UI watermark + W1-E2 e2e | ✅ | 1f66ac7 | Phase2 message footer adds AI-generated disclaimer + global App.tsx footer renders persistent watermark. e2e PASS on Portfolio + Chat tabs. |
| W1.12 | `data_quality=degraded` UI tag + W1-E3 e2e | ✅ | ff420e7 | _build_data_quality_map translates consistency_gate annotations to PortfolioOrder.metadata.data_quality. DecisionTracker renders gray "📉 数据降级" chip with hover tooltip listing degraded fields. e2e PASS: 1 chip on degraded row, 0 on clean row. |
| W1.13 | Integration test `test_intent_real_phase2.py` | ✅ | eec7fad | 4 cases: CRWV invalid raises ValidationError; clean close_long passes; mixed batch rejects all; open_short escape-hatch works. Confirms validator stops bad payload before persistence. |
| W1.14 | Cleanup test data | ✅ | (final) | 0 untracked files; mongo has 0 TST* fixtures (e2e all use page.route mocks, never write mongo). |
| W1.15 | Bump version + CHANGELOG + final commit | ✅ | (final) | backend 0.27.3 → 0.27.4; frontend 0.22.3 → 0.22.4; both CHANGELOGs updated. |

### Wave 1 Acceptance Criteria checklist

- [ ] AC1: CRWV historical payload raises `ValidationError`
- [ ] AC2: migration dry-run zero `unknown`
- [ ] AC3: AV invalid → yfinance fallback populates P/E + market cap
- [ ] AC4: Both invalid → `unavailable: true`, gate flags violation
- [ ] AC5: Fibonacci 9% above → `above_range`
- [ ] AC6: UI smoke disclaimer + intent badge

### Wave 1 e2e

- [ ] W1-E1 OrderPreview intent badge + invalid payload error
- [ ] W1-E2 Disclaimer on 4 routes
- [ ] W1-E3 data_quality=degraded tag + tooltip

### Wave 1 Integration test

- [ ] W1-IT `test_intent_real_phase2.py` passing

---

## Wave 2 — Architectural upgrades

Status: **DONE** (12/14 sub-tasks shipped + W2.2 closed in 0.27.9; W2.4 deferred with rationale; Wave 3 in progress)

| ID | Task | Status | Commit |
|---|---|---|---|
| W2.1 | Single-symbol flow `run_single_symbol` | ✅ | bb2bab5 | flows.py adds run_single_symbol that runs Phase1 (one ReAct) + Phase2 (degenerate single-symbol) + consistency_gate + risk_calc + persists to portfolio_orders source=single_symbol. portfolio_admin.py /trigger-analysis accepts flow=single_symbol&symbol=X. AnalysisRun.run_id widened to plain str (was Literal). E2E HTTP 200 with run_id=single_AAPL. |
| W2.2 | Reroute /api/watchlist/analyze to W2.1 `run_single_symbol` | ✅ | c8a6553 | UI per-row "Analyze Now" now persists structured PortfolioOrder via run_single_symbol with recommendation_source=single_symbol; DecisionTracker picks it up. Stamps watchlist_items.last_analyzed_at on success. Legacy `WatchlistAnalyzer.analyze_symbol` (free-text DECISION:/POSITION_SIZE: parse — bug #5) is no longer reachable from UI; all-symbols batch path retained for cron compat. 6 unit tests + e2e on CRWV PASS. |
| W2.3 | Translate Phase1 prompts to English | ✅ | ab64c2e | _phase1_language_directive() reads PHASE1_PROMPT_LANG env (defaults zh for back-compat). Setting `=en` switches output to English. 5 unit tests verify both modes + fallback. |
| W2.4 | A/B 5 historical runs old vs new prompt | ⚠️ deferred | - | Defaults to zh in production; user runs `PHASE1_PROMPT_LANG=en docker compose up -d` for 1-2 days, compares Phase2 scenarios + PT vs the zh baseline, then flips default. **Tracked as Wave-2 follow-up; not blocking.** |
| W2.5 | `risk_calculator.py` + unit test | ✅ | 66b6601 | Pure async function. Computes sector_exposure / beta_weighted / cash_pct / HHI / 60d corr matrix / portfolio σ. DI for meta + returns fetchers. 16 unit tests cover hand-computed math + missing data fallbacks + renderer. |
| W2.6 | Wire risk_calculator into Phase2 prompt | ✅ | 88eb11d | _fetch_symbol_meta_for_risk + _fetch_symbol_returns_for_risk wrap yfinance.info / .history. compute_portfolio_risk runs before LLM call; render_risk_block_for_prompt injected as ## Portfolio Risk section in decision_prompt. Fail-soft: empty block on any error. **Also fixed**: rewrote SELL geometry semantics in prompt to match W1.1 validator (long-side stop_loss < entry < take_profit), eliminating the every-SELL-now-rejects breakage. |
| W2.7 | `PortfolioDecision` schema extension | ✅ | 547d3a0 | 5 optional sub-models on TradingDecision: thesis (3 bullets), valuation (≥2 ValuationMethods), price_target (PriceTarget), scenarios (bull/base/bear ScenarioSet), catalysts (list[Catalyst]), risks (3 ranked). All optional → back-compat with old payloads. |
| W2.8 | Pydantic validators (lengths + prob sum) + test | ✅ | 547d3a0 | _validate_research_blocks enforces thesis len==3 / valuation len>=2 / risks len==3. ScenarioSet._probabilities_sum_to_one enforces 1.0±0.02. 21 unit tests in test_decision_research_blocks.py. |
| W2.9 | Numeric derivation `{value, formula, inputs}` + helpers | ✅ | 6ae0093 | derivations.py: Derivation Pydantic model + atr_stop / vol_adjusted_size helpers. TradingDecision gains optional entry/stop/target/size_derivation fields. Cross-validator: derivation.value must match corresponding price within 0.5%. 16 unit tests. |
| W2.10 | D3: scenario prob derivation prompt rule | ✅ | 7a8cc24 | Phase2 prompt teaches the new schema fields (thesis/valuation/scenarios/catalysts/risks/derivations). Each scenario probability rationale MUST cite base rate or historical frequency, not vibes. Also moved derivations.py from agent/portfolio/ to models/ to break a circular import; 93/93 regression tests green. |
| W2.11 | W2-E1 ~ W2-E5 e2e | ✅ | 599a878 | 1) backend _trading_decisions_to_dicts pulls all W2.7+ optional fields; _persist_decisions writes them to PortfolioOrder.metadata + intent. 2) frontend ResearchPanel.tsx renders thesis/valuation/scenarios/catalysts/risks + derivation chips when present, returns null when absent (back-compat). 3) e2e PASS on 3-row mock: FULL has all 5 sections + 2 deriv chips, BAD_PROB has scenarios + warning, BARE has no panel. |
| W2.12 | Integration `test_risk_calculator_real.py` | ✅ | (final) | 4-position fixture (AAPL/NVDA/AVGO/CRWV mirrors 2026-05-07 portfolio) with mocked yfinance fetchers. Covers full async path including correlation matrix + portfolio σ + render_risk_block_for_prompt. 2 tests pass. |
| W2.13 | Cleanup test data | ✅ | (final) | 0 untracked files; mongo has 0 TST* fixtures (e2e mocks via page.route). |
| W2.14 | Bump + CHANGELOG + commit | ✅ | (final) | backend 0.27.4 → 0.27.5; frontend 0.22.4 → 0.22.5; both CHANGELOGs updated with full Wave-2 detail. |

---

## Wave 3 — Provenance + insider depth

Status: **IN PROGRESS** (W2.2 closure shipped in 0.27.9; starting W3.1)

| ID | Task | Status | Commit |
|---|---|---|---|
| W3.1 | `Source` Pydantic model + test | ✅ | 34b713d | models/source.py: Source{value: Any, source, asof, url, id} + short_label(). 12 unit tests. Bumps 0.27.9 → 0.27.10. |
| W3.2 | Quote tool Source-wrap | ✅ | 20f5c54 | QuoteData gains optional source + asof fields; each provider (Finnhub/yfinance/AV) stamps its own. AV `get_stock_quote` tool appends `Source: yfinance [YF-Q-AAPL-2026-05-09] asof 2026-05-09T18:35Z`. 9 unit tests + 114 regression tests green. |
| W3.3 | Fundamentals tool Source-wrap | ✅ | 815f233 | All 4 fundamentals @tool wrappers (overview/cash_flow/balance_sheet/earnings/insider) append `Source: alphavantage [AV-{FIELD}-{SYMBOL}-{YYYY-MM-DD}] asof ...` (or yfinance variant after W1.4 fallback). Per-tool asof comes from AV's truthful field (LatestQuarter / fiscalDateEnding / reportedDate / transaction_date). 14 new unit tests + 7 W1.5–W1.8 regression tests adapted. |
| W3.4 | News tool Source-wrap | ✅ | 7fb0276 | finnhub_news + get_news_sentiment each emit `Source: {provider} [{PREFIX}-N-{SYMBOL}-{YYYY-MM-DD}] asof <iso>`. asof = newest headline timestamp (not now()) so a stale bucket reads as stale at citation time. AV path parses `time_published` YYYYMMDDTHHMMSS and skips malformed entries. No footnote on empty list / provider failure / empty feed. 11 new unit tests; full W3 source-wrap suite 57/57 green. Bumps 0.27.12 → 0.27.13. |
| W3.5 | Insider tool Source-wrap | ✅ | 6c073db | finnhub_insider_trades (Phase1 ReAct's Finnhub-backed insider tool, distinct from the AV-backed `get_insider_activity` already wrapped in W3.3) emits `Source: finnhub [FH-INS-{SYMBOL}-{YYYY-MM-DD}] asof <iso>`. asof = latest transaction date across rows; `_parse_row_date` tolerates Finnhub `YYYY-MM-DD`, AV ISO, and yfinance `DataFrame.to_dict()` shapes. No footnote when empty / provider failure. 13 new unit tests; W3 source-wrap suite 70/70. Bumps 0.27.13 → 0.27.14. |
| W3.6 | Phase2 prompt: thesis cites source IDs | ✅ | 64649c6 | Phase2 prompt now requires each thesis bullet that names a number/event to end with the matching `[ID]` token from W3.2-W3.5 tool footnotes. Worked example carries 3 bracketed tokens spanning Q/OV/N families. Pure qualitative bullets may skip. 5 new prompt-source tests + 6 phase2-regression green. Bumps 0.27.14 → 0.27.15. |
| W3.7 | Frontend footnote superscript + list | ✅ | 09c8408 | ResearchPanel parses `[FH-Q-AAPL-2026-05-09]` style tokens out of thesis bullets, replaces each with a numeric superscript chip, and renders a numbered "Sources" list at the panel bottom resolving each id to `Provider · field · symbol · asof`. Pure-function helpers `extractFootnotes` + `parseSourceId` + `SOURCE_ID_PATTERN` exported for W3.12 e2e reuse. 12 vitest tests cover regex / bullet segmentation / dedup / dotted-symbol parsing. Pre-W3.6 thesis (no tokens) renders unchanged — full back-compat. Bumps frontend 0.22.7 → 0.22.8. |
| W3.8 | SEC EDGAR Form 4 fetcher (UA `ffffhhhww@qq.com`) + test | ✅ | e9411c7 | New `agent/tools/sec_edgar/form4.py`: `Form4Client` async ctx-mgr exposing `lookup_cik` (cached ticker→CIK from `files/company_tickers.json`, single fetch per process) + `fetch_form4_atom` (atom XML for `type=4&output=atom`, count clamped 1..100). Token-bucket at default 8 req/s leaves headroom under PRD AC#5 ceiling 10/s; test asserts 50-seq stays under. UA defaults to D4 `ffffhhhww@qq.com`, env-overridable, blank→default. 17 unit tests with httpx.MockTransport. Bumps 0.27.15 → 0.27.16. |
| W3.9 | Form 4 footnote parser (10b5-1 detection) | ✅ | 2dc9899 | `parse_form4_detail` walks SEC ownership-document XML for `nonDerivativeTransaction` rows + footnote refs → `list[Form4Transaction]` (date/code/shares/price/post-tx holdings + `plan_type` + `plan_adopted_date` + reporter + issuer). `classify_plan_type` distinguishes 10b5-1 / discretionary / unknown across phrasing variants; explicit `not pursuant to 10b5` wins. `extract_plan_adopted_date` parses ISO/prose/US-numeric. `Form4Client.fetch_recent_transactions` chains atom → detail XMLs into a flat list, individual 404s skipped. 18 new tests; PRD AC#3 directly asserted. Bumps 0.27.16 → 0.27.17. |
| W3.10 | Insider schema: plan_type, pct_of_holdings_after, last_12mo | ✅ | c8467de | New `src/agent/tools/finnhub/insider_enrich.py` pure-function bridge between provider rows (Finnhub / AV / yfinance) and W3.9 `Form4Transaction` records. `enrich_insider_rows(rows, form4_txs)` matches by date + shares within 1 (RSU fractional tolerance) and merges `plan_type` / `shares_owned_after` / `plan_adopted_date.isoformat()` / derived `pct_of_holdings_after`; never mutates input. `compute_pct_of_holdings_after` returns 0..1 ratio with None on missing/zero/negative legs. `build_last_12mo_summary` aggregates 365-day window (inclusive at anchor, inclusive at cutoff) into transaction count + plan_breakdown + total_shares with `.render()` markdown summary. `render_enriched_row` appends `plan=...` / `X% of holdings after` segments only when populated; pre-enrichment rows render exactly like W3.5. NOT yet wired into live `finnhub_insider_trades` — opt-in until W3.13 SEC integration lands. 29 new tests; Wave 3 sweep 93/93. Bumps 0.27.17 → 0.27.18. |
| W3.11 | Phase1 prompt: discretionary cluster rule | ✅ | de50468 | New INSIDER FRAMING RULE block in `src/agent/portfolio/phase1_research.py`'s `_analyze_symbol` prompt. Three conjunctive conditions for bearish framing: cluster ≥3 sells in 30-day window, ≥1 tx with `pct_of_holdings_after > 0.05`, breaks 12-month pattern (must be inconsistent with `last_12mo` summary). PLAN-TYPE OVERRIDE: `10b5-1` MUST NOT be cited as discretionary bearish regardless (PRD AC#4); state `plan_type` + `plan_adopted_date`, treat as neutral. `discretionary` / `unknown` may contribute only when all three conditions hold. Missing plan_type defaults to neutral (fail-closed). 13 prompt-source tests in `tests/test_phase1_insider_framing_rule.py` lock wording. Wave 3 sweep 106/106. Bumps 0.27.18 → 0.27.19. |
| W3.12 | W3-E1 ~ W3-E4 e2e | ✅ | 6712d4d2 | New `tests/e2e_source_footnote.py` ties together W3.4 + W3.5 + W3.7 + W3.10 + W3.11 surfaces in a purely offline pipeline (no LLM / no SEC). W3-E1 mirrors the JS `SOURCE_ID_PATTERN` in Python and verifies extraction + citation-order dedup. W3-E2 round-trips IDs back to provider/field/symbol/asof across all 3 prefixes + dotted symbols + forward-compat unknown-field. W3-E3 pipes fixture rows through `enrich_insider_rows` → `render_enriched_row` asserting `plan=10b5-1` / `6.0% of holdings after` / unknown-plan suppression / 12-mo summary `3 discretionary`. W3-E4 single-10b5-1 fails cluster size + triggers PLAN-TYPE OVERRIDE; 3-tx discretionary cluster satisfies all three conditions (3 sells in 18-day span, 0.06 > 0.05, prior 12mo only 10b5-1 activity → cluster IS first discretionary burst). 15 new tests; Wave 3 sweep 121/121. Bumps 0.27.19 → 0.27.20. |
| W3.13 | Integration `test_form4_real.py` | ✅ | eee24c7 | New `tests/test_form4_real.py` — 9 live SEC integration tests (`pytestmark = pytest.mark.integration`), skipped by default. Covers CIK lookup (NVDA pinned to 0001045810), atom feed shape, fetch_recent_transactions returns ≥3 plan_type-populated tx (PRD AC#3 against live data), unknown-symbol short-circuit, 50 sequential calls under 10 req/s (PRD AC#5; measured 0.69 req/s), default rate constant < 10, concurrent atom fetches don't corrupt. **Real bug found:** `_index_to_form4_xml_url`'s `-index.htm` → `.xml` suffix swap was wrong for real SEC — primary docs use `wk-form4_<id>.xml` / `primary_doc.xml` / etc., SEC has no fixed convention. W3.9 mock tests passed because handler matched on SUT-generated URLs (self-reinforcing). Fix: new async `_resolve_form4_doc_url` fetches `{folder}/index.json` and picks first `.xml` entry; old swap kept as fallback (preserves W3.9's 18 fixture tests zero-change). 3 new resolver unit tests. Interview case study at `docs/interview/2026-05-09-sec-edgar-form4-url-resolution.md`. Wave 3 offline 124/124, integration 9/9 against live SEC. Bumps 0.27.20 → 0.27.21. |
| W3.14 | Cleanup test data | ✅ | 229a141 | `ruff check --fix` across all Wave 3 paths (`src/agent/tools/sec_edgar/`, `src/agent/tools/finnhub/insider_enrich.py`, all new tests). Fixes: import-order normalization, `typing.Iterable` → `collections.abc.Iterable` (UP035 py3.12 idiom), removed unused PLAN_TYPE_UNKNOWN import in test_form4_real.py. Audit: zero `print`/TODO/FIXME hits across Wave 3 files; zero leaked-secrets hits. W3.9 mock fixtures kept — they now test the `_resolve_form4_doc_url` fallback path. 148 pre-existing ruff warnings outside Wave 3 paths intentionally NOT touched (out of scope). Wave 3 sweep 124/124 still green after rewrite. Bumps 0.27.21 → 0.27.22. |
| W3.15 | Bump + CHANGELOG + commit | ✅ | dad532f | Wave 3 close — minor bump 0.27.22 → 0.28.0 marks the full provenance + insider-depth surface as shipped (W3.1 schema → W3.7 frontend chips → W3.13 live-SEC integration). CHANGELOG carries a Wave-3 close section with PRD AC + E2E AC audit tables. Final regression sweep: 124/124 offline + 9/9 live-SEC integration green. |

---

## Wave 3 hotfix — Phase 1 provenance fix bundle (post-Wave 3)

Status: **DONE** (4/4 sub-tasks shipped in 0.28.1; W3.17 carved out as follow-up)

A real frontend→backend e2e single_symbol run on 2026-05-09 against NVDA exposed three independent regressions every Wave 3 unit/e2e test missed (recurring "mock-self-reinforcement" antipattern). All three fixed; one Phase 2 gap documented + tracked as W3.17.

| ID | Task | Status | Commit |
|---|---|---|---|
| W3.16-A | `finnhub_quote` source-wrap parity (port W3.2 wrap to Finnhub-backed quote tool) | ✅ | fab820b | `_quote_source_id` helper + body-append in `src/agent/tools/finnhub/quotes.py`. Preserves DataManager fallback chain (yfinance/AV) so `QuoteData.source` flips drive the right token prefix. Legacy QuoteData rows without `source`/`asof` silently skip the footnote. 13 unit tests in `test_finnhub_quote_source_wrap.py`. |
| W3.16-B | Phase 1 prompt: TOKEN PRESERVATION RULE | ✅ | fab820b | New 4th rule (after FIBONACCI / FUNDAMENTAL / INSIDER FRAMING) with 5 clauses: preserve verbatim / append `[ID]` to citing sentence / multi-source space-separated / never invent / never delete `Source:` lines. Cross-references W3.6 + Phase 2. Live verification: NVDA report 0 → 8 tokens (1× FH-Q, 1× FH-N, 6× YF-OV). 11 prompt-source tests. |
| W3.16-C | Phase 1 token-counter dict-shape fix | ✅ | fab820b | `react_agent.ainvoke` returns top-level `input_tokens`/`output_tokens`, not a `usage` wrapper. Fix: read top-level keys with `or 0` guard. Live verification: input 0 → 38862, output 0 → 1870, tool_executions 7. 4 unit tests including a deliberate failure-mode test catching future regression to wrapped form. |
| W3.16-D | Real-data integration test (single_symbol flow) | ✅ | fab820b | New `test_single_symbol_flow_real.py` (`pytest.mark.integration`) reads latest `portfolio_orders.metadata.full_research` row (24h cutoff, skip otherwise). 3 assertions: Phase 1 carries ≥1 source-id token / Phase 1 length > 200 / Phase 2 cites ≥1 token across thesis/reasoning/scenarios. **Phase 2 assertion currently `xfail strict=True` and tracked as W3.17.** Uses sync `pymongo` (motor async fixture incompatible with pytest-asyncio per-test event loops at module scope). |

### Tracked follow-up

| ID | Task | Status | Commit | Notes |
|---|---|---|---|---|
| W3.17 | Phase 2 prompt: require `reasoning_summary` to cite `[ID]` tokens | ✅ | 8838c4a | New rule co-located with W3.6 thesis rule in Structured Research Blocks (`phase2_decisions.py:330-345`). Same 5 token-family examples, "research malpractice" language, qualitative-phrase carve-out. Worked example reasoning_summary extended with `[FH-N-EXMP-2026-02-08]` + `[AV-OV-EXMP-2025-12-31]` demonstrations. `reasoning_zh` is post-translated so prompt change is enough — tokens preserved through translation step. W3.16-D integration test unxfailed. Live NVDA HOLD verification: phase1 8→12 tokens, phase2 reasoning 0→3 tokens, reasoning_zh 0→3 tokens, thesis 3 bullets all cited. 5 prompt-lock unit tests in `test_phase2_reasoning_source_ids.py`. **Operational note:** backend uvicorn runs without `--reload`, so prompt-only edits require `docker compose restart backend` to take effect. |
| W3.18 | Extended-hours companion price (Holdings + Watchlist + Phase 1/2 visibility) | ✅ | 356f702 | `QuoteData` schema +4 optional fields with full backwards-compat for legacy redis rows (4 serialization tests). New `_extended_hours_companion(info, primary_session, primary_price, previous_close)` helper with 18h post / 6h pre freshness gates and pct vs *primary* (not prev_close — UX question is "delta from what user sees on the table", 16 helper tests). `DataManager._enrich_extended_hours_companion` + `_fetch_yfinance_info` add a separate `market:quote_ext:<SYM>` cache (TTL 300s) so the slow `Ticker.info` HTTP roundtrip doesn't gate the primary refresh; all failures swallowed (companion is decoration, 9 enrichment tests). Holding + WatchlistItem models gain four response-only ext-hours fields (NOT persisted — recomputed each GET, weekend-correct). Frontend `ExtHoursLine` component renders `AH $215.05 (-0.07%)` / `PM $214.80 (-0.19%)` under the primary cell on PortfolioSummaryTable + WatchlistPanel (8 Vitest cases). Phase 1 quote tools (Finnhub + AV) append `After-hours: $X.XX (±Y%)` line under same source-id token (one quote = one citation, 4 tool-body tests). Phase 1 prompt 1-sentence rule + Phase 2 prompt new "Important Considerations" bullet #6 extending the W3.17 citation contract to ext-hours moves ≥ ±1% (3 prompt-lock tests). Reworded W3.18 bullet's failure phrasing to avoid colliding with W3.17's `research malpractice` anchor. **Total:** 41 backend tests + 8 frontend tests across 6 new files; pre-existing ext-hours suite still 21/21 green; W3.6 + W3.17 prompt locks still 9/9 green. |

---

## Decisions log (per-task small choices that don't deserve PRD update)

| Date | Task | Decision | Reason |
|---|---|---|---|
| 2026-05-08 | PRD freeze | All 5 user-decisions locked | See PRD Part 3 |

---

## Resume protocol

If session crashes:
1. `git log --oneline -20` — find latest commit
2. Match commit message prefix to a `W*.N` task ID below
3. Find first ⏳ task after that, that's where to resume
4. Read PRD Part 3 + Part 4 row for that sub-task to recover context
