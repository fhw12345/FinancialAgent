# Stock Agent Upgrade — Progress Tracker

**PRD:** [STOCK_AGENT_UPGRADE_PRD.md](./STOCK_AGENT_UPGRADE_PRD.md) (frozen 2026-05-08)
**Started:** 2026-05-08
**Owner:** orchestrator

> Each sub-task = one commit. Mark ✅ when committed. Include commit hash + UTC timestamp.
> If interrupted, resume from the first ⏳ task. Read PRD section + this row to recover context.

---

## Wave 1 — Hard bugs + data fallback

Status: **IN PROGRESS**

| ID | Task | Status | Commit | Notes |
|---|---|---|---|---|
| W1.1 | `OrderIntent` enum + Pydantic validator + unit test | ✅ | (pending) | Reject CRWV-style payload (stop > limit on close_long). 11 tests pass. |
| W1.2 | Migration script `migrate_order_intent.py` dry-run + apply | ⏳ | - | Infer intent from sign(stop-entry), sign(target-entry) |
| W1.3 | Frontend OrderPreview intent badge + W1-E1 e2e | ⏳ | - | Mock close_long valid + invalid payload |
| W1.4 | yfinance fallback helper `_yf_fallback.py` | ⏳ | - | Single source of truth for AV→yf fallback |
| W1.5 | `get_company_overview` connect fallback + unit test | ⏳ | - | Returns `{data, source, asof, degraded}` or `{unavailable: true}` |
| W1.6 | `get_financial_statements` connect fallback + unit test | ⏳ | - | yfinance.income_stmt/balance_sheet/cashflow |
| W1.7 | `get_earnings` connect fallback + unit test | ⏳ | - | yfinance.earnings_dates + .calendar |
| W1.8 | `get_insider_activity` connect fallback + unit test | ⏳ | - | yfinance.insider_transactions |
| W1.9 | Fibonacci tool `current_price_position` + Phase1 prompt rule + unit test | ⏳ | - | above_range/in_range/below_range; price 9% above swing → above_range |
| W1.10 | Consistency checker LLM gate + unit test | ⏳ | - | Cheap model, ≤2k tokens, ≤$0.05/run |
| W1.11 | Global disclaimer footer + UI watermark + W1-E2 e2e | ⏳ | - | "AI-generated · not investment advice" on 4 routes |
| W1.12 | `data_quality=degraded` UI tag + W1-E3 e2e | ⏳ | - | Grey 数据降级 tag + tooltip |
| W1.13 | Integration test `test_intent_real_phase2.py` | ⏳ | - | FakeListChatModel injects invalid output, real `_persist_decisions` raises |
| W1.14 | Cleanup test data | ⏳ | - | Remove `*_dump.json` `*_after.json` etc |
| W1.15 | Bump version + CHANGELOG + final commit | ⏳ | - | backend patch (0.27.4) + frontend patch (0.22.4) |

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

Status: **NOT STARTED** (gated on Wave 1 user signoff)

| ID | Task | Status | Commit |
|---|---|---|---|
| W2.1 | Single-symbol flow `run_single_symbol` | ⏳ | - |
| W2.2 | Delete legacy single ReAct entry; 410 | ⏳ | - |
| W2.3 | Translate Phase1 prompts to English | ⏳ | - |
| W2.4 | A/B 5 historical runs old vs new prompt | ⏳ | - |
| W2.5 | `risk_calculator.py` + unit test | ⏳ | - |
| W2.6 | Wire risk_calculator into Phase2 prompt | ⏳ | - |
| W2.7 | `PortfolioDecision` schema extension | ⏳ | - |
| W2.8 | Pydantic validators (lengths + prob sum) + test | ⏳ | - |
| W2.9 | Numeric derivation `{value, formula, inputs}` + helpers | ⏳ | - |
| W2.10 | D3: scenario prob derivation prompt rule | ⏳ | - |
| W2.11 | W2-E1 ~ W2-E5 e2e | ⏳ | - |
| W2.12 | Integration `test_risk_calculator_real.py` | ⏳ | - |
| W2.13 | Cleanup test data | ⏳ | - |
| W2.14 | Bump + CHANGELOG + commit | ⏳ | - |

---

## Wave 3 — Provenance + insider depth

Status: **NOT STARTED** (gated on Wave 2 user signoff)

| ID | Task | Status | Commit |
|---|---|---|---|
| W3.1 | `Source` Pydantic model + test | ⏳ | - |
| W3.2 | Quote tool Source-wrap | ⏳ | - |
| W3.3 | Fundamentals tool Source-wrap | ⏳ | - |
| W3.4 | News tool Source-wrap | ⏳ | - |
| W3.5 | Insider tool Source-wrap | ⏳ | - |
| W3.6 | Phase2 prompt: thesis cites source IDs | ⏳ | - |
| W3.7 | Frontend footnote superscript + list | ⏳ | - |
| W3.8 | SEC EDGAR Form 4 fetcher (UA `ffffhhhww@qq.com`) + test | ⏳ | - |
| W3.9 | Form 4 footnote parser (10b5-1 detection) | ⏳ | - |
| W3.10 | Insider schema: plan_type, pct_of_holdings_after, last_12mo | ⏳ | - |
| W3.11 | Phase1 prompt: discretionary cluster rule | ⏳ | - |
| W3.12 | W3-E1 ~ W3-E4 e2e | ⏳ | - |
| W3.13 | Integration `test_form4_real.py` | ⏳ | - |
| W3.14 | Cleanup test data | ⏳ | - |
| W3.15 | Bump + CHANGELOG + commit | ⏳ | - |

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
