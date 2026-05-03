# Financial Agent - Product Requirements Document

> **Document Type**: Brownfield PRD (Living Document)
> **Last Updated**: 2025-12-20
> **Backend Version**: v0.8.8 | **Frontend Version**: v0.11.4
> **Status**: Production (http://localhost:3000)

---

## Executive Summary

**Financial Agent** is an AI-Enhanced Financial Analysis Platform that provides on-demand technical analysis (Fibonacci, Stochastic, Market Structure) for financial symbols. The platform combines chart visualization with AI-powered interpretations using a cloud-native architecture deployed on Alibaba Cloud (ACK).

### Product Vision

Transform sophisticated CLI financial analysis tools into a modern, conversational AI-powered web application that enables retail investors to perform professional-grade technical analysis through natural language.

### Target Users

| User Type | Description | Primary Use Cases |
|-----------|-------------|-------------------|
| **Retail Investors** | Individual traders seeking technical analysis | Fibonacci analysis, market sentiment, portfolio tracking |
| **Active Traders** | Day/swing traders needing quick analysis | Real-time quotes, stochastic analysis, market movers |
| **Financial Enthusiasts** | Learning technical analysis | AI explanations, educational insights |

---

## Current Capabilities

### Core Features (Production)

| Feature | Status | Description |
|---------|--------|-------------|
| **Conversational AI Chat** | Live | Natural language financial queries with LangGraph ReAct agent |
| **Fibonacci Analysis** | Live | Retracement levels with confidence scoring |
| **Stochastic Analysis** | Live | K%/D% oscillator with overbought/oversold detection |
| **Market Structure** | Live | Swing point detection and trend analysis |
| **Macro Sentiment** | Live | VIX, sector rotation, market indices |
| **News Sentiment** | Live | Real-time news with sentiment scoring |
| **Market Movers** | Live | Top gainers/losers with volume analysis |
| **Portfolio Tracking** | Live | Holdings management with P&L |
| **Watchlist** | Live | Symbol tracking with automated analysis |
| **Credit System** | Live | Token-based economy (1 RMB = 100 credits) |
| **Feedback Platform** | Live | User feedback with voting and comments |
| **Multi-language (i18n)** | Live | English/Chinese support |

### Data Sources

| Provider | Purpose | Rate Limit |
|----------|---------|------------|
| **Alpha Vantage** | Real-time quotes, fundamentals, news | 75 calls/min (Premium) |
| **Alpaca Markets** | Paper trading, historical data | Standard limits |
| **Alibaba DashScope** | LLM inference (Qwen models) | Pay-per-token |

---

## Technical Architecture Summary

> **Detailed Documentation**: See [System Design](architecture/system-design.md) for complete architecture.

### Technology Stack

| Layer | Technology | Version |
|-------|------------|---------|
| **Backend** | Python + FastAPI | 3.12 + 0.104 |
| **Frontend** | React + TypeScript + Vite | 18 + 5 + 5 |
| **Database** | Azure Cosmos DB (MongoDB API) | 4.2 |
| **Cache** | Redis | 7.2 |
| **AI/LLM** | LangGraph + Qwen (DashScope) | 0.2 + Latest |
| **Observability** | Langfuse (self-hosted) | 3.x |
| **Container** | Docker + Kubernetes (ACK) | Latest |
| **CI/CD** | GitHub Actions | Automated |

### Deployment Environments

| Environment | Platform | URL | Status |
|-------------|----------|-----|--------|
| **Local Dev** | Docker Compose | http://localhost:3000 | Active |
| **Production** | Alibaba ACK (Shanghai) | http://localhost:3000 | Active |
| **Test** | Azure AKS | http://localhost:3000 | Planned |

### Key Architectural Decisions

1. **Hybrid Cloud**: Azure (ACR, Key Vault, Cosmos DB) + Alibaba (ACK, OSS, DashScope)
2. **12-Factor Agent**: LangGraph ReAct pattern with stateless design
3. **Separate Pods**: Independent scaling for frontend/backend/Redis
4. **External Secrets**: Azure Key Vault -> K8s via External Secrets Operator

---

## Source Code Organization

### Repository Structure

```
financial_agent/
├── backend/                    # Python FastAPI backend
│   ├── src/
│   │   ├── api/               # REST API endpoints (modular)
│   │   │   ├── analysis/      # Technical analysis endpoints
│   │   │   ├── chat/          # Chat/conversation endpoints
│   │   │   ├── feedback/      # Feedback platform
│   │   │   ├── market/        # Market data endpoints
│   │   │   ├── portfolio/     # Portfolio management
│   │   │   ├── schemas/       # Pydantic request/response models
│   │   │   └── dependencies/  # Dependency injection
│   │   ├── agent/             # LangGraph ReAct agent
│   │   │   ├── tools/         # LangChain tools (Alpha Vantage, etc.)
│   │   │   ├── optimizer/     # Order optimization
│   │   │   ├── portfolio/     # Portfolio analysis agent
│   │   │   └── callbacks/     # Streaming callbacks
│   │   ├── core/              # Core utilities
│   │   │   ├── analysis/      # Technical analysis (Fibonacci, etc.)
│   │   │   ├── data/          # Data fetching services
│   │   │   └── utils/         # Shared utilities
│   │   ├── database/          # MongoDB/Redis connections
│   │   │   └── repositories/  # Data access layer
│   │   ├── models/            # Pydantic domain models
│   │   ├── services/          # Business logic services
│   │   └── workers/           # Background workers
│   ├── tests/                 # Pytest tests
│   └── pyproject.toml         # Python project config
│
├── frontend/                   # React TypeScript frontend
│   ├── src/
│   │   ├── components/        # React components
│   │   │   ├── auth/          # Authentication UI
│   │   │   ├── chart/         # TradingView charts
│   │   │   ├── chat/          # Chat interface
│   │   │   ├── feedback/      # Feedback platform
│   │   │   ├── portfolio/     # Portfolio dashboard
│   │   │   └── credits/       # Credit balance
│   │   ├── hooks/             # Custom React hooks
│   │   ├── pages/             # Page components
│   │   ├── services/          # API client services
│   │   ├── types/             # TypeScript types
│   │   └── utils/             # Utility functions
│   ├── public/locales/        # i18n translations
│   └── package.json           # Node.js dependencies
│
├── .pipeline/                  # CI/CD and K8s configs
│   ├── k8s/                   # Kubernetes manifests
│   │   ├── base/              # Base resources
│   │   └── overlays/          # Environment patches
│   └── scripts/               # Deployment scripts
│
├── .github/workflows/          # GitHub Actions
│   ├── pr-checks.yml          # PR validation
│   └── deploy.yml             # Production deployment
│
├── docs/                       # Documentation
│   ├── architecture/          # System design docs
│   ├── deployment/            # Deployment guides
│   ├── development/           # Dev guides
│   ├── features/              # Feature specifications
│   ├── testing/               # E2E testing guides
│   └── troubleshooting/       # Issue resolution
│
└── scripts/                    # Utility scripts
    └── bump-version.sh        # Version management
```

### Key Entry Points

| Purpose | File | Description |
|---------|------|-------------|
| **Backend Main** | `backend/src/main.py` | FastAPI app initialization |
| **Frontend Main** | `frontend/src/main.tsx` | React app entry |
| **App Config** | `backend/src/core/config.py` | Pydantic settings |
| **ReAct Agent** | `backend/src/agent/langgraph_react_agent.py` | LangGraph agent |
| **Docker Compose** | `docker-compose.yml` | Local development |

---

## API Structure

### Backend API Endpoints

| Router | Prefix | Purpose |
|--------|--------|---------|
| `health` | `/api/health` | Health checks, readiness probes |
| `auth` | `/api/auth` | Login, registration, password reset |
| `chat` | `/api/chat` | Conversations, streaming chat |
| `analysis` | `/api/analysis` | Fibonacci, Stochastic, Macro |
| `market_data` | `/api/market` | Quotes, search, price history |
| `portfolio` | `/api/portfolio` | Holdings, transactions, summary |
| `watchlist` | `/api/watchlist` | Symbol tracking, analysis |
| `credits` | `/api/credits` | Balance, transactions, pricing |
| `feedback` | `/api/feedback` | Feedback items, votes, comments |
| `admin` | `/api/admin` | Admin-only monitoring |
| `llm_models` | `/api/llm-models` | Model selection, pricing |

### Key API Flows

1. **Chat Flow**: `POST /api/chat/stream-react` -> SSE streaming response
2. **Analysis Flow**: `POST /api/analysis/{type}` -> Synchronous analysis
3. **Portfolio Flow**: `GET /api/portfolio/summary` -> User holdings
4. **Auth Flow**: `POST /api/auth/login` -> JWT token pair

---

## Database Collections

> **Detailed Schema**: See [Database Schema](architecture/database-schema.md)

| Collection | Purpose | Key Fields |
|------------|---------|------------|
| `users` | User accounts | user_id, email, credits |
| `chats` | Chat conversations | chat_id, user_id, ui_state |
| `messages` | Chat messages | message_id, chat_id, content |
| `credit_transactions` | Credit accounting | transaction_id, amount |
| `refresh_tokens` | JWT refresh tokens | token_hash, expires_at |
| `feedback` | User feedback | feedback_id, votes |
| `holdings` | Portfolio positions | symbol, quantity, cost_basis |
| `watchlist` | Tracked symbols | symbol, alerts |
| `portfolio_orders` | Order audit trail | order_id, status |
| `tool_executions` | Tool usage tracking | tool_name, tokens |

---

## External Integrations

### LLM Integration (Qwen via DashScope)

```
Application -> LangGraph Agent -> Qwen-Plus/Max/Turbo
                    ↓
              Tool Execution -> Alpha Vantage / Analysis
                    ↓
              Langfuse (tracing)
```

### Market Data Flow

```
User Request -> Backend API -> Alpha Vantage API
                    ↓
              Redis Cache (TTL: 1hr)
                    ↓
              Response Formatting
```

### Authentication Flow

```
Login Request -> Auth Service -> JWT Generation
                      ↓
              MongoDB (refresh tokens)
                      ↓
              Client (localStorage)
```

---

## Development Workflow

### Quick Commands

```bash
# Local development
make dev                    # Start all services
make test                   # Run all tests
make fmt && make lint       # Format and lint

# Backend only
cd backend && make test && make lint

# Frontend (in container)
docker compose exec frontend npm run lint

# Version bump (required for commits)
./scripts/bump-version.sh backend patch
./scripts/bump-version.sh frontend minor
```

### Pre-commit Hooks

- **Black/Ruff**: Python formatting and linting
- **ESLint/Prettier**: TypeScript formatting
- **Version Check**: Ensures version bump on commit
- **File Length**: Max 500 lines per file

---

## Roadmap

### Completed Phases

| Phase | Status | Key Deliverables |
|-------|--------|------------------|
| **Foundation** | Done | Infrastructure, walking skeleton |
| **Agent Core** | Done | LangGraph ReAct agent, tools |
| **Production** | Done | Auth, deployment, observability |

### Current Phase: Scale

| Feature | Priority | Status |
|---------|----------|--------|
| Performance optimization | High | In Progress |
| Multi-user support | High | In Progress |
| Test environment (AKS) | Medium | Planned |
| Geographic distribution | Low | Planned |

### Backlog

- Options trading support
- Additional data providers
- Advanced portfolio analytics
- Mobile app (React Native)
- Real-time WebSocket updates

---

## Known Technical Debt

| Area | Issue | Impact | Priority |
|------|-------|--------|----------|
| **Cosmos DB Sorting** | Cannot sort by `_id` with compound filters | Medium | Fixed |
| **Intraday Technical Analysis** | Only daily+ intervals supported | Low | Documented |
| **Test Environment** | AKS not deployed | Low | Backlog |

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [CLAUDE.md](../CLAUDE.md) | Development guidelines, quick commands |
| [System Design](architecture/system-design.md) | Complete architecture |
| [Database Schema](architecture/database-schema.md) | MongoDB collections |
| [Agent Architecture](architecture/agent-architecture.md) | 12-factor agent |
| [Deployment Workflow](deployment/workflow.md) | CI/CD procedures |
| [Feature Specs](features/README.md) | Feature documentation |
| [E2E Testing](testing/e2e-reference.md) | Testing guides |

---

## Change Log

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2025-12-20 | 1.0 | Initial brownfield PRD creation | Winston (Architect) |
