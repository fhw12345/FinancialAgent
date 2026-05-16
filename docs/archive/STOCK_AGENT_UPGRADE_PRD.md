# PRD: Stock Analysis Agent — Trustworthy Daily Briefing Upgrade

> **Archived** — kept for historical context. This PRD was frozen on 2026-05-08
> and drove the Wave 1–3 stock-agent upgrade. The shipped architecture is
> described in [`docs/features/portfolio-agent-architecture-refactor.md`](../features/portfolio-agent-architecture-refactor.md).

**Status:** FROZEN 2026-05-08
**Owner:** orchestrator (per repo CLAUDE.md, autonomous mode NOT opted in — wave-by-wave user signoff required)
**Scope:** `backend/src/agent/portfolio/`, `backend/src/agent/tools/`, `backend/src/models/trading_decision.py`, `frontend/src/components/orders/`, `frontend/src/components/reports/`

---

## Part 1 — Problem Statement

Two reviews (PM/quant + sell-side analyst) agree the agent is "Seeking Alpha mid-tier wrapped in pretty markdown" — not trustworthy as a personal daily-briefing tool. Two concrete failures already shipped to mongo:

1. **Wrong-order risk.** CRWV `SELL` decision had `entry=$138 / stop=$142 / target=$122`. This `stop > entry > target` layout is byte-identical to a short-trade payload in any OMS. There is no `intent` field separating "close long" from "open short" — a human or downstream system **will** mis-route it.
2. **Hallucinated thesis.** Across all 4 holdings, `get_company_overview` and `get_cash_flow` returned empty (Alpha Vantage 25/day cap), yet Phase2 still produced "TICKER is the cheapest of the cohort" — a P/E claim with no P/E in evidence. No retry, no fallback, no consistency gate.

**Goal:** keep the LLM-driven research surface, bolt on (a) hard-typed intent semantics, (b) deterministic data fallback + risk math, (c) schema-enforced derivations + sources. Every number on screen is either footnoted or explicitly marked unavailable.

---

## Part 2 — Goals / Non-Goals

**Goals (13 items, mapped A–M from reviews):**
- A: `OrderIntent` enum
- B: yfinance fundamentals fallback
- C: deterministic risk calculator
- D: unify three paths (single-symbol = Phase1+Phase2 single mode)
- E+K: Fibonacci sanity gate
- F: per-claim source object
- G: report schema (Thesis / Valuation×2 / PT / Bull-Base-Bear / Catalysts / Risks)
- H: consistency checker between data + thesis
- I: numeric-derivation enforcement
- J: Form 4 footnote parsing (10b5-1 vs discretionary, % of holdings, 12-mo pattern)
- L: Phase2 risk math hard constraints
- M: global disclaimer + UI watermark
- + data-quality logging

**Non-Goals (will NOT do, see Part 5 for reasons):**
- Segment revenue split
- Real-time unusual-options "whale" tape
- Named-broker same-day rating changes
- Broker auto-execution
- Sell-side institutional initiation-report parity
- Any new paid data source

---

## Part 3 — Decisions Locked (user signoff 2026-05-08)

| # | Decision point | Choice |
|---|---|---|
| D1 | Consistency gate | **LLM-based** (cheap model, ≤2k tokens, ≤$0.05/run) |
| D2 | Phase1 prompt language | **Translate to English**. Existing zh mongo messages stay untouched; only new analyses run EN → frontend `useTranslated` path renders zh |
| D3 | Scenarios probability | **Add derivation constraint** in prompt: each prob must cite base rate / historical frequency reasoning |
| D4 | SEC EDGAR User-Agent | Default `ffffhhhww@qq.com` via `SEC_EDGAR_USER_AGENT` env. If env missing, fall back to default (do NOT fail fast) |
| D5 | Wave scope | **All 3 waves**, sub-tasks split fine, progress md updated per task |

---

## Part 4 — Three-Wave Delivery Plan

### Wave 1 — Hard bugs + data fallback (5–7 days, MUST ship first)

Items: **A, B, E, K, H, M** + data-quality logging.

#### Sub-tasks (small, one commit each)

| ID | Task | Files |
|---|---|---|
| W1.1 | `OrderIntent` enum + Pydantic validator (`close_long` rejects `stop > limit`) + unit test | `backend/src/models/trading_decision.py`, `backend/tests/models/test_trading_decision.py` |
| W1.2 | Migration script `migrate_order_intent.py` (dry-run + `--apply`); infer intent from sign(stop-entry), sign(target-entry) | `backend/scripts/migrate_order_intent.py` |
| W1.3 | Frontend OrderPreview intent badge + W1-E1 e2e (mock close_long valid + invalid payload) | `frontend/src/components/orders/OrderPreview.tsx`, `e2e_intent_disclaimer.py` |
| W1.4 | yfinance fallback helper module | `backend/src/agent/tools/_yf_fallback.py` |
| W1.5 | `get_company_overview` connect fallback + unit test | `backend/src/agent/tools/alpha_vantage/fundamentals.py:33`, test |
| W1.6 | `get_financial_statements` connect fallback + unit test | `:73`, test |
| W1.7 | `get_earnings` connect fallback + unit test | locate or extend `fundamentals.py`, test |
| W1.8 | `get_insider_activity` connect fallback + unit test | `:162`, test |
| W1.9 | Fibonacci tool `current_price_position` field + Phase1 prompt rule + unit test | locate `fibonacci_analysis_tool` in `backend/src/agent/tools/`, `backend/src/agent/portfolio/phase1_research.py` |
| W1.10 | Consistency checker LLM gate + unit test | new `backend/src/agent/portfolio/consistency_gate.py`, wired in `flows.py` |
| W1.11 | Global disclaimer footer + UI watermark + W1-E2 e2e | `phase2_decisions.py:264` (message storage), frontend layout, e2e |
| W1.12 | `data_quality=degraded` UI tag + W1-E3 e2e | mongo schema field, OrderPreview, e2e |
| W1.13 | Integration test (real backend, mock LLM) `test_intent_real_phase2.py` | `backend/tests/integration/test_intent_real_phase2.py` |
| W1.14 | Cleanup: remove fixture/mock/throwaway files; ensure no test data in commits | repo root, `chats_*.json`, etc |
| W1.15 | bump version + CHANGELOG + final commit | `backend/pyproject.toml`, `frontend/package.json`, CHANGELOGs |

#### Wave 1 Acceptance Criteria

1. `pytest backend/tests/models/test_trading_decision.py::test_close_long_rejects_stop_above_entry` passes; the historical CRWV payload raises `ValidationError`.
2. `python backend/scripts/migrate_order_intent.py --dry-run` prints inferred intent for every existing decision; zero `unknown`.
3. Run `analyze_holdings` with `ALPHA_VANTAGE_API_KEY=invalid`. Phase1 output: ≥1 symbol shows `source: yfinance`, P/E and market cap populated.
4. Both AV invalid + yfinance ticker `XYZFAKE`. Tool returns `{"unavailable": true}`; consistency gate flags violation if Phase1 still cited the field.
5. Fibonacci unit test: input price 9% above swing high → `current_price_position == "above_range"`.
6. UI smoke: every report card shows disclaimer footer; OrderPreview renders intent badge on `close_long` decision.

#### Wave 1 e2e

| AC | Verification |
|---|---|
| W1-E1 | OrderPreview close_long renders 平多 badge (amber) + stop label "止损 (低于现价)"; CRWV-style payload (stop>limit) shows error placeholder, not a normal row |
| W1-E2 | Disclaimer "AI-generated · not investment advice" visible on dashboard / holdings table / watchlist / chat modal (4 routes) |
| W1-E3 | Mock holding with `data_quality=degraded` shows grey "数据降级" tag + tooltip listing fallback fields |

#### Wave 1 Integration Test

`backend/tests/integration/test_intent_real_phase2.py` — use `langchain.chat_models.fake.FakeListChatModel` to inject a CRWV-style invalid Phase2 output, run real `_persist_decisions()`, assert Mongo write raises `ValidationError`.

**Effort:** 5–7 dev-days. **Blocks:** Wave 2 risk_calculator needs B (W1.4–W1.8) populating `beta`, `sector`, `marketCap`.

---

### Wave 2 — Architectural upgrades (8–12 days, depends on Wave 1)

Items: **D, C, L, G, I.**

#### Sub-tasks

| ID | Task |
|---|---|
| W2.1 | Add `run_single_symbol` flow to `flows.py`; route stock analysis through Phase1+Phase2 (degenerate single-symbol mode) |
| W2.2 | Delete legacy single ReAct entry; old endpoint returns 410 |
| W2.3 | Translate Phase1 system+user prompts to English (per D2) |
| W2.4 | A/B test 5 historical runs old (zh) vs new (en) prompts; manual diff scenarios + PT |
| W2.5 | New `risk_calculator.py` (sector exposure, beta-weighted, cash%, HHI, 60d corr matrix) + unit test |
| W2.6 | Wire risk_calculator output into Phase2 prompt as hard constraints |
| W2.7 | `PortfolioDecision` schema extension: thesis (3 bullets), valuation (≥2 methods), price_target, scenarios (bull/base/bear, prob sum=1.0±0.02), catalysts, risks (3) |
| W2.8 | Pydantic validators for schema (lengths + prob sum) + unit test |
| W2.9 | Numeric derivation: every `limit_price` / `protective_stop` / `target_price` / `position_size_pct` carries `{value, formula, inputs}`. Helpers `atr_stop`, `vol_adjusted_size`. Phase2 prompt: no formula → must use qualitative band |
| W2.10 | Phase2 prompt rule for D3: each scenario probability must cite base rate / historical frequency |
| W2.11 | W2-E1 ~ W2-E5 e2e (`e2e_report_schema.py`) |
| W2.12 | Integration test `test_risk_calculator_real.py` (real 4-holding fixture, no LLM mock) |
| W2.13 | Cleanup test data |
| W2.14 | Bump version + CHANGELOG + commit |

#### Wave 2 Acceptance Criteria

1. `curl POST /api/stocks/{symbol}/analyze` payload shows `phase: phase1` then `phase2`; legacy single-ReAct route returns 410.
2. `grep -P "[一-鿿]" backend/src/agent/portfolio/phase1_research.py` returns 0 matches inside string literals.
3. `risk_calculator` unit test: 3-position fixture asserts sector_exposure / HHI / beta-weighted exposure within 1e-6 of hand-computed.
4. `PortfolioDecision` with 1 valuation method or scenario prob sum 0.7 → rejected.
5. `target_price.value=620` without `formula` → rejected; with valid formula → accepted; computed value cross-checks within 0.5%.
6. Manual: rerun original 4-holding portfolio. CRWV decision has valid scenarios prob=1.0 sum, ≥2 valuation methods, stop has ATR or support derivation with timestamp.

#### Wave 2 e2e

| AC | Verification |
|---|---|
| W2-E1 | Single-symbol path: chat modal renders 2 visual sections (Research / Decision), not one markdown blob |
| W2-E2 | Phase2 report shows 4 fixed sections (Thesis 3 bullets / Valuation ≥2 methods table / Scenarios bull/base/bear table+bar / Catalysts) |
| W2-E3 | Mock prob sum = 0.7 → frontend shows error placeholder, no broken bar |
| W2-E4 | Numbers with derivation show superscript on hover (formula+inputs); without derivation grey out |
| W2-E5 | Risk calculator output (sector exposure / cash% / HHI) renders as structured numbers in summary, not LLM text |

**Effort:** 8–12 dev-days.

---

### Wave 3 — Provenance + insider depth (6–10 days, depends on Wave 2 schema)

Items: **F, J.** Tracked-but-deferred follow-ups in Part 6.

#### Sub-tasks

| ID | Task |
|---|---|
| W3.1 | `Source` Pydantic model `{value, source, asof, url}` + unit test |
| W3.2 | Refactor quote tool output to Source-wrap |
| W3.3 | Refactor fundamentals tool output |
| W3.4 | Refactor news tool output |
| W3.5 | Refactor insider tool output |
| W3.6 | Phase2 prompt: thesis bullets reference source IDs |
| W3.7 | Frontend ReportRenderer: footnote superscript + bottom footnote list |
| W3.8 | New `backend/src/agent/tools/sec_edgar/form4.py` (atom feed fetcher, 10 req/s, User-Agent from D4 default) + unit test |
| W3.9 | Form 4 footnote parser: extract 10b5-1 plan adoption date, transaction code |
| W3.10 | Insider tool schema upgrade: per-tx `plan_type` / `pct_of_holdings_after` / `last_12mo` |
| W3.11 | Phase1 prompt: discretionary cluster sells > X **and** > Y% **and** breaking 12-mo pattern → bearish framing only |
| W3.12 | W3-E1 ~ W3-E4 e2e (`e2e_source_footnote.py`) |
| W3.13 | Integration test `test_form4_real.py` (real SEC EDGAR, `@pytest.mark.integration`) |
| W3.14 | Cleanup test data |
| W3.15 | Bump + CHANGELOG + commit |

#### Wave 3 Acceptance Criteria

1. JSON of Phase2 decision: every numeric field under `valuation`, `price_target`, `scenarios` is a `Source` object; `pytest -k "test_no_bare_floats"` walks the model and asserts no untyped float.
2. UI: hover any number → tooltip shows source name + asof; click opens URL when present.
3. `python -m backend.src.agent.tools.sec_edgar.form4 --symbol NVDA --limit 5` prints 5 parsed Form 4s with `plan_type` populated for ≥3.
4. Fixture test: a `plan_type=10b5-1, plan_adopted=2024-03-01` insider tx with current date 2025-01-01 is **not** allowed to be cited as discretionary bearish.
5. Rate-limit test: 50 sequential SEC requests stay under 10/s.

#### Wave 3 e2e

| AC | Verification |
|---|---|
| W3-E1 | Every report number has footnote superscript `[1]`, `[2]`, …; hover shows source + asof |
| W3-E2 | Footnote list at report bottom; non-empty URL opens in new tab |
| W3-E3 | Insider table per row: plan_type label (10b5-1 grey / discretionary red-green / unknown), pct_of_holdings_after column |
| W3-E4 | Mock 1 single 10b5-1 sale → decision text grep no "strong bearish"; mock 3 discretionary > 5% holdings → decision grep bearish framing |

**Effort:** 6–10 dev-days.

---

## Part 5 — Risks & Mitigations

| Risk | Mitigation |
|---|---|
| yfinance rate limit / IP block | retry with exponential jitter (3 attempts), 15-min in-process LRU cache `(symbol, endpoint, date)` |
| `yfinance.info` returns None for small caps (CRWV) | W1.4 explicit `unavailable=true`, never silent default to 0 / "" |
| Phase2 prompt EN drift | W2.4 A/B compare 5 historical runs, diff scenarios + PT |
| Intent enum is breaking change | W1.2 dry-run migration; legacy reader kept 1 release |
| Single-symbol latency 3min → 5min after Phase1+Phase2 | Frontend SSE progress; prefetch on watchlist hover |
| Consistency gate adds 1 LLM call | Cheap model, ≤2k tokens, budget ≤$0.05/run |
| SEC EDGAR rate limit / User-Agent | Centralised httpx client; default UA `ffffhhhww@qq.com` per D4 |
| LLM emits invalid JSON under stricter Wave 2 schema | Pydantic strict + 1 retry with errors injected; second fail → degrade to "holdings unchanged" |

---

## Part 6 — Explicitly Out of Scope (will not be done)

- **Segment revenue breakdown** — requires 10-K text extraction, effort > rest of PRD
- **Real-time unusual-options whale tape** — needs OPRA paid feed
- **Named-broker same-day rating changes** — needs FactSet/Refinitiv paid feed; we use yfinance/Finnhub mean target as directional proxy and label it as such
- **Broker auto-execution** — personal tool stays read-only by design
- **Sell-side institutional initiation-report completeness** — wrong product target

## Part 7 — Out of Scope This PRD, Tracked

- Self-computed unusual options activity (`today_volume / 30d_avg_volume` from `yfinance.option_chain`) — Wave 3 follow-up
- Finnhub `recommendation_trends` ingestion — Wave 3 follow-up, feeds Wave 2 valuation triangulation
- Full DCF model with user-input WACC/growth — UI cost too high

---

## Inter-wave Dependency Graph

```
Wave 1 B (yfinance fallback → beta, sector, marketCap)
  └─► Wave 2 C+L (risk_calculator)
        └─► Wave 2 G (valuation pe_vs_peer)
              └─► Wave 3 F (Source wrap final schema)

Wave 1 A (intent) ──► Wave 2 I (formula triple attaches to intent fields)
Wave 1 H (gate) ────► Wave 3 F (gate also checks Source.asof staleness)
```

---

## Cleanup discipline

After each Wave: delete throwaway dump files (`*_dump.json`, `*_after.json`, scratch e2e probes that aren't keep-worthy), remove mongo test data inserted by integration tests in `finally` blocks. **No test data in committed repo.**
