---
title: FAQ
status: shipped
version: backend@0.29.x, frontend@0.22.x
last_updated: 2026-05-16
owner: maintainer
related_paths:
  - docs/development/getting-started.md
  - docs/architecture/overview.md
---

# Frequently Asked Questions

Quick answers to the issues that come up most often when running Financial
Agent locally. For first-time setup, start with
[`development/getting-started.md`](development/getting-started.md).

## Setup & Runtime

### 1. Do I need `docker compose`, or can I run things with a Python virtualenv?

Use **docker compose**. The backend assumes MongoDB and Redis are reachable on
the compose network. Running `uvicorn` directly works for unit-tests, but
integration tests and the agent loop expect the stack from
`docker-compose.yml`. Frontend dev server (`vite`) does run fine outside a
container — but most contributors run it inside the `frontend` service so
HMR pathing stays consistent with the backend's CORS origins.

### 2. I edited `.env` and `docker compose restart` didn't pick up the change.

`restart` reuses the existing container env. Use:

```bash
docker compose up -d --force-recreate backend
```

`docker compose up -d --build` works too if you also changed code. The
`Makefile`'s `make dev` always calls `up -d` so it picks up new env values.

### 3. Port 3000 / 8000 / 27017 / 6379 is already in use.

Edit `docker-compose.yml` and remap the host port, e.g.
`"3001:3000"` for the frontend. The internal service-to-service ports never
change; only the left side of the colon (host) matters. Update
`VITE_API_BASE_URL` and `cors_origins` accordingly.

## Data & APIs

### 4. yfinance returns 429 or is extremely slow.

yfinance is a fallback, not the primary. Set `FINNHUB_API_KEY` and
`ALPHAVANTAGE_API_KEY` in `.env` and recreate the backend — `DataManager` will
route the quote and history paths through them first. Cached responses
(Redis) cover most repeat reads anyway. See
[`features/extended-hours-trading-data.md`](features/extended-hours-trading-data.md)
for the full provider fallback chain.

### 5. Chinese translations are missing or appear as English in the UI.

The write-time translation pipeline only fires when DashScope is reachable.
If `DASHSCOPE_API_KEY` is empty, fields are stored English-only and the
frontend renders them as-is. Check
[`features/write-time-translation.md`](features/write-time-translation.md)
and the case study
[`case-studies/2026-05-05-translation-pipeline-multilayer.md`](case-studies/2026-05-05-translation-pipeline-multilayer.md).

### 6. SEC EDGAR Form 4 links 404 unpredictably.

EDGAR re-issues accession URLs; we resolve them lazily and cache the result.
The full root-cause + fix is documented in
[`case-studies/2026-05-09-sec-edgar-form4-url-resolution.md`](case-studies/2026-05-09-sec-edgar-form4-url-resolution.md).

## Agent & Portfolio

### 7. What's the Portfolio Phase 1 / 2 / 3 split actually doing?

- **Phase 1** — one independent Deep ReAct research pass *per symbol*. No
  portfolio context yet, so the result is reusable across rebalances.
- **Phase 2** — single LLM call that consumes all Phase 1 outputs and emits a
  `List[TradingDecision]` with full portfolio visibility (sizing, sector
  caps, cash use).
- **Phase 3** — order executor sorts SELLs before BUYs to free up liquidity,
  then writes proposed orders to MongoDB. Nothing leaves the box.

See [`features/portfolio-agent-architecture-refactor.md`](features/portfolio-agent-architecture-refactor.md).

### 8. How do I add a new agent skill?

A skill is a directory under `backend/src/agent/skills/<domain>/<skill>/`
containing a `SKILL.md` and the implementation that registers tools with the
ReAct agent. Add the skill to
[`backend/src/agent/skills/README.md`](../backend/src/agent/skills/README.md)
so the capability matrix stays accurate, and wire it into
`langgraph_react_agent.py` if it should be loaded by default. The skill
contract is described in [`architecture/agent-architecture.md`](architecture/agent-architecture.md).

### 9. How do I add a new external data provider?

Add a service class under `backend/src/services/`, wire it into
`DataManager` (`backend/src/services/data_manager.py`) inside the existing
fallback chain, and add the API key to `.env.example` + `core/config.py`
(`Settings`). The chat agent does **not** call providers directly; it goes
through `DataManager` so caching and graceful degradation come for free.

## Versioning & Tests

### 10. Why are backend and frontend versioned separately?

We deploy them as separate containers under compose and want to be able to
patch one without bumping the other. The pre-commit hook
(`scripts/validate-version.sh`) enforces that at least one component's
version increments per commit. Details in
[`project/versions/README.md`](project/versions/README.md).

### 11. Why must tests run inside the container?

Two reasons: (1) the `backend` image bakes the Python deps and tools
expected by `pytest` (Motor, redis-py, structlog), and (2) the tests resolve
MongoDB/Redis at `mongodb:27017` / `redis:6379` — the compose hostnames.
Use:

```bash
docker compose exec backend pytest
docker compose exec frontend npm test
```

`make test` runs both.

### 12. Where do I document a bug I just spent two hours on?

Write a new case study under `docs/case-studies/` using the template at the
top of [`case-studies/README.md`](case-studies/README.md). The pattern:
context → reasoning → root cause → fix → takeaways. Bilingual TL;DR after
the H1. This is how we keep institutional knowledge from disappearing into
git history.
