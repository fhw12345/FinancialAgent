---
title: Agent Skill Catalog
status: shipped
version: backend@0.29.x, frontend@n/a
last_updated: 2026-05-16
owner: maintainer
related_paths:
  - backend/src/agent/skills/
  - backend/src/agent/langgraph_react_agent.py
  - backend/src/agent/portfolio/
---

# Agent Skill Catalog

The ReAct and Deep ReAct agents draw on a fixed set of **skills**, each
packaged as a directory containing a `SKILL.md` (the human + LLM-readable
contract) and the tools listed in its `allowed-tools` frontmatter. A skill is
the smallest unit of capability the agent can reason about: it has a name, a
single-line description, a complexity tier, and a tool whitelist.

This page is the **capability matrix**. Open a skill's `SKILL.md` for the
step-by-step workflow the LLM follows.

## How Skills Are Wired

```
backend/src/agent/skills/
├── debater/        # adversarial checks against a thesis
├── financial/      # fundamentals, valuation, cash flow
├── news/           # sentiment, catalysts, market mood
└── technical/      # price action: Fibonacci, momentum, trend
```

- **Default ReAct agent** loads all technical / financial / news skills
  (`langgraph_react_agent.py`).
- **Deep ReAct** (used by the portfolio Phase 1 research pass and the chat
  agent's deep-dive mode) additionally pulls in the debater skills for
  fact-check / counter-evidence / risk review.
- Skill discovery is filesystem-driven — adding a directory under the right
  domain and wiring it in `langgraph_react_agent.py` is enough.

## Capability Matrix

| Domain | Skill | Complexity | Allowed Tools | What it does |
|---|---|---|---|---|
| technical | fibonacci-analysis | intermediate | `get_historical_prices`, `fibonacci_analysis_tool` | Calculate Fibonacci retracement levels and identify golden-zone support/resistance |
| technical | momentum-signals | intermediate | `stochastic_analysis_tool`, `get_historical_prices` | Analyze Stochastic oscillator for momentum signals and divergences |
| technical | trend-detection | basic | `get_historical_prices`, `stochastic_analysis_tool` | Identify primary trend direction and strength using price action |
| financial | cashflow-health | intermediate | `get_financial_statements`, `get_company_overview` | Assess cash-flow generation, debt levels, and financial stability |
| financial | earnings-quality | intermediate | `get_company_earnings`, `get_financial_statements` | Evaluate earnings trends, beat rate, and quality signals |
| financial | valuation-assessment | basic | `get_company_overview` | Analyze valuation metrics (P/E, PEG, P/S) to assess fair value |
| news | catalyst-identification | intermediate | `get_news_sentiment`, `get_company_overview` | Identify upcoming and recent catalysts that could move the stock |
| news | market-mood | basic | `get_market_movers` | Assess overall market sentiment and how the target stock fits |
| news | sentiment-analysis | basic | `get_news_sentiment` | Aggregate and analyze news sentiment for a stock symbol |
| debater | assumption-testing | advanced | `fetch_yfinance_news`, `search_web_exa` | Challenge the underlying assumptions in the investment thesis |
| debater | counter-evidence | advanced | `fetch_yfinance_news`, `search_web_exa` | Search for evidence that contradicts the investment thesis using independent sources |
| debater | fact-checking | intermediate | `fetch_yfinance_news`, `search_web_exa` | Verify specific claims in the thesis against independent sources |
| debater | risk-assessment | advanced | `fetch_yfinance_news`, `search_web_exa` | Identify risk factors not adequately addressed in the thesis |

**Counts**: 13 skills across 4 domains — 3 technical, 3 financial, 3 news, 4
debater.

## Complexity Tiers

| Tier | Meaning |
|---|---|
| basic | Single tool call, deterministic interpretation, no chained reasoning |
| intermediate | 2–3 tool calls, conditional branching, basic synthesis |
| advanced | Multi-step research with independent-source cross-checks, used by debater sub-agents |

## Adding a New Skill

1. Create `backend/src/agent/skills/<domain>/<skill-name>/SKILL.md` with the
   frontmatter schema you see in any existing skill (`name`, `description`,
   `allowed-tools`, `metadata.domain`, `metadata.complexity`).
2. Implement / reuse the tools listed in `allowed-tools`. Tool registration
   happens in the corresponding tool factory under
   `backend/src/agent/tools/` or `backend/src/services/`.
3. Wire the skill into `backend/src/agent/langgraph_react_agent.py` (default
   ReAct) and/or the deep-research path
   (`backend/src/agent/portfolio/` for portfolio agent, debater sub-agent
   for the chat debate flow).
4. Update this matrix in the same commit so the catalog stays accurate.
5. Add tests under `backend/tests/` mirroring the skill's tool list — see
   existing skill tests for the pattern.

## Cross-References

- Agent architecture & 12-factor design:
  [`../../../docs/architecture/agent-12-factors.md`](../../../docs/architecture/agent-12-factors.md)
- ReAct agent integration:
  [`../../../docs/architecture/react-agent-integration.md`](../../../docs/architecture/react-agent-integration.md)
- Portfolio Phase-1/2/3 pipeline:
  [`../../../docs/features/portfolio-agent-architecture-refactor.md`](../../../docs/features/portfolio-agent-architecture-refactor.md)
- Architecture overview (system map):
  [`../../../docs/architecture/overview.md`](../../../docs/architecture/overview.md)
