# Financial Agent

Personal AI-powered financial analysis tool. Runs locally via Docker Compose.

## Quick Start

```bash
cp .env.example .env          # then fill in your API keys
docker compose up
```

Open http://localhost:3000.

Required keys in `.env`:

- `QWEN_API_KEY` — Alibaba DashScope (Qwen) for the LLM agent
- `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` — market data
- `FRED_API_KEY` — macro / liquidity metrics (free)
- `EXA_API_KEY` — web search for the debater agent
- `POLYGON_API_KEY` — extended-hours data (optional)

## Features

- **Chat** — conversational financial analysis with streaming LLM responses and tool use
- **Market Insights** — daily snapshots of price anomaly, sentiment, smart money flow,
  put/call ratio, IPO heat, liquidity, Fed expectations; with sparklines and trend charts
- **Technical Analysis** — Fibonacci retracement, stochastic oscillator, market structure
- **Portfolio** — watchlist + AI-generated trade suggestions (no auto-trading)

## Development

```bash
make dev          # start docker compose
make test         # run backend + frontend tests
make fmt && make lint
docker compose logs -f backend
```

Frontend commands run inside the container:
`docker compose exec frontend npm <cmd>`.

See `CONTRIBUTING.md` and `CLAUDE.md` for the development workflow.
