---
title: Insights Shared Prefetch Contract Repair
status: in-progress
version: backend@0.51.5, frontend@0.32.5
last_updated: 2026-09-09
owner: maintainer
related_paths:
  - backend/src/services/insights/snapshot_service.py
  - backend/src/services/insights/snapshot_inputs.py
  - backend/src/services/data_manager/cache.py
  - backend/src/api/insights/endpoints.py
  - backend/tests/test_snapshot_refresh_integration.py
  - frontend/e2e/insights-prefetch.spec.ts
---

# PH-002: Insights Shared Prefetch Contract Repair

## Scope and Root Cause

The original snapshot caller used `indicators=` instead of
`treasury_maturities=`. Commit `960d29a` repaired that signature, but closeout
review found that the visible refresh still called the registry directly and
never consumed snapshot prefetch. The old UI-mocked screenshot was not proof of
the backend integration.

The continuation connects the actual refresh endpoint to snapshot creation.
Local acceptance is now verified; status remains `in-progress` pending hosted
CI and the publication workflow.

## Contract

1. Resolve the dynamic AI basket once per snapshot. Prefetch all its symbols,
   Treasury `2y`/`10y`, technology news and IPO inputs with the real DataManager
   orchestrator. The four-symbol browser fixture is not a production basket limit.
2. Snapshot price metrics request full daily history, not the compact default;
   the 200-day SMA must receive enough data.
3. A request-local category/provider view converts those exact typed inputs to
   the existing calculator shapes. Singleton category providers are never mutated.
   Treasury and daily rows are presented in chronological order.
4. Unshared intraday/options/liquidity capabilities retain existing behavior.
   Provider-cache TTLs still apply; Refresh is not a global network-cache purge.
5. Persist the snapshot before returning successful refresh. Programming or
   persistence errors cannot become successful empty results.
6. Preserve partial provider failures by source. Public/cache `prefetch_errors`
   contain generic unavailable messages, not raw provider URLs or credentials;
   affected metrics retain explicit placeholder metadata.
7. Cache dedup failure must not trigger a second provider call. A cache transport
   failure before fetching can fall back; a failed cache write/unlock after a
   successful fetch returns that result. A swallowed provider failure is re-raised.
   An unconfigured optional Redis cache still permits a direct fetch.

## Implementation

- `snapshot_inputs.py` delegates full-history reads to the existing DataManager
  and creates a private prepared AI category for each run.
- `InsightsSnapshotService` uses that plan for prefetch and calculation, then
  persists the score, metrics, and sanitized degradation metadata.
- The visible refresh route invokes this snapshot service, and startup binds it
  to the same registry used by the admin snapshot path, independently of LLM
  initialization success.
- `CacheOperations` tracks callback completion/errors so Redis dedup fallback
  cannot repeat or hide provider failure. The real Redis orchestration in the
  composition test reproduced this bug before the fix.

## Tests and Browser Evidence

Targeted suites:

- `test_snapshot_prefetch_composition.py`: real signature, requested inputs,
  provider degradation and cache reuse;
- `test_snapshot_refresh_integration.py`: real Snapshot/AI calculators/DataManager/
  Redis dedup orchestration with fake external storage/provider transports,
  persistence failure, sanitized errors, and concurrent provider-view isolation;
- `test_cache_prefetch_failures.py`: failure/retry, swallowed error, post-success
  cache failure, optional Redis and programming-error controls;
- `test_insights_api.py`: visible route calls snapshot, 404, persistence failure,
  and explicit degradation response.

Playwright `visible Insights refresh consumes one shared prefetch` uses real
application routes, MongoDB, Redis and metric calculators with recorded market
providers. An explicit fixture barrier proves the loading/disabled state; no
arbitrary sleep is used. After release it asserts:

- one shared prefetch, with both `2y` and `10y`;
- one request per shared OHLCV/Treasury/news/IPO input;
- full history requested for all four fixture symbols;
- seven persisted metrics and matching API/UI composite score;
- refresh completion before screenshot capture.

[Real integrated refresh screenshot](assets/ph-002/01-shared-prefetch-refresh.png)
replaces the old UI-mocked evidence. The mocked rendering regression remains in
the suite but no longer writes this screenshot.

The final tree passed backend **2,014 tests** (27 live integrations deselected),
Ruff/Black/mypy, critical coverage, frontend **254 tests**, lint/types/build,
deterministic eval, **6 fresh-image smoke tests** and **11 default E2E tests**.
See [build receipts](assets/ph-004/clean-build-validation.json) for the two clean
builds and actual installed dependency/output comparisons. Browser acceptance ran
without application-source/dependency bind mounts.

Tested tree: `ddf4284` plus the closeout implementation pending commit.

## Acceptance Criteria

- [x] No invalid keyword is passed to DataManager.
- [x] Shared prefetch executes and its output feeds metric calculation.
- [x] Provider/cache failures are not silently retried into false success.
- [x] Contract, composition, API and real browser tests pass.
- [x] Curated screenshot and final image receipts are captured.
- [x] Backend and frontend local quality gates pass.
- [ ] Implementation hash, hosted CI and publication are recorded.

## Risks

- Live market providers remain nondeterministic; CI uses recorded responses.
- A same-date snapshot is an upsert, not an append-only per-run history. Concurrent
  completion order determines the last value; request-local inputs prevent mixing.
- MongoDB and Redis are not a cross-store transaction. A persistence failure is
  explicit and never reported as a successful refresh; category cache freshness
  and durable trend history are separate until the write succeeds.
- Broad source decomposition remains PH-009; this change does not split the
  oversized DataManager or AI metric implementations.
