---
title: Insights Shared Prefetch Contract Repair
status: in-progress
version: backend@0.51.1, frontend@0.32.1
last_updated: 2026-08-06
owner: maintainer
related_paths:
  - backend/src/services/insights/snapshot_service.py
  - backend/src/services/data_manager/manager.py
  - backend/tests/test_insights_snapshot.py
  - frontend/src/pages/InsightsPage.tsx
---

# PH-002: Insights Shared Prefetch Contract Repair

## Objective

Repair the `InsightsSnapshotService` to `DataManager.prefetch_shared` contract
and prove that one refresh prefetches AI basket, Treasury, news, and IPO inputs
without a swallowed programming error.

## Root Cause and Contract

The caller passes `indicators=`, while DataManager accepts
`treasury_maturities=`. The resulting `TypeError` is caught as a partial data
failure and converted to `{}`.

Required contract:

```python
await data_manager.prefetch_shared(
    symbols=["NVDA", "MSFT", "AMD", "PLTR"],
    treasury_maturities=["2y", "10y"],
    include_news=True,
    include_ipo=True,
)
```

Programming errors such as unexpected keyword arguments must not be classified
as provider degradation.

## Ownership and Dependencies

Agent B owns snapshot prefetch code and focused tests. Coordinate any DataManager
signature change with Agents C and G. Do not restructure the large modules;
PH-009 handles that later.

## Implementation Plan

1. Replace the invalid keyword and remove the unused `indicators` abstraction.
2. Separate expected provider/data failures from programming failures.
3. Preserve partial provider degradation through `SharedDataContext.errors`.
4. Add structured logs for requested inputs, successful categories, and errors.
5. Add an integration-style contract test using the real method signature.
6. Verify snapshot persistence and frontend refresh behavior.

## Test Plan

### Unit tests

- exact symbols and Treasury maturities are requested;
- empty provider results remain valid;
- one provider error is represented in `SharedDataContext.errors`;
- a `TypeError` caused by code misuse is not silently returned as `{}`.

### Integration tests

Use a real `DataManager` with fake provider adapters and Redis. Assert each
logical source is fetched once and the resulting snapshot contains a composite,
metrics, and timing metadata.

### Playwright E2E — required

Scenario `ph-002-insights-refresh`:

1. Start the deterministic backend fixture with recorded provider responses.
2. Open the Insights page.
3. Trigger snapshot refresh through the visible UI.
4. Assert loading state, completion state, metric cards, and composite score.
5. Assert the fixture recorded one shared prefetch with `2y` and `10y`.
6. Capture `docs/features/assets/ph-002/01-shared-prefetch-refresh.png`.

Add a second deterministic provider-partial-failure scenario if the UI exposes
stale/degraded status; otherwise cover it at API integration level.

## Acceptance Criteria

- [ ] No invalid keyword is passed to DataManager.
- [ ] Shared prefetch executes rather than returning an empty fallback.
- [ ] Provider failures and programming failures have different handling.
- [ ] Contract, integration, and browser tests pass.
- [ ] Curated screenshot and tested commit are recorded.
- [ ] Backend and frontend full gates pass.

## Implementation and Test Record

The snapshot service now calls `treasury_maturities=["2y", "10y"]`, exposes
provider errors from `SharedDataContext`, and no longer converts programming
`TypeError` failures into empty data. Targeted backend tests passed, including
exact awaited arguments and a programming-error regression.

The deterministic Playwright scenario `insights refresh completes through the
visible UI` asserted category metrics, refresh HTTP success, and the composite
interpretation before capturing
[`assets/ph-002/01-shared-prefetch-refresh.png`](assets/ph-002/01-shared-prefetch-refresh.png).
It used deterministic network fixtures; the backend contract is proven by the
focused Python test. The tested implementation commit is `960d29a`.

## Risks

Live providers are nondeterministic. Browser acceptance must use deterministic
recorded responses; one optional manual real-provider smoke may supplement but
never replace assertions.
