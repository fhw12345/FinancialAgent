---
title: Getting Started
status: shipped
version: n/a
last_updated: 2026-05-16
owner: maintainer
related_paths:
  - docker-compose.yml
  - Makefile
  - backend/src/main.py
  - frontend/package.json
---

# Getting Started - Financial Agent Development

> Personal single-user local fork. Cloud / K8s / multi-user auth have been
> removed. Everything runs in `docker compose`.

## Prerequisites

- **Docker & Docker Compose**
- **Git**
- (Optional, only if you run services outside Docker) Python 3.12+, Node 20+

## 1. Clone & Start

```bash
git clone <repository>
cd financial_agent
make dev                       # docker compose up — backend, frontend, mongo, redis
```

Access:

- Frontend: <http://localhost:3000>
- Backend API: <http://localhost:8000>
- API Docs: <http://localhost:8000/docs>

Verify:

```bash
curl http://localhost:8000/api/health | python3 -m json.tool
```

Expected:

```json
{
  "status": "ok",
  "dependencies": {
    "mongodb": {"connected": true},
    "redis": {"connected": true}
  }
}
```

After changing any `.env*` file:

```bash
docker compose up -d --force-recreate <service>   # restart does NOT reload env
```

## 2. Optional: Run Services Outside Docker

Only needed if you want hot reload outside the container.

**Backend**:

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -e ".[dev]"
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend**:

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

Manual setup still needs Mongo + Redis:

```bash
docker compose up -d mongodb redis
```

## Common Commands

```bash
make fmt        # Format
make lint       # Lint
make test       # Run all tests
docker compose logs -f backend
docker compose exec frontend npm <cmd>
```

Bump version (required by pre-commit hook):

```bash
./scripts/bump-version.sh backend  patch     # 0.1.0 → 0.1.1
./scripts/bump-version.sh frontend minor
```

## Project Structure

```
financial_agent/
├── backend/                 # FastAPI backend
│   └── src/
│       ├── api/             # REST API endpoints
│       ├── core/            # Configuration, utilities, analysis
│       ├── database/        # MongoDB / Redis
│       ├── services/        # Business logic
│       └── main.py
├── frontend/                # React + Vite + TS
│   └── src/
│       ├── components/
│       ├── services/        # API clients
│       └── ...
├── docs/
├── scripts/
├── docker-compose.yml
├── Makefile
└── README.md
```

## Tech Stack

| Layer    | Stack                                            |
| -------- | ------------------------------------------------ |
| Backend  | Python 3.12 + FastAPI + MongoDB + Redis          |
| Frontend | React 18 + TypeScript 5 + Vite + TailwindCSS     |
| AI / LLM | LangChain + LangGraph + Alibaba DashScope (Qwen) |
| Runtime  | Docker Compose (local only)                      |

## Common Tasks

**Add a backend endpoint**: create in `backend/src/api/`, add tests in
`backend/tests/api/`, update the matching client in `frontend/src/services/`,
then `make fmt && make test && make lint`.

**Add a React component**: create in `frontend/src/components/`, add types in
`frontend/src/types/`, write a Vitest test, run quality gates.

**Add a database model**: Pydantic model in `backend/src/models/`, ops in
`backend/src/database/repositories/`, mirror types in the frontend if it
crosses the API boundary.

## Environment

Backend env vars live in `.env` (gitignored). Frontend dev URL can be set in
`frontend/.env.local`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

## Troubleshooting

**Port conflicts**:

```bash
lsof -i :3000  :8000  :27017  :6379
```

**Backend not reloading**: function/route edits hot-reload; new deps or
module-level changes require restart.

**Env vars not taking effect**: `docker compose restart` does NOT reload env —
use `up -d --force-recreate <service>`.

## Next Steps

- [Coding Standards](coding-standards.md)
- [Agent Architecture](../architecture/agent-architecture.md)
- [12-Factor Agent Guide](../architecture/agent-12-factors.md)
- [Feature Specifications](../features/README.md)
