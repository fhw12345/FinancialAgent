---
title: Watchlist Analysis Persistence Wiring
status: in-progress
version: backend@0.35.0, frontend@0.25.3
last_updated: 2026-07-17
owner: maintainer
related_paths:
  - backend/src/api/watchlist.py
  - backend/src/api/dependencies/watchlist_deps.py
  - backend/src/database/repositories/watchlist_repository.py
  - frontend/src/hooks/useWatchlist.ts
  - frontend/src/components/portfolio/WatchlistPanel.tsx
  - frontend/e2e/uaw-004-watchlist-persistence.spec.ts
---

# UAW-004: Watchlist Analysis Persistence Wiring

## Implementation Record

The implementation and validation are complete in the current working tree.
The feature remains `in-progress` until the change set is committed.

Delivered:

- canonical `WATCHLIST_COLLECTION` and FastAPI repository dependency;
- atomic symbol-based timestamp update without the old 200-row scan limit;
- millisecond-normalized timestamp returned exactly as persisted by MongoDB;
- explicit `watchlist_updated` and `last_analyzed_at` response metadata;
- persistence failures surfaced instead of logged as cosmetic success;
- immediate React Query cache update followed by an awaited Mongo refetch;
- stable browser selectors for the portfolio watchlist flow;
- real-Mongo Playwright proof with the refetch deliberately blocked;
- browser reload proof that the timestamp survives in MongoDB;
- dedicated E2E app that replaces only expensive portfolio execution and
  disables external quote/cache warming calls.

Validation summary:

```text
UAW-004 backend tests: 12 passed
Backend full regression suite: 1794 passed, 27 deselected
Backend Ruff: passed
Changed backend modules isolated mypy: passed
Frontend targeted tests: 13 passed
Frontend full tests: 216 passed
Frontend lint/type-check/build: passed
Playwright watchlist persistence scenario: 1 passed
```

### Screenshot Evidence

| Evidence | Scenario | Stack | Commit | Result |
| --- | --- | --- | --- | --- |
| [Immediate timestamp update](assets/uaw-004/01-last-analyzed-updated.png) | Mutation response updates the row while Mongo refetch is blocked | Real frontend/backend/MongoDB + deterministic portfolio flow | pending | PASS |
| [Timestamp after reload](assets/uaw-004/02-timestamp-persists-after-reload.png) | Reload reads the same timestamp from MongoDB | Real frontend/backend/MongoDB + deterministic portfolio flow | pending | PASS |

## 1. Task Summary

Make the per-row Watchlist **Analyze Now** action update the same MongoDB
document read by the Watchlist dashboard.

The completed request must:

- persist the single-symbol portfolio decision;
- atomically update `watchlist.last_analyzed_at` when the symbol is watched;
- return the persisted timestamp to the frontend;
- update the visible row immediately;
- retain the timestamp after a browser reload;
- surface persistence failures instead of reporting success.

This is the fourth correctness task from the
[Unified Agent Workflow Improvement Roadmap](../architecture/unified-agent-workflow-roadmap.md).

## 2. Current Problem

Watchlist CRUD, startup indexes, the portfolio agent, and the dashboard all use:

```text
watchlist
```

The per-row single-symbol analysis path instead constructs:

```python
WatchlistRepository(mongo.get_collection("watchlist_items"))
```

That collection does not contain the row displayed by the dashboard.

The timestamp update is also wrapped in a broad exception handler:

```python
except Exception:
    logger.warning("watchlist_stamp_failed")
```

The endpoint therefore returns `analysis_completed` after the decision is
persisted even when `last_analyzed_at` was never written.

Existing tests replace `WatchlistRepository` with a mock. They verify that
`update_last_analyzed()` was called, but never observe which MongoDB collection
was selected.

## 3. Root Cause

Collection ownership is encoded as repeated string literals instead of one
repository dependency.

The API contract also treats the timestamp as cosmetic, while the dashboard
uses it as the user-visible proof that analysis completed.

## 4. Goal

Introduce one watchlist repository factory and make successful per-row
analysis return a persistence acknowledgement:

```json
{
  "status": "analysis_completed",
  "symbol": "AAPL",
  "result_count": 1,
  "run_id": "single_abc123",
  "watchlist_updated": true,
  "last_analyzed_at": "2026-07-17T05:30:00Z"
}
```

An ad-hoc symbol that is not watched may still complete with:

```json
{
  "watchlist_updated": false,
  "last_analyzed_at": null
}
```

If a watched row exists but MongoDB cannot update it, the endpoint must fail.

## 5. Non-Goals

UAW-004 does not:

- migrate the batch watchlist analyzer to the unified portfolio flow;
- activate the dormant five-minute scheduler;
- redesign portfolio decisions;
- add multi-user watchlists;
- change quote enrichment behavior;
- make the analysis request asynchronous;
- add background task cancellation.

## 6. Repository Contract

Define one collection constant:

```python
WATCHLIST_COLLECTION = "watchlist"
```

Define one FastAPI dependency:

```python
def get_watchlist_repository(
    mongodb: MongoDB = Depends(get_mongodb),
) -> WatchlistRepository:
    return WatchlistRepository(
        mongodb.get_collection(WATCHLIST_COLLECTION)
    )
```

All API paths should receive or construct the repository through this contract.

The repository adds symbol-oriented operations:

```python
get_by_symbol(symbol)
mark_analyzed_by_symbol(symbol, timestamp)
```

The update must use one MongoDB `update_one` call and return the exact timestamp
written to the document.

## 7. Backend Flow

```text
POST /api/watchlist/analyze?symbol=AAPL
  -> run_single_symbol()
  -> verify result_count > 0
  -> mark watchlist row analyzed in "watchlist"
  -> return timestamp acknowledgement
```

Failure semantics:

- analysis failure: return the existing failed analysis result;
- symbol not present in watchlist: successful analysis with
  `watchlist_updated=false`;
- Mongo read/update failure: HTTP 500;
- matched watchlist row but failed update: HTTP 500.

The API must not catch a persistence exception and reshape it as success.

## 8. Frontend Flow

The mutation response updates React Query cache immediately:

```text
analysis response
  -> setQueryData(watchlistKeys.list())
  -> row renders returned last_analyzed_at
  -> invalidateQueries()
  -> Mongo-authoritative refetch confirms the value
```

`mutateAsync()` must not resolve before the invalidation/refetch promise is
registered.

Stable browser selectors are added for:

- portfolio navigation;
- watchlist panel;
- one watchlist row;
- per-row analyze button;
- visible `last_analyzed_at` state.

## 9. Tests

### Repository Unit Tests

- `get_by_symbol()` normalizes ticker case;
- `mark_analyzed_by_symbol()` writes the expected query and timestamp;
- missing symbols return `None`;
- database errors propagate.

### Endpoint Integration Tests

- the real dependency requests the `watchlist` collection;
- a successful watched-symbol analysis updates the row;
- a non-watchlisted symbol does not create a watchlist row;
- persistence exceptions return HTTP 500;
- a collection mismatch fails the test.

### Frontend Tests

- analysis response shape includes persistence metadata;
- successful response updates the cached row timestamp;
- failed analysis does not produce a success-shaped cache update;
- invalidation is awaited.

## 10. Playwright E2E

Use a dedicated deterministic single-symbol flow while preserving:

```text
React UI
  -> FastAPI watchlist endpoint
  -> WatchlistRepository
  -> real MongoDB
  -> response cache update
  -> React Query refetch
```

Only expensive portfolio model execution is replaced.

### Scenario

1. Seed one `AAPL` row in the real `watchlist` collection with
   `last_analyzed_at=null`.
2. Open the Portfolio dashboard.
3. Assert the row shows “waiting for first analysis.”
4. Delay the post-analysis GET refetch.
5. Click the row's **Analyze Now** button.
6. Assert the timestamp appears from the mutation response before the delayed
   refetch finishes.
7. Reload the browser.
8. Assert the same row still has a persisted timestamp.

### Screenshot Evidence

```text
docs/features/assets/uaw-004/
  01-last-analyzed-updated.png
  02-timestamp-persists-after-reload.png
```

## 11. Validation

```bash
cd backend
python -m pytest \
  tests/test_watchlist_repository.py \
  tests/test_watchlist_analyze_endpoint.py

make test-e2e-uaw004
make test
make lint
```

## 12. Acceptance Criteria

- [x] One collection constant or repository factory owns watchlist access.
- [x] Per-row analysis writes `watchlist.last_analyzed_at`.
- [x] The API returns the exact persisted timestamp.
- [x] A non-watchlisted symbol remains a valid ad-hoc analysis.
- [x] Persistence errors do not return `analysis_completed`.
- [x] The frontend updates the row immediately from the mutation result.
- [x] React Query refetch confirms MongoDB state.
- [x] Reload preserves the timestamp.
- [x] Integration coverage observes the actual collection name.
- [x] Playwright passes against real MongoDB.
- [x] Two screenshot artifacts are linked.
- [x] Version and changelog documentation are updated.

## 13. Risks

| Risk | Mitigation |
| --- | --- |
| Analysis succeeds but timestamp fails | Treat persistence failure as endpoint failure |
| Cache shows a value Mongo never stored | Return only the repository timestamp, then refetch |
| Ad-hoc analysis is mistaken for a missing row error | Return `watchlist_updated=false` when no row exists |
| Tests mock away collection selection | Exercise the real dependency with a recording Mongo object |
| Live quote vendors make E2E flaky | Replace quote enrichment only in the test app |

## 14. Follow-Up

After UAW-004:

1. Agent-task cancellation.
2. Honest streaming semantics.
3. Unified run contracts.
4. Durable Research Job checkpoints.
