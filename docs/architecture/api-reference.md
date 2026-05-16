---
title: API Reference
status: shipped
version: backend@0.29.x, frontend@n/a
last_updated: 2026-05-16
owner: maintainer
related_paths:
  - backend/src/api/
  - backend/src/main.py
---

# API Reference

All HTTP routes are mounted by `backend/src/main.py` and live under
`backend/src/api/`. The browser is the only HTTP client — there is no public
contract, so this page is a quick map of the surface, not a full OpenAPI clone.

**Source of truth** for live signatures, schemas, and example payloads:

```bash
# Docker compose dev only — the routes are not exposed in production builds
curl http://localhost:8000/openapi.json | jq

# Interactive Swagger UI
open http://localhost:8000/docs

# Interactive ReDoc
open http://localhost:8000/redoc
```

All endpoints require the placeholder `Authorization: Bearer local` header (the
fork removed auth; `require_admin` accepts the literal token). The frontend
attaches it automatically — see `frontend/src/services/api.ts`.

## 1. Router Map

| Prefix | Tag | File | Purpose |
|---|---|---|---|
| `/api` | health | `api/health.py` | liveness / readiness probes |
| `/api/admin` | admin | `api/admin.py` | dashboards, cache, LLM tool perf |
| `/api/admin/portfolio` | portfolio-admin | `api/portfolio_admin.py` | settings + trigger-analysis flows |
| `/api/analysis` | Financial Analysis | `api/analysis/` | on-demand analysis tools |
| `/api/chat` | chat | `api/chat/` | persistent chats + SSE streaming |
| `/api/portfolio` | portfolio | `api/portfolio/` | holdings, orders, transactions, decisions |
| `/api/market` | Market Data | `api/market/` | prices, quotes, search, status, fundamentals |
| `/api/watchlist` | watchlist | `api/watchlist.py` | watchlist CRUD + manual analyze |
| `/api/insights` | Market Insights | `api/insights/` | composite scores, trends, refresh |
| `/api/translate` | translate | `api/translate.py` | on-demand zh-CN translation |
| `/api/models` | llm_models | `api/llm_models.py` | LLM model list + pricing |

## 2. Endpoint Index

### `/api` — Health

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | overall app health |
| GET | `/api/health/mongodb` | mongo ping |
| GET | `/api/health/redis` | redis ping |
| GET | `/api/health/ready` | readiness probe (all deps) |
| GET | `/api/health/live` | liveness probe (no deps) |

### `/api/admin` — Admin

| Method | Path | Notes |
|---|---|---|
| GET | `/api/admin/health` | extended health w/ subsystem detail |
| GET | `/api/admin/database` | mongo collection stats |
| GET | `/api/admin/timing-metrics` | request latency histograms |
| POST | `/api/admin/insights/trigger-snapshot` | force a fresh insights snapshot |
| POST | `/api/admin/cache/warm` | warm Redis market cache |
| POST | `/api/admin/cache/warm-market-movers` | warm market movers panel |
| GET | `/api/admin/cache/warming-status` | last-warm timestamps |
| GET | `/api/admin/cache/stats` | redis hit/miss counters |
| GET | `/api/admin/llm/tool-performance` | per-tool latency + success rate |
| GET | `/api/admin/llm/slowest-tools` | top-N slow tool calls |
| GET | `/api/admin/llm/token-usage` | DashScope token totals |

### `/api/admin/portfolio` — Portfolio Admin

| Method | Path | Notes |
|---|---|---|
| GET | `/api/admin/portfolio/settings` | read portfolio config |
| PUT | `/api/admin/portfolio/settings` | update portfolio config |
| GET | `/api/admin/portfolio/universe/sectors` | sector universe used for picks |
| POST | `/api/admin/portfolio/trigger-analysis` | run Phase 1→2→3 pipeline |
| GET | `/api/admin/portfolio/status/{run_id}` | poll an analysis run |

### `/api/analysis` — Financial Analysis

| Method | Path | Notes |
|---|---|---|
| POST | `/api/analysis/fibonacci` | Fibonacci retracement levels |
| POST | `/api/analysis/macro` | macro / market regime sentiment |
| POST | `/api/analysis/fundamentals` | composite fundamentals |
| POST | `/api/analysis/company-overview` | company snapshot |
| POST | `/api/analysis/cash-flow` | cash-flow statement scoring |
| POST | `/api/analysis/balance-sheet` | balance-sheet scoring |
| POST | `/api/analysis/stochastic` | stochastic oscillator |
| POST | `/api/analysis/chart` | generate chart payload |
| POST | `/api/analysis/news-sentiment` | news sentiment for a symbol |
| GET | `/api/analysis/market-movers` | top movers across the universe |
| GET | `/api/analysis/history` | recent analysis runs |

### `/api/chat` — Chat

| Method | Path | Notes |
|---|---|---|
| POST | `/api/chat/chats` | create new chat |
| GET | `/api/chat/chats` | list chats |
| GET | `/api/chat/chats/{chat_id}` | full chat detail |
| DELETE | `/api/chat/chats/{chat_id}` | delete a chat |
| PATCH | `/api/chat/chats/{chat_id}/ui-state` | persist UI state blob |
| POST | `/api/chat/stream` | SSE stream — main agent loop |

### `/api/portfolio` — Portfolio

| Method | Path | Notes |
|---|---|---|
| GET | `/api/portfolio/holdings` | current positions |
| POST | `/api/portfolio/holdings` | add holding |
| PATCH | `/api/portfolio/holdings/{holding_id}` | update holding |
| DELETE | `/api/portfolio/holdings/{holding_id}` | remove holding |
| POST | `/api/portfolio/holdings/refresh-prices` | re-quote all holdings |
| GET | `/api/portfolio/summary` | aggregate metrics |
| GET | `/api/portfolio/transactions` | derived txn ledger |
| GET | `/api/portfolio/user-transactions` | manually entered txns |
| POST | `/api/portfolio/user-transactions` | record buy/sell |
| PATCH | `/api/portfolio/user-transactions/{id}` | edit manual txn |
| DELETE | `/api/portfolio/user-transactions/{id}` | delete manual txn |
| GET | `/api/portfolio/orders` | proposed-order history |
| POST | `/api/portfolio/orders` | submit/dry-run an order suggestion |
| GET | `/api/portfolio/decisions` | Phase 2 decision history |
| GET | `/api/portfolio/chat-history` | chats grouped per run |
| GET | `/api/portfolio/chats/{chat_id}` | one portfolio chat |
| DELETE | `/api/portfolio/chats/{chat_id}` | delete portfolio chat |

### `/api/market` — Market Data

| Method | Path | Notes |
|---|---|---|
| GET | `/api/market/price/{symbol}` | OHLCV time series |
| GET | `/api/market/quote/{symbol}` | latest quote + session marker |
| GET | `/api/market/search` | symbol autocomplete |
| GET | `/api/market/info/{symbol}` | full symbol metadata |
| GET | `/api/market/market-movers` | aggregated movers |
| GET | `/api/market/status` | exchange open/closed status |
| GET | `/api/market/overview/{symbol}` | fundamentals overview |
| GET | `/api/market/news-sentiment/{symbol}` | news sentiment shortcut |
| GET | `/api/market/cash-flow/{symbol}` | cash-flow shortcut |
| GET | `/api/market/balance-sheet/{symbol}` | balance-sheet shortcut |

### `/api/watchlist` — Watchlist

| Method | Path | Notes |
|---|---|---|
| GET | `/api/watchlist` | list tracked symbols |
| POST | `/api/watchlist` | add symbol |
| DELETE | `/api/watchlist/{watchlist_id}` | remove symbol |
| POST | `/api/watchlist/analyze` | trigger manual analyzer run |

### `/api/insights` — Market Insights

| Method | Path | Notes |
|---|---|---|
| GET | `/api/insights/categories` | list categories |
| GET | `/api/insights/{category_id}` | category snapshot |
| GET | `/api/insights/{category_id}/composite` | composite score |
| GET | `/api/insights/{category_id}/trend` | trend time series |
| GET | `/api/insights/{category_id}/{metric_id}` | one metric |
| POST | `/api/insights/{category_id}/refresh` | force recompute |

### `/api/translate` — Translate

| Method | Path | Notes |
|---|---|---|
| POST | `/api/translate` | translate a text block to zh-CN (Redis-cached) |

### `/api/models` — LLM Models

| Method | Path | Notes |
|---|---|---|
| GET | `/api/models` | available LLM models + pricing |

## 3. Authentication & CORS

- The fork strips real auth. `require_admin` accepts the fixed token `local`.
- CORS origins are read from `settings.cors_origins` (see
  `backend/src/core/config.py`). The dev default trusts
  `http://localhost:3000`.
- Rate limiting is enabled via SlowAPI (skipped in tests). See
  `backend/src/api/dependencies/rate_limit.py` for per-route limits.

## 4. SSE Streaming

`POST /api/chat/stream` returns `text/event-stream` events with the schema in
`backend/src/api/chat/streaming/helpers.py`. The frontend consumer is
`frontend/src/services/api.ts` (`streamChat`). Events include
`message`, `tool_call`, `tool_result`, `error`, and `done`. The agent loop
behind it is documented in
[`react-agent-integration.md`](react-agent-integration.md).

## 5. Cross-References

- High-level data flow: [`overview.md`](overview.md)
- Agent internals: [`react-agent-integration.md`](react-agent-integration.md),
  [`react-agent-debugging.md`](react-agent-debugging.md)
- Versioning: [`../project/versions/README.md`](../project/versions/README.md)
- FAQ: [`../FAQ.md`](../FAQ.md)
