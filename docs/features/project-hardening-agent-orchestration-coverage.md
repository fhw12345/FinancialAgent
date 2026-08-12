---
title: Agent Orchestration Composition Coverage
status: shipped
version: backend@0.51.3, frontend@0.32.3
last_updated: 2026-08-12
owner: maintainer
related_paths:
  - backend/src/agent/langgraph_react_agent.py
  - backend/src/agent/portfolio/
  - backend/src/services/data_manager/
  - backend/tests/
---

# PH-007: Agent Orchestration Composition Coverage

## Objective

Add tests at the real module boundaries where the current unit suite's mocks
allow signatures, lifecycle states, persistence, and fallback behavior to
drift.

## Required Invariants

- one user request owns one durable run;
- each run reaches exactly one terminal state;
- terminal assistant/decision persistence is idempotent;
- Phase 1 outputs validate as Phase 2 inputs and Phase 3 inputs;
- provider partial failures are data failures, not programming-error fallbacks;
- cancellation stops child work and releases locks;
- model/tool failures retain observability metadata;
- no broker order is submitted.

## Ownership and Parallel Safety

Agent G primarily owns new test harnesses and fixtures. Production fixes found
by tests must be coordinated with the owning task. Do not duplicate PH-002's
specific Insights test or PH-003's typing cleanup.

## Implementation Plan

1. Build reusable in-process Mongo/Redis repository fixtures or isolated test
   databases.
2. Use fake HTTP/model providers at the outer boundary, not mocked internal
   service methods.
3. Add composition tests for Direct, ReAct, Deep, and Portfolio execution.
4. Add failure injection for provider, LLM, Redis, Mongo, cancellation, and
   malformed structured output.
5. Assert persisted Run, Message, ToolExecution, Decision, and Order records.
6. Publish per-critical-module coverage in CI and establish ratcheting floors.
7. Keep live integration tests separately marked and opt-in.

## Coverage Targets

Initial minimums after this task:

- `langgraph_react_agent.py`: 60%;
- portfolio `flows.py`: 55%;
- Phase 1/2/3 modules: 65% each;
- optimizer executor/plan builder: 60%;
- DataManager: 70%.

Targets are not a substitute for invariant assertions.

## Test Plan

### Backend composition

Test success, clarification, duplicate request, cancellation, LLM timeout,
provider partial failure, structured-output rejection, and persistence failure.
Every test must assert both emitted events and database terminal state.

### Playwright E2E — required

Use the real frontend and deterministic backend/provider stubs:

1. ReAct tool request completes with source evidence;
2. Deep request shows specialist progress and final verdict;
3. Portfolio analysis persists a structured decision visible after reload;
4. injected tool failure ends with an honest recoverable/failed state;
5. cancellation persists after reload.

Capture `docs/features/assets/ph-007/01-portfolio-decision-after-reload.png` and
`02-agent-cancelled-terminal-state.png` after their respective assertions.

## Acceptance Criteria

- [x] Runtime, persistence, cancellation, retry, provider, and pipeline invariants have composition coverage.
- [x] Critical module coverage meets every declared floor.
- [x] Tests use real internal contracts and fake only external model/provider/storage boundaries.
- [x] Portfolio completion and cancellation browser workflows pass across reload.
- [x] Screenshot records identify deterministic fixture mode and tested commit.
- [x] Full backend, static, evaluation, and relevant browser suites pass.

## Implementation and Test Record

Four new composition suites exercise the real orchestration code while faking
only external providers, model graphs, and persistence transports:

- ReAct history, tool accounting, zero-tool nudge, transient retry, retry
  exhaustion, structured validation, and observability failures;
- Portfolio dashboard full/empty/single-symbol paths, consistency metadata,
  translation, Mongo degradation, and Phase 1→2 contract continuity;
- deterministic SELL/cover/BUY scaling, suggestion persistence, metadata
  updates, HOLD signals, and Phase 3 execution summaries;
- Treasury, IPO, news, insider, historical-price, FRED, Alpha Vantage, and
  yfinance provider normalization/fallback behavior.

The tests found and fixed two lifecycle defects: a transient ReAct exception was
retained and re-raised after a successful retry, and Phase 2 failure history
used `source="system"`, which the MessageCreate contract rejects.

Final full-suite coverage and gates:

| Critical module | Coverage | Floor |
| --- | ---: | ---: |
| ReAct orchestration | 60.05% | 60% |
| Portfolio flows | 64.58% | 55% |
| Phase 1 research | 74.66% | 65% |
| Phase 2 decisions | 69.77% | 65% |
| Phase 3 execution | 77.78% | 65% |
| Plan builder | 88.64% | 60% |
| Suggestion executor | 95.92% | 60% |
| DataManager | 71.11% | 70% |

The complete backend suite passed with 1,985 tests, 27 live integrations
deselected, 69% aggregate coverage, strict mypy, Ruff, and Black. CI now reads
`coverage.json` through `scripts/check-critical-coverage.py` and blocks any
floor regression. Deterministic Agent evaluation and the existing UAW event,
Portfolio prompt-governance, watchlist, Insights, and cancellation browser
paths remain green.

After visible assertions passed, Playwright captured:

- [`assets/ph-007/01-portfolio-decision-after-reload.png`](assets/ph-007/01-portfolio-decision-after-reload.png) from the deterministic frontend-to-backend Portfolio governance stack;
- [`assets/ph-007/02-agent-cancelled-terminal-state.png`](assets/ph-007/02-agent-cancelled-terminal-state.png) after the dedicated cancellation stack restored the persisted cancelled state.

Implementation commit: `54252dc`.

## Risks

Coverage work can become coupled to implementation details. Prefer public
service contracts, persisted invariants, and event sequences over private call
counts except where deduplication is the behavior under test.
