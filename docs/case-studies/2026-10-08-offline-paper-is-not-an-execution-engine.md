---
title: Offline PAPER Is Not an Execution Engine / 离线模拟账本不是交易引擎
status: in-progress
version: backend@0.60.0, frontend@0.41.0
last_updated: 2026-10-08
owner: maintainer
related_paths:
  - backend/src/services/paper_ledger/
  - backend/src/models/paper_ledger.py
  - frontend/src/components/portfolio/paper/
---

# Offline PAPER Is Not an Execution Engine / 离线模拟账本不是交易引擎

> **TL;DR (EN):** A local tool that is frequently closed must not pretend it traded at
> the next open or monitored a stop. The first PAPER slice is a clearly manual scenario
> journal: exact FIFO accounting, user-declared prices/actions, on-demand valuation and
> immutable history. It neither consumes AI approvals nor mutates the real account.
>
> **TL;DR (中文)：** 经常关闭的本地工具不能假装在开盘成交或持续监控止损。首版是明确标注的
> 人工模拟情景账本：精确 FIFO 记账、人工价格／公司行动、按需估值与不可改写历史。
> 不消费 AI 批准，也不修改真实账户。

## 1. Context / 背景

The proposed IDQ-008 next-open engine assumed a future execution policy, experiment-bound
approvals and time-aware processing. The user explicitly said the service is not online
24h, then approved **manual paper bookkeeping + on-demand valuation**. Scope was split:
IDQ-008-A delivers the manual journal; approval-linked simulation remains future B.
A local_holdings approval is never an authorization for a different PAPER portfolio.

## 2. Investigation / 排查

The architectural boundary is not a cron expression. Decisions, approval, real actual-trade
bookkeeping and hypothetical PAPER entries have different authority and time semantics.
Opening the panel must not fetch marks or fabricate missing transactions. Later market
prices cannot be used to claim an earlier observed fill. A stale stored valuation is useful
only if its session and ledger revision remain visible.

Existing IDQ-002 closing-provider/calendar adapters supply outer market inputs. Their
adjusted return histories are not used for ledger P&L: crediting dividends separately and
using total-return history would double count income. Latest close valuation uses the
current hypothetical quantities; its session can precede today's manual entries, so it
must not be presented as a historical or independently validated forward return.

## 3. Root Cause / 根因

Most ledger errors cross representation or commit boundaries:

- Float quantity arithmetic leaves fractional dust and anonymous rounded basis residuals.
- Two requests checking the same cash then writing different documents can both spend it.
- A delayed valuation can publish against an obsolete portfolio or completed-session clock.
- A valid price × valid quantity can exceed the supported monetary range. If receipt
  calculation throws **after** the event commits, every later read may fail despite the
  account's journal itself being valid.

## 4. Fix / 修复

- Bounded decimal strings for inputs; cents ROUND_HALF_EVEN, six-decimal quantities,
  explicit directional slippage/commission and FIFO inclusive buy fees. Last-lot sale
  consumes exact remaining basis cents.
- One `paper_experiments` aggregate contains frozen creation settings and a hashed,
  append-only event sequence. Only sequence CAS makes an event visible. Pure replay is
  authoritative; no mutable shadow cash/holding collections or multi-document transactions.
- Provider work is outside the commit; ledger-sequence CAS and Mongo `$$NOW` before the
  next XNYS close guard publication. Read/startup/export performs no provider/model I/O.
- Unavailable prices and valuation arithmetic overflow produce a durable **unavailable**
  receipt with reasons, never zero-price positions or a broken account read.
- Corporate actions are explicitly user-declared reconciliation, not inferred entitlements.
  Closing an incorrect scenario retains history; no edit/delete/backdated repair exists.
- Parallel identical requests reuse their single committed event. Independent competing
  requests conflict rather than overdraft or append duplicate fees.

公司行动及价格属于人工情景假设，不证明真实市场发生了该成交／分红。缺价和金额越界
保持无法估值；当前数量按最近收盘价重估也不冒充过去时点的收益。

## 5. Verification / 验证

Pure accounting oracles cover buy/sell, FIFO fees and cent residuals, fractional shares,
splits/dividends, strict numeric inputs and no borrowing. Lifecycle tests cover 100 replays,
competing cash requests, delayed storage clocks, corruption, provider/storage/cancellation
failures and no I/O on reads. Real browser scenarios traverse UI/API/Mongo with only outer
market receipts and explicit storage/clock faults recorded. The real account/review and
model-call audit stays unchanged. Local acceptance passes **2354 backend / 280 frontend
 tests**, all critical/strict gates, **51 final-image cases**, repeat equal-source/dependency/
asset builds and real recreation without fresh provider/model calls. Hosted publication
is pending; current evidence is linked in
[the feature](../features/investment-manual-paper-ledger.md).

Tests prove specified accounting and failure behavior, not that chosen prices are unbiased,
company actions verified, a strategy profitable or a model calibrated. Service downtime is
normal; restarting reconstructs history, not trades missed while offline.
