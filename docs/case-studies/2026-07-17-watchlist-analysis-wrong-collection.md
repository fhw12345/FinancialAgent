---
title: Watchlist Analysis Updated the Wrong Collection
status: shipped
version: backend@0.35.0, frontend@0.25.3
last_updated: 2026-07-17
owner: maintainer
related_paths:
  - backend/src/api/watchlist.py
  - backend/src/database/repositories/watchlist_repository.py
  - frontend/src/hooks/useWatchlist.ts
  - frontend/e2e/uaw-004-watchlist-persistence.spec.ts
---

# Watchlist Analysis Updated the Wrong Collection

> **TL;DR (EN)**: Per-row watchlist analysis successfully persisted its
> investment decision, then attempted to update `last_analyzed_at` in the
> nonexistent `watchlist_items` collection. A broad exception handler hid the
> mismatch, so the API reported success while the dashboard remained stale.
> We centralized repository creation, returned the persisted timestamp, and
> proved immediate UI update plus reload persistence against real MongoDB.
>
> **TL;DR (中文)**：逐行 Watchlist 分析已经成功保存投资决策，却把
> `last_analyzed_at` 写入了不存在的 `watchlist_items` collection。宽泛异常捕获
> 隐藏了错误，导致 API 报成功但 dashboard 时间不更新。修复后统一 repository
> 创建，返回真实持久化时间戳，并通过真实 MongoDB 验证即时 UI 更新和 reload
> 后持久化。

## 1. Context

The Watchlist dashboard exposes an **Analyze Now** button per symbol.

The expensive single-symbol portfolio flow completed and wrote a structured
decision to `portfolio_orders`, but the row continued to display:

```text
Waiting for first analysis
```

Refreshing the browser did not help.

## 2. Investigation

Watchlist CRUD and startup indexes consistently used:

```text
watchlist
```

The single-symbol completion path used:

```python
WatchlistRepository(
    mongo.get_collection("watchlist_items")
)
```

Its tests replaced `WatchlistRepository` with a mock, so they verified a method
call without observing the collection name.

The code also loaded up to 200 rows and searched for the symbol in Python. Even
with the correct collection, a row beyond that limit would never be updated.

Finally, the complete stamp block was wrapped in:

```python
except Exception:
    logger.warning("watchlist_stamp_failed")
```

The endpoint therefore returned `analysis_completed` after a failed write.

## 3. Root Cause

Collection ownership was represented by repeated string literals instead of
one repository dependency.

The endpoint also treated `last_analyzed_at` as cosmetic metadata, while the
frontend treated it as the visible proof of completion.

Mock boundaries hid both assumptions.

## 4. Fix

The backend now:

- defines `WATCHLIST_COLLECTION = "watchlist"`;
- injects one canonical `WatchlistRepository`;
- updates by normalized symbol with one atomic `update_one`;
- uses `matched_count` to distinguish a missing row from a successful match;
- normalizes timestamps to BSON millisecond precision;
- returns `watchlist_updated` and the exact timestamp written;
- surfaces MongoDB write failures as endpoint failures.

The frontend now:

- writes the response timestamp into React Query cache immediately;
- awaits invalidation so MongoDB remains authoritative;
- rejects `analysis_failed` responses;
- exposes stable selectors for browser verification.

The Playwright test blocks the post-analysis GET request. The visible timestamp
must update before that refetch is released, proving the mutation response
drives the immediate UI. After releasing the refetch and reloading the browser,
the timestamp must still exist.

## 5. Lessons

### Mock the expensive boundary, not the persistence boundary

Replacing the portfolio model flow is safe for this test. Replacing the
repository would erase the behavior being verified.

### Collection names are part of the contract

A repository method mock cannot prove that the repository points at the right
collection. Integration tests must observe dependency construction.

### User-visible metadata is not cosmetic

If the dashboard uses a field to communicate success, failure to persist that
field cannot be silently downgraded to a warning.

### Return what the database can store

MongoDB stores datetimes at millisecond precision. Returning a microsecond
value that cannot survive a reload creates a subtle cache-versus-database
mismatch.

### Avoid application-side scans for keyed updates

The old 200-row scan was slower and incomplete. A symbol-indexed `update_one`
is both simpler and correct for arbitrarily long watchlists.
