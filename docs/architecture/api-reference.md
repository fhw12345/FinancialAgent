---
title: API Reference
status: shipped
version: backend@0.30.x, frontend@n/a
last_updated: 2026-07-13
owner: maintainer
related_paths:
  - backend/src/api/
  - backend/src/main.py
---

# API Reference

The local API has no authentication layer. OpenAPI is the source of truth:

```bash
curl http://localhost:8000/openapi.json
```

Interactive documentation is available at <http://localhost:8000/docs>.

## Router Map

| Prefix                 | Purpose                                              |
| ---------------------- | ---------------------------------------------------- |
| `/api/health`          | application, MongoDB, and Redis health               |
| `/api/admin`           | local metrics, cache controls, and insight snapshots |
| `/api/admin/portfolio` | portfolio settings and analysis runs                 |
| `/api/analysis`        | deterministic financial analysis                     |
| `/api/chat`            | persistent chats and SSE streaming                   |
| `/api/portfolio`       | holdings, transactions, decisions, and suggestions   |
| `/api/market`          | quotes, prices, search, status, and fundamentals     |
| `/api/watchlist`       | watchlist CRUD and analysis                          |
| `/api/insights`        | insight categories, metrics, and trends              |
| `/api/translate`       | cached Simplified Chinese translation                |

## Important Endpoints

### Health and Administration

| Method | Path                                   |
| ------ | -------------------------------------- |
| GET    | `/api/health`                          |
| GET    | `/api/health/mongodb`                  |
| GET    | `/api/health/redis`                    |
| GET    | `/api/admin/health`                    |
| GET    | `/api/admin/database`                  |
| GET    | `/api/admin/timing-metrics`            |
| GET    | `/api/admin/cache/stats`               |
| POST   | `/api/admin/cache/warm`                |
| POST   | `/api/admin/insights/trigger-snapshot` |

### Chat

| Method | Path                                 |
| ------ | ------------------------------------ |
| POST   | `/api/chat/chats`                    |
| GET    | `/api/chat/chats`                    |
| GET    | `/api/chat/chats/{chat_id}`          |
| PATCH  | `/api/chat/chats/{chat_id}/ui-state` |
| DELETE | `/api/chat/chats/{chat_id}`          |
| POST   | `/api/chat/stream`                   |

`POST /api/chat/stream` returns `text/event-stream` events for text chunks,
tool execution, deep-agent progress, errors, and completion.

### Portfolio

| Method       | Path                                     |
| ------------ | ---------------------------------------- |
| GET/POST     | `/api/portfolio/holdings`                |
| PATCH/DELETE | `/api/portfolio/holdings/{holding_id}`   |
| GET          | `/api/portfolio/summary`                 |
| POST         | `/api/portfolio/holdings/refresh-prices` |
| GET          | `/api/portfolio/orders`                  |
| GET          | `/api/portfolio/decisions`               |
| GET/POST     | `/api/portfolio/user-transactions`       |
| POST         | `/api/admin/portfolio/trigger-analysis`  |
| GET          | `/api/admin/portfolio/status/{run_id}`   |

### Market and Analysis

| Method | Path                             |
| ------ | -------------------------------- |
| GET    | `/api/market/search`             |
| GET    | `/api/market/info/{symbol}`      |
| GET    | `/api/market/price/{symbol}`     |
| GET    | `/api/market/quote/{symbol}`     |
| GET    | `/api/market/status`             |
| POST   | `/api/analysis/fibonacci`        |
| POST   | `/api/analysis/stochastic`       |
| POST   | `/api/analysis/macro`            |
| POST   | `/api/analysis/company-overview` |
| POST   | `/api/analysis/news-sentiment`   |

### Insights

| Method | Path                                      |
| ------ | ----------------------------------------- |
| GET    | `/api/insights/categories`                |
| GET    | `/api/insights/{category_id}`             |
| GET    | `/api/insights/{category_id}/trend`       |
| GET    | `/api/insights/{category_id}/{metric_id}` |
| POST   | `/api/insights/{category_id}/refresh`     |

See [Architecture Overview](overview.md) for the request and agent data flows.
