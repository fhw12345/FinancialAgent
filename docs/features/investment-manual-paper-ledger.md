---
title: Offline-Friendly Manual Paper Ledger
status: shipped
version: backend@0.60.0, frontend@0.41.0
last_updated: 2026-10-08
owner: maintainer
related_paths:
  - backend/src/models/paper_ledger.py
  - backend/src/services/paper_ledger/
  - backend/src/api/portfolio/paper.py
  - frontend/src/components/portfolio/paper/
---

# IDQ-008-A：按需启动、手动模拟记账与估值

## Authorization / Scope

User clarified the service is not online 24h and approved the revised **manual paper
bookkeeping + explicit on-demand valuation** scope. This supersedes the proposed
next-open engine for this slice. No timer, worker, broker, model call, implicit opening
trade, retroactive favorable fill, or stop-loss monitoring is included.

This is an independent **manual scenario journal**, like manual actual-trade recording
but strictly paper. It does not consume or relabel local_holdings approvals as approved
paper fills. Model suggestions can inform the user, but these bookings are explicitly
`manual_unverified`, not `AI-validated`, executable orders or verified forward results.
Paper-account research/review scopes and policy-linked simulated execution remain future
IDQ-008-B; IDQ-008 as a whole remains in-progress, not fully shipped by this slice.

## Frozen Contracts

- Explicit cash-only creation: user chooses name, USD initial cash, allowlisted symbols,
  commission bps and directional slippage bps (including explicitly entering zero).
  No real-account copying, activation or invented personal values. Long-only/no borrowing.
- Trades are user-entered scenario reference prices and quantities, recorded **now** by
  server time. No editable/backdated fill time, imported approval ID, arbitrary source URL,
  limit/bracket, short, or readiness fields. Manual scenario prices are not market evidence.
- Decimal wire strings, quantity/price precision ≤6 decimals; cash/fees/cost basis cents,
  ROUND_HALF_EVEN at disclosed monetary boundaries; FIFO includes buy fees in lot basis
  and sell fees in proceeds. Partial sales allocate cent-rounded basis; final lot depletion
  consumes its full residual basis. No dust or float accounting. Fixed bounded ranges.
- Trade price = reference × (1 ± slippage_bps / 10000); principal is rounded once to cents;
  commission is principal × commission_bps / 10000, cents. A scenario price itself is not
  certified. All trades and corporate actions disclose their manual origin.
- Explicit manual split/dividend journal entries support offline reconciliation. Split
  preserves total basis and cash; unsupported sub-microshare rounding is rejected.
  Dividend cash = current quantity × declared gross/share − declared withholding; not
  auto-detected, dated back to an ex-date, or a claim of market entitlement. No action is
  inferred from price drops. No deposits/withdrawals, history deletion or silent correction.
  An erroneous experiment may be closed read-only and replaced, with old history retained.
- Confirm each valuation's corporate-action reconciliation through the requested completed
  XNYS session. This user attestation is a limitation, not independent action verification.
  Without reconciliation no complete valuation; manual actions and marks must not double
  count adjusted total-return histories. Only latest daily closing marks are used, never
  adjusted-history return plus separately credited dividends.

## Storage / Atomicity

`paper_experiments` stores one bounded aggregate per account: frozen settings and
append-only events (max 500, max 2 MiB). Each event binds sequence, previous hash,
request identity/hash, typed payload and server recording time. CAS on sequence commits
an event atomically; standalone Mongo multi-document transactions are not assumed.
A pure replay projector derives cash/FIFO lots/realized P&L/fees and verifies hash chains;
no mutable shadow ledger is authoritative. Request replays find the original event before
stale-sequence/closed checks. Changed inputs conflict; concurrent cash spending commits
at most the legal sequence. Failed provider/storage operations do not claim success.

Read/history/export/startup performs **no provider/model I/O and no trade mutation**.
Valuation only occurs on a user POST, captures the ledger sequence and current completed
session, fetches bounded provider inputs, then commits by CAS. Racing ledger changes
or a new completed session reject. The final Mongo CAS also caps validity at next XNYS
close using `$$NOW`; application prechecks alone are not enough. Schema, identity and
wire bounds are enforced; empty source account has no fabricated data.

## NAV / Offline Behavior

Current NAV = cash + Σ(quantity × contemporaneous USD close). A stored valuation is
complete only if every held symbol has a valid same-session mark and the reconciliation
is acknowledged. Missing/delisted/provider error stays **unavailable**, with per-symbol
reasons and marked-position coverage; missing assets never become zero-priced assets.
Stored values show their session/recording time and use current scenario quantities
at the last completed close, which can precede today's entries; no historical fills or
forward-performance interpretation is implied. New ledger events/session changes make
old receipts stale; they remain readable as last-known, not current NAV or zero risk.
Cash-only accounts value without a stock fetch. Unvalued bought positions do not earn
fictional gains. Profit summaries are explicitly conditional scenario accounting, not
investment-effectiveness, benchmark alpha, tax reporting or verified execution outcomes.

## API / UI

Local-action/no-store portfolio paper routes: list/create/detail, append trade/split/
dividend/close, explicit valuation refresh, and read-only manifest export. All journal
mutations carry expected sequence, request ID and manual-origin confirmation. API and UI
keep PAPER visible; all fields begin blank. UI separates this ledger from model decisions
and real Add Transaction. No button opening/selecting a paper account calls a model,
fetches fresh marks, imports holdings or submits a trade.

## Acceptance / Browser Scenarios

- Accounting golden: 10000 cash, BUY 10 @100 with 10bps slip/fee-bps 0 → principal 1001,
  cash 8999; mark 100 → NAV 9999. SELL @110 → 109.89/share, cash 10097.90 (no commissions).
  Independent commission/FIFO partial sell tests including exact residual depletion.
- Boundaries: strict numeric strings, nonfinite/bool/exponent/excess precision, overdraft,
  oversell, universe/extra authority, split fractions, dividend withholding and overflow.
- Same request replay 100 times → one event/fee; changed payload/stale seq conflicts.
  Concurrent 60%-cash BUYs → exactly one commit; provider/cancel/persistence failure never
  returns saved success. Replay after restart is identical without fresh I/O.
- Split 100 @10 → 200 @5, basis preserved; declared $1 dividend and mark drop $1 produce
  offsetting cash/market values (no double-counted income). Missing marks and stale receipts
  never become current complete NAV. Next actual XNYS close handles holidays/early closes.
- Browser real UI/API/Mongo + recorded outer market: create/manual BUY/refresh/SELL/export/
  reload; unavailable/stale marks; fractional FIFO/actions; concurrency and storage error.
  Assert real holdings/cash/transactions/review approvals unchanged. No mocked ledger results.
  Curated screenshots after assertions: `assets/idq-008-a/`.
- Full repository tests/types/lint/security/critical floors, repeat clean builds, final-image
  regressions, case study/indexes/version/changelogs, protected implementation then shipment
  PRs required before shipped. No live investment settings or paper account auto-created.

## Acceptance / Protected Publication

- Backend **2354 passed / 27 live integrations deselected**, aggregate **75.7785%**;
  strict mypy **352 files**, Black/Ruff/Bandit/eval and all original plus six new critical
  floors pass. Paper model/store/service/valuation/API coverage 100%, accounting 97.98%.
- Frontend **280 tests / 33 files**, production lint **0**, total lint warnings **131**,
  types/build pass. Nine script tests/six subtests remain passing. See
  [local receipt](assets/idq-008-a/local-validation.json).
- **51 final-image browser cases:** 5 paper + 9 review/model + 4 strategy + 3 evidence +
  3 risk + 6 safety + 4 Copilot + 6 hardening + 11 default. The paper tests use a recorded
  2026-09-17T12:00:00Z clock (last completed session 2026-09-16), not live account data.
  [Complete NAV screenshot](assets/idq-008-a/01-manual-paper-nav.png),
  [missing mark screenshot](assets/idq-008-a/02-unavailable-paper-nav.png).
- Two clean no-cache builds match full installed dependencies, source trees and frontend
  assets, runtime UID 1000, no local env or credentials:
  [build receipt](assets/idq-008-a/clean-build-validation.json).
- Journal/projection/manifest responses are byte-equivalent across actual backend/frontend
  recreation; startup/read does not fetch marks or call models:
  [persistence receipt](assets/idq-008-a/persistence-validation.json).
- Final review tested valuation arithmetic overflow, exact inclusive numeric range, FIFO
  residual depletion, concurrent identical replay, cancelled fetches and failed storage.
  Parent IDQ-008 remains incomplete; only this authorized manual slice is shipped.
- Implementation `c7333782a22d0e938f7ebe0bfd1b12d38b497677` merged through protected
  [PR #20](https://github.com/fhw12345/FinancialAgent/pull/20) as
  `70c90ffdeae5e6f702df86b1dc90678414ace544`. Hosted
  [run 37759803259](https://github.com/fhw12345/FinancialAgent/actions/runs/37759803259)
  passed every gate and eight browser lanes (40 cases). Downloaded archive digest and
  all eight embedded report stats/hashes match, no credentials:
  [hosted receipt](assets/idq-008-a/hosted-validation.json).
- Live **localhost:3013**, 0.60.0/0.41.0, uses accepted B images. Copilot login/default
  Astra/routing revision 1/private credential volume, the existing one real holding and
  all account/configuration hashes survive rollout. No paper experiment or personal
  investment policy is auto-created. Read-only browser verified blank creation inputs,
  consent required and no model/trade POSTs:
  [live receipt](assets/idq-008-a/live-validation.json).
- Main required `Unit Tests` (Actions app 15368), strict up-to-date and administrator
  enforcement remained unchanged; no bypass. No live inference or performance claim.

## Risks / Deferred

Manual reference prices and corporate actions permit subjective/counterfactual outcomes;
make this provenance prominent and never present them as unbiased investment validation.
User entry mistakes are retained, not editable. Budget exhaustion preserves history and
blocks new entries; archive creates no external cash flow. Broker identity, historical PIT,
benchmark evaluation, policy-approved experiment-bound execution, automatic corporate-action
capture and next-open/replay engines are out of this slice. PH-009 and IDQ-003 remain paused.
