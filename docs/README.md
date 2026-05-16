# Documentation Index

> Single-user local fork of Financial Agent. Cloud / SaaS / multi-tenant docs
> have been removed. Everything below describes the locally-run tool.

**Start here**: [`architecture/overview.md`](architecture/overview.md) →
[`development/getting-started.md`](development/getting-started.md) →
[`FAQ.md`](FAQ.md). The full documentation policy (frontmatter schema, status
enum, dates, links) lives in
[`development/documentation.md`](development/documentation.md).

## Architecture

- [Overview](architecture/overview.md) — system map, data flow, agent graph
- [API Reference](architecture/api-reference.md) — every backend route, OpenAPI as source of truth
- [Agent 12-Factors](architecture/agent-12-factors.md) — design principles
- [Agent Architecture](architecture/agent-architecture.md) — Deep Agent + sub-agents
- [ReAct Agent Integration](architecture/react-agent-integration.md)
- [ReAct Agent Debugging](architecture/react-agent-debugging.md)

## Development

- [Getting Started](development/getting-started.md) — local Docker setup
- [Documentation Policy](development/documentation.md) — how to write docs
- [Coding Standards](development/coding-standards.md)
- [Error Handling](development/error-handling.md)

## Features

- [Write-time Translation](features/write-time-translation.md)
- [Market Insights — Trend Visualization](features/market-insights-trend-visualization.md)
- [Chat Symbol Context](features/chat-symbol-context.md)
- [Symbol Search & Chart Improvements](features/symbol-search-and-chart-improvements.md)
- [Fibonacci Trend Detection](features/fibonacci-trend-detection-improvements.md)
- [Extended-Hours Trading Data](features/extended-hours-trading-data.md)
- [Portfolio Agent Architecture](features/portfolio-agent-architecture-refactor.md)
- [LangGraph SDK ReAct Agent](features/langgraph-sdk-react-agent.md)
- [Backend API Module Restructure](features/backend-api-module-restructure.md)

See also: [`features/README.md`](features/README.md).

## Agent Skills

- [Skill Catalog](../backend/src/agent/skills/README.md) — 13-skill capability matrix

## Case Studies

Bug post-mortems and pitfalls in interview-style write-ups.

- [Case Studies Index](case-studies/README.md)

## Project

- [FAQ](FAQ.md) — common runtime / setup / agent questions
- [Versions](project/versions/README.md) — independent backend / frontend semver
- [Backend Changelog](project/versions/backend/CHANGELOG.md)
- [Frontend Changelog](project/versions/frontend/CHANGELOG.md)
- [Archive](archive/) — historical PRDs and progress logs
