---
title: Market Insights Trend Visualization
status: shipped
version: backend@0.30.x, frontend@0.23.x
last_updated: 2026-07-13
owner: maintainer
related_paths:
  - backend/src/api/insights/
  - backend/src/services/insights/
  - frontend/src/components/insights/
---

# Market Insights Trend Visualization

The Insights page displays the current AI-sector risk score, its component
metrics, and historical trends.

## Data Flow

1. `InsightsCategoryRegistry` calculates category metrics.
2. `InsightsSnapshotService` persists snapshots in MongoDB.
3. The latest snapshot is cached in Redis.
4. `/api/insights/{category_id}/trend` returns historical series.
5. The frontend renders sparklines and expanded charts.

Snapshots are created when the local refresh endpoint or the admin snapshot
endpoint is invoked:

```text
POST /api/insights/{category_id}/refresh
POST /api/admin/insights/trigger-snapshot
```

Snapshots are triggered explicitly by the local application.

## Components

| Component         | Location                                                  |
| ----------------- | --------------------------------------------------------- |
| Category registry | `backend/src/services/insights/registry.py`               |
| Snapshot service  | `backend/src/services/insights/snapshot_service.py`       |
| Trend API         | `backend/src/api/insights/endpoints.py`                   |
| Sparkline         | `frontend/src/components/insights/TrendSparkline.tsx`     |
| Expanded chart    | `frontend/src/components/insights/ExpandedTrendChart.tsx` |

## Storage

- MongoDB collection: `insight_snapshots`
- Redis latest-snapshot cache: `insights:{category_id}:latest`
- Trend windows supported by the UI: 30, 60, and 90 days

The current registry contains the `ai_sector_risk` category with seven
weighted metrics.
