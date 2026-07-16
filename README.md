# Financial Agent

Personal AI-assisted financial research and portfolio tracking tool. It runs
locally with Docker Compose and never submits broker orders.

## Start

1. Copy `backend/.env.example` to `backend/.env.development`.
2. Configure the Agent Maestro endpoint and any optional market-data keys.
3. Start the stack:

```bash
docker compose up -d
```

Open <http://localhost:3000>. The backend API and OpenAPI docs are available at
<http://localhost:8000> and <http://localhost:8000/docs>.

## LLM Provider

Set `LLM_PROVIDER` in `backend/.env.development`:

| Value             | Backend                                                              |
| ----------------- | -------------------------------------------------------------------- |
| `maestro`         | Agent Maestro at `MAESTRO_BASE_URL`                                  |
| `anthropic`       | Direct Anthropic API using `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` |
| `copilot_reverse` | GitHub Copilot through the sibling `../copilot-bridge` repository    |

For the Copilot reverse mode, start the bridge first:

```powershell
make copilot-reverse
```

Then configure:

```env
LLM_PROVIDER=copilot_reverse
COPILOT_REVERSE_BASE_URL=http://localhost:8765/cc
COPILOT_REVERSE_AUTH_TOKEN=dummy
```

When the Financial Agent backend itself runs in Docker, use
`http://host.docker.internal:8765/cc`; Compose already supplies this URL.

## What It Provides

- Streaming chat with automatic routing across simple, ReAct, and deep
  multi-agent flows
- Deterministic Fibonacci, stochastic, fundamentals, macro, and news analysis
- Local holdings, watchlist, transactions, decisions, and order suggestions
- Portfolio-wide research and structured decision generation
- AI-sector risk insights with historical trends
- English and Simplified Chinese UI/output support

## Stack

| Layer    | Technology                                              |
| -------- | ------------------------------------------------------- |
| Frontend | React 18, TypeScript, Vite, TailwindCSS, TanStack Query |
| Backend  | Python 3.12, FastAPI, Motor, redis-py                   |
| Agents   | LangChain, LangGraph, DeepAgents, Agent Maestro         |
| Storage  | MongoDB and Redis                                       |
| Runtime  | Docker Compose                                          |

Market data uses yfinance by default, with optional Finnhub, Alpha Vantage,
FRED, Exa, and SEC EDGAR integrations.

## Development

```bash
make dev
make test
make fmt
make lint
docker compose logs -f backend
```

Frontend commands run inside the container:

```bash
docker compose exec frontend npm <command>
```

See [docs/README.md](docs/README.md) for architecture, API, development, and
feature documentation.
