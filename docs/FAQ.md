---
title: FAQ
status: shipped
version: backend@0.30.x, frontend@0.23.x
last_updated: 2026-07-13
owner: maintainer
related_paths:
  - docs/development/getting-started.md
  - docs/architecture/overview.md
---

# Frequently Asked Questions

## Why does chat fail while the health endpoint is green?

MongoDB and Redis can be healthy while the selected LLM provider is
unavailable. Check `LLM_PROVIDER` and its matching endpoint.

## How do I switch LLM providers?

Set one of:

```env
LLM_PROVIDER=maestro
LLM_PROVIDER=anthropic
LLM_PROVIDER=copilot_reverse
```

Direct Anthropic additionally requires `ANTHROPIC_API_KEY` and
`ANTHROPIC_MODEL`. Copilot reverse requires the sibling `copilot-bridge`
process on port `8765`. Restart the backend after switching.

## Why did an environment change not take effect?

Container restarts reuse the existing environment. Run:

```bash
docker compose up -d --force-recreate backend
```

## Which market-data keys are required?

None for basic usage: yfinance is the free default. Finnhub improves quotes,
news, and insider data; FRED supplies macro liquidity metrics; Alpha Vantage
is a fallback; Exa improves independent web verification.

## Why are Chinese translations missing?

Translations also use Agent Maestro. If translation fails, English is stored
and rendered rather than blocking the write. Redis caches successful
translations, and the frontend can request a missing translation lazily.

## What are the chat modes?

- **Copilot (`v2`)**: direct simple-chat completion
- **Agent (`v3`)**: ReAct agent that selects financial tools
- **Deep (`v4-deep`)**: specialist research, adversarial review, and verdict

## What does the portfolio pipeline do?

Phase 1 researches each symbol independently. Phase 2 considers the portfolio,
cash, diversification, and deterministic risk metrics together. Results are
stored as decisions and order suggestions. No broker API is called.

## How do I run portfolio analysis?

Use the analysis controls on the Portfolio page. The removed cloud CronJob and
multi-user scheduler are not part of the local application.

## How do I add a data provider?

Add the provider under `backend/src/services/` and integrate it into
`DataManager` so caching and fallback behavior remain centralized.

## How do I add an agent skill?

Add a skill under `backend/src/agent/skills/<domain>/`, register any tools in
the appropriate tool factory, and update the
[skill catalog](../backend/src/agent/skills/README.md).

## Where are historical changes documented?

Use the backend/frontend changelogs and the case studies. Superseded PRDs and
implementation snapshots are intentionally not kept in the active docs tree.
