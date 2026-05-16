---
title: Market Insights Trend Visualization
status: shipped
version: backend@0.9.0, frontend@0.11.4
last_updated: 2025-12-30
owner: maintainer
related_paths:
  - backend/src/api/insights/
  - frontend/src/components/MarketInsights/
---

# Market Insights Trend Visualization

## Overview

Phase 2 of Market Insights adds historical trend visualization capabilities to the AI Sector Risk analysis. This enables users to track how risk metrics evolve over time through sparklines and expanded trend charts.

## Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Daily Snapshot Workflow                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  CronJob (14:30 UTC)                                            │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────────┐    ┌─────────────────┐                     │
│  │ DataManager     │───▶│ Alpha Vantage   │                     │
│  │ prefetch_shared │    │ APIs            │                     │
│  └────────┬────────┘    └─────────────────┘                     │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │ InsightsRegistry│                                            │
│  │ get_category    │                                            │
│  └────────┬────────┘                                            │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐    ┌─────────────────┐                     │
│  │ MongoDB         │    │ Redis Cache     │                     │
│  │ (Persist)       │    │ (24hr TTL)      │                     │
│  └─────────────────┘    └─────────────────┘                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| DataManager | `backend/src/services/data_manager/` | Batch data pre-fetching with deduplication |
| SnapshotService | `backend/src/services/insights/snapshot_service.py` | Creates and persists daily snapshots |
| Trend API | `backend/src/api/insights/endpoints.py` | Serves historical trend data |
| TrendSparkline | `frontend/src/components/insights/TrendSparkline.tsx` | Mini chart for collapsed metrics |
| ExpandedTrendChart | `frontend/src/components/insights/ExpandedTrendChart.tsx` | Full chart for expanded view |

## Features

### 1. Daily Automated Snapshots

- **CronJob**: `insights-snapshot-trigger` runs at 01:00 UTC (9:00 AM Beijing/CST) daily
- **Storage**: MongoDB `insight_snapshots` collection with compound index on `(category_id, date)`
- **Cache**: Redis key `insights:{category_id}:full` with 24hr TTL (populated by CronJob, instant page load)

### 2. Trend API Endpoint

```
GET /api/insights/{category_id}/trend?days=30
```

Returns:
```json
{
  "category_id": "ai_sector_risk",
  "days": 30,
  "data_points": 5,
  "trend": [
    {"date": "2025-12-28", "score": 56.1},
    {"date": "2025-12-27", "score": 54.2}
  ],
  "metrics": {
    "ai_price_anomaly": [
      {"date": "2025-12-28", "score": 67.0},
      {"date": "2025-12-27", "score": 65.5}
    ]
  }
}
```

### 3. Frontend Visualization

**TrendSparkline** (collapsed view):
- Shows last 7-30 days as mini line chart
- Single data point displays as centered blue dot
- Width: 100px, Height: 20px

**ExpandedTrendChart** (expanded view):
- Full SVG chart with axes and tooltips
- Supports 30/60/90 day ranges
- Color-coded by trend direction (green=up, red=down, gray=flat)

### 4. CompositeScoreCard Trend

- Shows trend chart when >1 data point available
- Dark theme variant for header card
- Displays "Risk Over Time" label

## Snapshot Trigger

Snapshots are produced on demand via the admin API:

```bash
curl -X POST http://localhost:8000/api/admin/insights/trigger-snapshot \
  -H "Authorization: Bearer $TOKEN"
```

## Configuration

### Backend Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `INSIGHTS_SNAPSHOT_TTL` | 86400 | Redis cache TTL in seconds |
| `INSIGHTS_PREFETCH_SYMBOLS` | NVDA,MSFT,AMD,PLTR | Symbols for AI sector analysis |

### Frontend Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `TREND_DAYS_OPTIONS` | [30, 60, 90] | Available trend periods |
| `SPARKLINE_WIDTH` | 100 | Sparkline width in pixels |
| `SPARKLINE_HEIGHT` | 20 | Sparkline height in pixels |

## Testing

### Unit Tests
```bash
cd backend && pytest tests/test_insights_snapshot.py -v
cd backend && pytest tests/test_insights_trend_api.py -v
```

### E2E Scenarios
Located in `.harshJudge/scenarios/`:
- `insights-sparkline-single-point` - Single data point displays as dot
- `insights-trend-multi-day` - Multi-day trend line displays
- `insights-composite-chart` - Composite card trend chart

## Related Documentation

- [Market Insights Epic](../epics/market-insights-epic.md) - Full epic with all phases
- [Story 2.1 - DataManager](../stories/2.1.story.md) - Data caching layer
- [Performance Baselines](../performance/README.md) - API response times

## Changelog

### v0.11.4 (2025-12-28)
- Phase 2 complete: Trend visualization deployed
- TrendSparkline handles single data point as blue dot
- ExpandedTrendChart with interactive tooltips
- CronJob `insights-snapshot-trigger` active
