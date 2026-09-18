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

## Research Safety

Stage A records **non-actionable research assessments**, not approved BUY/SELL
recommendations. Daily-close risk and user-confirmed allocation **previews** are
available; full investment policy, point-in-time evidence, strategy and approval
integration remain pending. No result can be `ready` or approved. Legacy decisions remain readable but cannot be
marked executed. Use **Add Transaction** independently to record trades you actually
made. On Portfolio, use **Refresh risk** to capture daily-close risk and explicitly
confirm your own **Risk preview policy** limits; old model-size hints are not policy.
Cash is your declared account balance, not an automatic settlement ledger.
The **Research mandate** panel offers the approved fundamental pilot (252 XNYS sessions,
SPY total return, USD US non-financial equities). Confirm costs and supply your own
assumptions/peers before using an immutable version for future research; configuration
never calls a model. PE/DCF outputs are conditional model estimates, not verified fair
values or execution prices. Short-term experiments remain disabled.

Research assessments also expose **Research evidence** dossiers: inspect exact values,
units, periods and sources. “Fields match” means agreement with sealed records, not
proof of source truth or the investment conclusion. Unknown publication/PIT remains unknown.
See [evidence boundaries](docs/features/investment-evidence-snapshots.md),
[risk definitions](docs/features/investment-portfolio-risk-allocation.md) and [the Stage-A boundary](docs/features/investment-decision-safety-containment.md).

## LLM Provider

Set `LLM_PROVIDER` in `backend/.env.development`:

| Value             | Backend                                                              |
| ----------------- | -------------------------------------------------------------------- |
| `maestro`         | Agent Maestro at `MAESTRO_BASE_URL`                                  |
| `anthropic`       | Direct Anthropic API using `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` |
| `copilot_reverse` | GitHub Copilot through the sibling `../copilot-bridge` repository    |
| `github_copilot`  | Native Python OAuth + GPT/Gemini/Grok; default and role models configured on Health |

Native Copilot needs no pi process, bridge, or OpenAI/Anthropic API key. Set
`LLM_PROVIDER=github_copilot`, recreate backend, then open **Health → GitHub Copilot**.
Authorize on GitHub, refresh the permitted model list, select a default model,
and explicitly test the connection (uses Copilot allowance). GPT/Grok use Responses;
Gemini uses Chat Completions. MAI, hidden entries and unsupported
protocols are excluded. Enterprise Server login is not supported; account model
permissions still apply.

Expand **Role-based model routing** to assign models to research, news, adversarial
review, translation and final decisions. Empty overrides inherit the default.
The multi-vendor suggestion is a draft until explicitly saved; existing runs retain
their snapshot. See [role routing](docs/features/copilot-multivendor-role-routing.md)
for the role map, compatibility boundaries and recorded/live validation.

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
