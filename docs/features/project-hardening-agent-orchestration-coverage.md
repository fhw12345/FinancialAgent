---
title: Agent Orchestration Composition Coverage
status: planning
version: backend@0.51.2, frontend@0.32.2
last_updated: 2026-08-06
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
`02-agent-failure-terminal-state.png` after their respective assertions.

## Acceptance Criteria

- [ ] All listed invariants have composition tests.
- [ ] Critical module coverage meets floors.
- [ ] Tests use real internal contracts and only fake external boundaries.
- [ ] Required browser workflows pass and persist across reload.
- [ ] Screenshot records include fixture mode and tested commit.
- [ ] Full backend/frontend/eval suites pass.

## Risks

Coverage work can become coupled to implementation details. Prefer public
service contracts, persisted invariants, and event sequences over private call
counts except where deduplication is the behavior under test.
