---
title: Getting Started
status: shipped
version: n/a
last_updated: 2026-09-09
owner: maintainer
related_paths:
  - docker-compose.yml
  - Makefile
  - backend/.env.example
  - backend/src/main.py
  - frontend/package.json
---

# Getting Started

## Prerequisites

- Docker Compose
- Git
- Agent Maestro running on the host

Python 3.12 and Node 20 are only required when running services outside
containers.

## Configure

```bash
git clone <repository>
cd FinancialAgent
cp backend/.env.example backend/.env.development
```

Select one LLM backend with `LLM_PROVIDER`.

### Agent Maestro

```env
MAESTRO_BASE_URL=http://host.docker.internal:23333/api/anthropic
MAESTRO_AUTH_TOKEN=Powered by Agent Maestro
```

### Direct Anthropic

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=<YOUR_KEY>
ANTHROPIC_MODEL=<VALID_ANTHROPIC_MODEL_ID>
```

### GitHub Copilot Reverse Proxy

The sibling repository is named `copilot-bridge`, while the Financial Agent
flag is `copilot_reverse`.

```powershell
make copilot-reverse
```

For a locally running backend:

```env
LLM_PROVIDER=copilot_reverse
COPILOT_REVERSE_BASE_URL=http://localhost:8765/cc
COPILOT_REVERSE_AUTH_TOKEN=dummy
```

For a Docker backend, use `host.docker.internal` instead of `localhost`.

yfinance works without a key. Optional integrations include Finnhub, Alpha
Vantage, FRED, and Exa.

## Start

```bash
docker compose up -d
```

- Frontend: <http://localhost:3000>
- Backend: <http://localhost:8000>
- OpenAPI: <http://localhost:8000/docs>

Check health:

```bash
curl http://localhost:8000/api/health
```

After changing an environment file, recreate the affected service:

```bash
docker compose up -d --force-recreate backend
```

`docker compose restart` does not reload environment variables.

## Local Network Boundary and Remote Opt-in

Every default published port (including E2E profiles) binds to `127.0.0.1`.
Containers still communicate using service names on their Docker network.
CORS is not authentication and does not protect database ports.

Remote access is not enabled by the default configuration. Prefer an authenticated
SSH tunnel to the existing loopback ports. Any LAN deployment requires a separate,
explicit Compose override plus authenticated ingress and a network-security
review. Replace the selected application port mappings rather than appending a
second wildcard mapping; never expose MongoDB or Redis to the LAN. Simply changing
`127.0.0.1` to `0.0.0.0` is not a safe remote-access configuration.

Validate the full default port configuration with:

```bash
python scripts/check-compose-loopback.py
```

The checker renders every profile without resolving local secret env files.
On Windows, start the engine with `docker desktop start` and confirm `docker info`
before bringing services up. Stop on a failed `docker compose up`; do not keep
polling an endpoint when its container never started.

## Development Commands

```bash
make dev
make fmt
make test
make lint
docker compose logs -f backend
docker compose exec frontend npm <command>
```

## Run Outside Docker

Start MongoDB and Redis first:

```bash
docker compose up -d mongodb redis
```

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

When switching providers or endpoints, fully restart the backend so the cached
settings and compiled agents are rebuilt.

## Project Structure

```text
backend/src/
  api/          FastAPI routes and schemas
  agent/        ReAct, deep-agent, and portfolio pipelines
  services/     Business logic and data providers
  database/     MongoDB and Redis access
  models/       Domain models

frontend/src/
  components/   UI and feature components
  hooks/        TanStack Query and UI hooks
  services/     HTTP/SSE clients
  pages/        Main application tabs
```

## Next Steps

- [Architecture Overview](../architecture/overview.md)
- [Coding Standards](coding-standards.md)
- [Agent 12-Factors](../architecture/agent-12-factors.md)
- [Feature Index](../features/README.md)
