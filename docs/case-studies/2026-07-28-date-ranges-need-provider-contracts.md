---
title: Date Ranges Need Provider Contracts
status: shipped
version: backend@0.49.0, frontend@0.29.0
last_updated: 2026-07-28
owner: maintainer
related_paths:
  - frontend/src/components/chart/DateRangePicker.tsx
  - frontend/src/utils/dateRangeCalculator.ts
  - backend/src/services/data_manager/manager.py
  - backend/src/services/market_data/yfinance_bars.py
  - backend/src/services/market_data/bars_extended.py
---

# Date Ranges Need Provider Contracts

> **TL;DR (EN)**: Adding two date inputs was not enough. Provider history
> limits, cache identity, exchange timezones, analyzer granularity, empty-range
> behavior, overlays, and persisted UI state all had to share one explicit
> contract.
>
> **TL;DR (中文)**：增加两个日期输入框远远不够。Provider 历史窗口、cache
> identity、交易所时区、分析周期、空范围行为、图表 overlay 和持久化 UI
> state 都必须遵守同一个明确契约。

## 1. Context

The frontend already stored `selectedDateRange`, and the backend request models
already exposed `start_date` and `end_date`. The missing picker therefore
looked like a small UI task.

The first browser implementation proved that price and technical-analysis
requests could receive the same range, but review showed that the underlying
providers and caches could still return different data.

## 2. Investigation

The investigation found several hidden mismatches:

- the chart query deliberately ignored the selected dates;
- one-minute Yahoo data required multiple seven-day requests;
- default daily post-processing truncated explicit five-year ranges;
- an empty intraday range silently returned unrelated recent bars;
- `1mo` analysis requests fell back to daily granularity;
- Stochastic compact data could not satisfy long explicit ranges;
- cache keys did not distinguish compact, full, or different ranges;
- UTC or New York boundaries could drop international exchange dates;
- newly created and legacy chats could lose their applied range.

## 3. Root Cause

The date range existed as a field, not as an end-to-end contract. Each layer
interpreted it independently:

```text
picker -> chart request -> provider window -> cache -> analyzer -> overlay
       -> chat metadata -> UI-state restoration
```

Any layer that ignored, truncated, reinterpreted, or replaced the range made
the displayed summary dishonest.

## 4. Fix

- Added a draft/apply/reset picker with validated presets.
- Used symbol suffixes to resolve supported exchange calendar timezones.
- Rejected partial ranges instead of silently ignoring one side.
- Passed explicit dates through chart, DataManager, provider, Fibonacci, and
  Stochastic calls.
- Chunked one-minute yfinance requests and removed unrelated-data fallback.
- Bypassed default caps for explicit ranges.
- Added output-size and range dimensions to cache keys and invalidation.
- Matched overlays by symbol, interval, start date, and end date.
- Persisted the latest UI state when a new chat ID is created, with retry.
- Added browser evidence for request parity, analysis persistence, UI state,
  and recovery from empty ranges.

## 5. Lessons

- A UI filter is only truthful when every downstream layer honors it.
- Explicit user ranges must never degrade into unrelated default data.
- Cache identity is part of API correctness.
- Calendar dates should follow the instrument's exchange, not the server or
  browser timezone.
- Browser evidence should verify both network payloads and durable restored
  state.
