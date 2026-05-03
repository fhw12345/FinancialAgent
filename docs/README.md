# Financial Agent Documentation

AI-Enhanced Financial Analysis Platform documentation hub.

---

## Current Status

| Component | Version | Environment | URL |
|-----------|---------|-------------|-----|
| Backend | v0.8.8 | Prod (ACK) | http://localhost:3000 |
| Frontend | v0.11.4 | Prod (ACK) | http://localhost:3000 |
| Test | Planned | AKS | http://localhost:3000 |
| Local Dev | Docker | Compose | http://localhost:3000 |

> **Environment details**: See [CLAUDE.md](../CLAUDE.md#-environment-rules) for complete environment configuration.

---

## Quick Navigation

### Essential Links
- [PRD (Product Requirements)](prd.md) - Complete product specification
- [Getting Started](development/getting-started.md) - Local development setup
- [System Design](architecture/system-design.md) - Architecture overview
- [Deployment Workflow](deployment/workflow.md) - Deploy to cloud
- [CLAUDE.md](../CLAUDE.md) - Development guidelines & quick commands

### By Category

#### Architecture
System design and architectural decisions.

- [System Design](architecture/system-design.md) - Tech stack, patterns, overview
- [Agent Architecture](architecture/agent-architecture.md) - 12-factor agent implementation
- [Database Schema](architecture/database-schema.md) - MongoDB collections
- [React Agent Integration](architecture/react-agent-integration.md) - LangGraph agent flow
- [React Agent Debugging](architecture/react-agent-debugging.md) - Components, patterns, debugging

#### Deployment
Cloud infrastructure and deployment procedures.

- [Deployment Workflow](deployment/workflow.md) - Build, deploy, verify, rollback
- [ACK Architecture](deployment/ack-architecture.md) - Alibaba Cloud production
- [Cloud Setup](deployment/cloud-setup.md) - Azure/Alibaba hybrid setup
- [Infrastructure](deployment/infrastructure.md) - K8s resources, networking
- [SLS Logging](deployment/sls-logging.md) - Application log collection to Alibaba Cloud SLS
- [Cost Optimization](deployment/cost-optimization.md) - Resource management

#### Development
Local development and coding practices.

- [Getting Started](development/getting-started.md) - Environment setup
- [Coding Standards](development/coding-standards.md) - Python/TypeScript patterns
- [Testing Strategy](development/testing-strategy.md) - Unit, integration, E2E
- [Verification](development/verification.md) - Health checks, validation

#### Features
Feature specifications (create before implementing).

- [Feature Specs Guide](features/README.md) - How to write feature specs
- [Market Insights Trend Visualization](features/market-insights-trend-visualization.md) - Phase 2 trend charts & sparklines
- [Backend API Module Restructure](features/backend-api-module-restructure.md) - v0.8.8 modular architecture
- [Portfolio Agent Architecture](features/portfolio-agent-architecture-refactor.md) - 3-phase analysis
- [Langfuse Observability](features/langfuse-observability.md) - LLM trace visualization
- Browse `features/` for more specifications

#### Testing
End-to-end testing guides.

- [E2E Automation Guide](testing/e2e-automation-guide.md) - Playwright testing
- [E2E Reference](testing/e2e-reference.md) - Selectors, endpoints

#### Performance
System performance baselines and optimization.

- [Performance Overview](performance/README.md) - Bottleneck analysis, success metrics
- [API Baseline](performance/api-baseline.md) - Endpoint response times
- [Redis Baseline](performance/redis-baseline.md) - Cache hit rates, memory usage
- [LLM Baseline](performance/llm-baseline.md) - Agent performance, token usage
- [Frontend Baseline](performance/frontend-baseline.md) - Bundle size, Core Web Vitals
- [Infrastructure Baseline](performance/infrastructure-baseline.md) - K8s resource utilization

#### Troubleshooting
Issue resolution and debugging.

- [Troubleshooting Index](troubleshooting/README.md) - All issues
- [Deployment Issues](troubleshooting/deployment-issues.md) - K8s problems
- [Docker Env Reload Issue](troubleshooting/docker-env-reload-issue.md) - 🚨 Critical: Container env vars
- [Known Bugs](troubleshooting/known-bugs.md) - Current issues

#### Project
Version history and specifications.

- [Version Management](project/versions/README.md) - Release notes, changelogs
- [Specifications](project/specifications.md) - Full project specs

---

## Key Features

### Financial Analysis
- Fibonacci retracement with confidence scoring
- Stochastic oscillator analysis
- Market structure detection
- Macro sentiment (VIX, sectors)
- Fundamental analysis (overview, balance sheet, cash flow)
- News sentiment analysis
- Market movers (gainers, losers)

### Market Insights (NEW - Phase 2)
- AI-powered sector risk analysis (AI Sector Risk Index)
- Multi-metric composite scoring with transparent breakdowns
- Historical trend visualization with sparklines
- Daily automated snapshots via CronJob
- Expandable metric cards with methodology explanations

> **Note**: Technical analysis available for daily/weekly/monthly intervals only. Intraday (1min) is price-only.

### AI Capabilities
- Natural language chat interface
- Multimodal chart interpretation (Qwen-VL)
- Autonomous tool chaining (LangGraph ReAct agent)
- Context-aware responses

---

## Documentation Standards

- **Max 500 lines** per file
- Link to CLAUDE.md for development workflows
- Keep content current - update when making changes
- Archive deprecated content in `docs/archive/`
  - `archive/versions/` - Historical version release notes
  - `archive/troubleshooting-history/` - Resolved issues reference

---

## Additional Resources

- [Project README](../README.md) - Repository overview
- [CLAUDE.md](../CLAUDE.md) - Development guidelines
- [API Docs](http://localhost:8000/docs) - OpenAPI (local)
