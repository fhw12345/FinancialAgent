---
title: A Data Refetch Recreated the Entire Chart
status: shipped
version: frontend@0.30.0
last_updated: 2026-07-30
owner: maintainer
related_paths:
  - frontend/src/components/EnhancedChatInterface.tsx
  - frontend/src/components/TradingChart.tsx
  - frontend/src/components/chart/useChart.ts
  - frontend/src/components/chart/useChartData.ts
  - frontend/e2e/chart-volume-overlay.spec.ts
---

# A Data Refetch Recreated the Entire Chart

> **TL;DR (EN)**: The volume histogram looked correct, but changing the date
> range briefly removed query data and unmounted the chart. Browser evidence
> caught the recreated instance. Keeping same-symbol placeholder data mounted,
> updating both series atomically, and reading tooltip volume from the exact
> histogram point made the overlay stable and truthful.
>
> **TL;DR (中文)**：成交量柱看起来正确，但切换日期范围时 query data 会短暂消失，
> 导致整张图表被卸载重建。浏览器测试通过实例标记发现了这个生命周期问题。保留同一
> symbol 的旧数据、原子更新价格与成交量 series，并从准确的 histogram point 读取
> tooltip volume 后，overlay 才真正稳定且可信。

## 1. Context

The candlestick chart already received OHLCV bars, but only rendered price.
The task appeared to be a straightforward second Lightweight Charts series:

```text
OHLCV response -> candlestick series + volume histogram
```

The first implementation produced a visible histogram and replaced its data
when the response changed.

## 2. Investigation

Unit tests proved that price and volume timestamps were sorted together.
Playwright then added a chart-instance marker and changed both the selected
date range and interval.

The volume count changed correctly, but the instance marker also changed.
React Query used the range and interval in the query key, so a new key briefly
had no data. `ChartPanel` stopped rendering `TradingChart`, destroyed the chart,
and created a new one after the response arrived.

Review also found that tooltip volume used a map keyed only by calendar date.
Multiple intraday bars on the same day therefore overwrote one another.

## 3. Root Cause

The implementation synchronized data values but not lifecycle:

```text
query-key change
  -> data becomes temporarily unavailable
  -> chart unmounts
  -> old series are destroyed
  -> response mounts a new chart
```

Separately, date-only tooltip identity was weaker than the timestamp identity
used by the rendered series.

## 4. Fix

- Added the histogram on an independent hidden bottom scale.
- Built both series from one sorted list with identical converted `Time` values.
- Replaced price and volume data in one callback and cleared both together.
- Used same-symbol React Query placeholder data during range and interval
  refetches, while still discarding data when the symbol changes.
- Read tooltip volume directly from `MouseEventParams.seriesData` for the
  histogram series.
- Colored regular volume by candle direction and pre/post/closed bars by
  market session.
- Added Playwright assertions that bar counts change while the chart-instance
  marker remains stable.
- Saved curated screenshots for the initial and weekly views.

## 5. Lessons

- Correct pixels do not prove correct component lifecycle.
- Query-key transitions must preserve mounted visualization state explicitly.
- Related chart series should share one ordering and timestamp conversion path.
- Tooltip identity must be at least as precise as rendered data identity.
- Browser tests should assert both visible results and hidden lifecycle
  invariants that users experience as flicker or lost interaction state.
