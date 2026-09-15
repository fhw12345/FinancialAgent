# Financial Agent

Personal AI-assisted financial research and portfolio tracking tool. It runs
locally with Docker Compose and never submits broker orders.

## Start

1. Copy `backend/.env.example` to `backend/.env.development`.
2. Choose an LLM provider below and configure any optional market-data keys.
3. Start the stack:

```bash
docker compose up -d
```

Open <http://localhost:3000>. The backend API and OpenAPI docs are available at
<http://localhost:8000> and <http://localhost:8000/docs>.

All published Compose ports bind to `127.0.0.1` by default. MongoDB, Redis, and
the unauthenticated local API must not be exposed to a LAN. Remote access
requires an explicit Compose override plus an appropriate authentication and
network-security review; changing the bindings to `0.0.0.0` alone is unsafe.
See [remote-access opt-in guidance](docs/development/getting-started.md#local-network-boundary-and-remote-opt-in).

## LLM Provider

Set `LLM_PROVIDER` in `backend/.env.development`:

| Value             | Backend                                                              |
| ----------------- | -------------------------------------------------------------------- |
| `maestro`         | Agent Maestro at `MAESTRO_BASE_URL`                                  |
| `anthropic`       | Direct Anthropic API using `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` |
| `copilot_reverse` | GitHub Copilot through the sibling `../copilot-bridge` repository    |
| `github_copilot`  | Native Python OAuth + GPT Responses; sign in and select a model on Health |

Native Copilot needs no pi process, bridge, or OpenAI/Anthropic API key. Set
`LLM_PROVIDER=github_copilot`, recreate backend, then open **Health → GitHub Copilot**.
Authorize on GitHub, refresh the permitted model list, select a GPT Responses model,
and explicitly test the connection (uses Copilot allowance). The selected model is
used for all roles; native v1 does not support Claude/Gemini transports or Enterprise
Server login. Account entitlement and model policies still apply.

Credentials stay in a private local Docker volume, separate from pi and GitHub CLI.
Local logout does not revoke the GitHub grant. See the
[native provider specification](docs/features/native-github-copilot-provider.md)
for isolated ports, security limits, and recorded/live verification boundaries.

After changing local env configuration, use
`docker compose up -d --force-recreate backend`; a restart alone does not reload it.

For the existing Copilot reverse mode, start the bridge first:

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
