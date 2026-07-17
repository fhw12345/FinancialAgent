---
title: Deep Research Conversation Context
status: shipped
version: backend@0.34.0, frontend@0.25.2
last_updated: 2026-07-17
owner: maintainer
related_paths:
  - backend/src/agent/deep_research_context.py
  - backend/src/agent/deep_agent_adapter.py
  - backend/src/agent/deep_react_agent.py
  - backend/src/agent/symbol_tokens.py
  - backend/src/api/chat/streaming/deep_agent.py
  - frontend/e2e/uaw-003-deep-context.spec.ts
---

# UAW-003: Deep Research Conversation Context

## Implementation Record

Shipped in commit `95631fc`.

Delivered:

- bounded `DeepResearchContext` with recent turns and size limits;
- newest-first history budgeting so old turns are dropped before the latest
  user request and assistant report;
- deterministic extraction of prior symbol, horizon, risk tolerance, and
  research constraints;
- current-turn precedence for horizon, risk tolerance, and mutually exclusive
  research focus;
- validated prior-symbol reuse only for deictic follow-ups;
- shared explicit-ticker parsing with current-message ticker priority over UI
  state and historical candidates;
- context injection into technical, news, financial, debate, rebuttal, and
  verdict prompts;
- compact prior-report excerpts for specialists and full context only for
  critique, rebuttal, and verdict synthesis;
- specialist selection that honors technical-only, valuation/fundamental-only,
  and exclude-news constraints;
- context metadata persistence with the final Deep assistant message;
- deterministic test-only Deep adapter that preserves the real browser,
  FastAPI, MongoDB, context, SSE, and restoration path;
- Playwright proof across three Deep turns and browser reload;
- fixes for risk-language ambiguity (`aggressively` is not investor risk
  tolerance) and restored-chat synchronization inherited from UAW-002.

Validation summary:

```text
UAW-003 backend regression tests: 52 passed
Backend full regression suite: 1788 passed, 27 deselected
Backend Ruff: passed
Changed backend modules isolated mypy: passed
Frontend unit tests: 212 passed
Frontend lint/type-check/build: passed
Playwright Deep context scenario: 1 passed
```

The repository-wide mypy baseline remains non-green with 349 pre-existing
errors across 91 files. UAW-003 changed modules pass isolated mypy checking.

### Screenshot Evidence

| Evidence | Scenario | Stack | Commit | Result |
| --- | --- | --- | --- | --- |
| [Prior thesis challenged](assets/uaw-003/01-prior-thesis-challenged.png) | Follow-up receives previous bullish thesis and adversarial/downside constraints | Real frontend/backend + deterministic Deep adapter | `95631fc` | PASS |
| [Horizon preserved](assets/uaw-003/02-horizon-preserved.png) | Initial six-month horizon and moderate risk are structured | Real frontend/backend + deterministic Deep adapter | `95631fc` | PASS |
| [Constraints after reload](assets/uaw-003/03-constraints-restored-after-reload.png) | Reloaded chat preserves valuation, downside, horizon, and risk constraints | Real frontend/backend + deterministic Deep adapter | `95631fc` | PASS |
| [Context metadata](assets/uaw-003/04-context-metadata-visible-in-history.png) | Persisted response exposes turn count, prior-report status, and truncation | Real frontend/backend + deterministic Deep adapter | `95631fc` | PASS |

## 1. Task Summary

Make Deep Research understand relevant prior turns without injecting the full
raw chat transcript into every specialist prompt.

The workflow must preserve:

- confirmed symbol;
- previous research thesis and verdict;
- investment horizon;
- risk tolerance;
- explicit user constraints;
- the current follow-up intent.

Examples that must work:

```text
Now challenge that thesis more aggressively.
Use the same six-month horizon but compare the downside case.
Keep the previous risk tolerance and focus only on valuation.
```

This is the third implementation task from the
[Unified Agent Workflow Improvement Roadmap](../architecture/unified-agent-workflow-roadmap.md).

## 2. Current Problem

The Deep streaming handler prepares Mongo-authoritative history and passes it
to `DeepAgentAdapter.ainvoke`.

The adapter currently logs:

```text
conversation history received, not forwarded
```

It then calls:

```python
deep_agent.analyze(
    symbol=symbol,
    user_message=user_message,
)
```

`DeepReActAgent.analyze` creates initial state containing only the current user
message. More importantly, specialist prompts are hard-coded:

```text
Analyze the technical setup for SYMBOL.
Analyze recent news and sentiment for SYMBOL.
Analyze the fundamentals of SYMBOL.
```

The current user request itself is not included in those specialist prompts,
so even first-turn requirements such as “focus on downside risk over six
months” can be weakened or lost.

## 3. Goal

Introduce a bounded, typed `DeepResearchContext` that converts persisted
conversation history into explicit research constraints.

The context is injected into:

- technical specialist prompt;
- news specialist prompt;
- financial specialist prompt;
- adversarial debate prompt;
- rebuttal prompt;
- final verdict prompt.

The current request and prior context must remain distinguishable.

## 4. Non-Goals

UAW-003 does not:

- add durable graph checkpoints;
- resume a partially completed research graph;
- merge Deep Research with conversational ReAct;
- store hidden chain-of-thought;
- include every historical message;
- perform semantic vector retrieval;
- support multi-symbol portfolio research inside one Deep graph;
- add a unified Run model;
- redesign the Deep Agent accordion.

## 5. Context Contract

Proposed model:

```python
@dataclass(frozen=True)
class DeepResearchContext:
    confirmed_symbol: str
    current_request: str
    previous_user_request: str | None
    previous_assistant_report: str | None
    investment_horizon: str | None
    risk_tolerance: str | None
    constraints: tuple[str, ...]
    relevant_turns: tuple[ResearchTurn, ...]
    truncated: bool
```

`ResearchTurn` contains:

```text
role
content
```

It does not contain provider payloads, tool traces, or hidden reasoning.

## 6. Context Selection

### 6.1 Source

Use the Mongo-authoritative history produced by UAW-002.

### 6.2 Selection Rules

- retain at most six recent user/assistant turns;
- cap each turn to 1,200 characters;
- cap total rendered context to 6,000 characters;
- prioritize the most recent assistant report;
- prioritize explicit user constraints;
- exclude welcome messages and empty content;
- exclude raw tool metadata;
- preserve compacted summary messages;
- mark `truncated=true` when limits are applied.

### 6.3 Structured Extraction

Use deterministic parsing first:

- horizon: day/week/month/year phrases in English and Chinese;
- risk tolerance: conservative/moderate/aggressive and Chinese equivalents;
- constraints: valuation-only, downside-only, no-news, technical-only,
  adversarial, compare scenarios.

Do not add another LLM call in UAW-003 solely for context extraction.

## 7. Symbol Continuity

Resolution priority:

1. explicit ticker in current request;
2. current frontend symbol;
3. last validated symbol from research context;
4. normal UAW-001 clarification.

Any symbol recovered from history must still pass `SymbolSearchService.exact`.

A follow-up such as:

```text
Challenge that conclusion.
```

may reuse the previous symbol only when the chat contains one unambiguous
validated research symbol.

## 8. Prompt Rendering

Render one shared block:

```text
=== RESEARCH REQUEST CONTEXT ===
Confirmed symbol: SKHY
Current request: Challenge the previous bullish thesis.
Previous request: Analyze SKHY over a six-month horizon.
Investment horizon: 6 months
Risk tolerance: moderate
Constraints:
- focus on downside evidence
- preserve prior horizon

Previous report excerpt:
...
=== END RESEARCH REQUEST CONTEXT ===
```

Every specialist prompt receives the same block followed by role-specific
instructions.

The final verdict explicitly answers the current request rather than generating
a generic investment report.

## 9. Backend Scope

### New Component

```text
backend/src/agent/deep_research_context.py
```

Responsibilities:

- normalize relevant prior turns;
- extract structured constraints;
- identify prior report and symbol candidates;
- enforce size limits;
- render prompt context.

### Modified Components

`deep_agent_adapter.py`:

- build context from `conversation_history`;
- use prior symbol only when frontend/current message lacks one;
- pass context into `DeepReActAgent.analyze`;
- log context fields without logging full report text.

`deep_react_agent.py`:

- add structured context to `AnalysisState`;
- include it in specialist, debate, rebuttal, and verdict prompts;
- use compact specialist context and full synthesis context;
- return context metadata for observability.

`deep_agent.py`:

- continue using Mongo-authoritative prepared history;
- persist context metadata under assistant message `raw_data`;
- keep clarification behavior unchanged.

## 10. Tests

### Unit

- empty history produces current-request-only context;
- previous report is selected from latest assistant turn;
- six-turn and character limits are enforced;
- English and Chinese horizons are extracted;
- risk tolerance is extracted;
- constraints are deduplicated;
- prior symbol requires validation;
- explicit current ticker overrides history symbol.

### Graph Prompt Tests

- each specialist prompt includes current request;
- prior thesis appears once;
- debate and verdict include the same horizon and risk tolerance;
- truncated context does not exceed the configured limit;
- no raw tool metadata enters prompts.

### Handler Integration

- Deep handler forwards prepared Mongo history;
- follow-up without symbol reuses validated prior symbol;
- unrelated chat cannot leak its symbol or report;
- persisted response records context metadata.

## 11. Playwright E2E

Use a dedicated deterministic Deep adapter in a test-only FastAPI app. The
browser still uses:

```text
React UI -> FastAPI chat handler -> MongoDB -> context builder -> Deep adapter
```

Only expensive specialist/model execution is replaced with a deterministic
adapter that echoes the received structured context.

### Scenario A: Challenge Prior Thesis

1. Select `SKHY`.
2. Send a deep analysis request with a six-month horizon.
3. Receive deterministic bullish thesis.
4. Send “Now challenge that thesis more aggressively.”
5. Assert the response contains:
   - SKHY;
   - six-month horizon;
   - prior bullish thesis;
   - adversarial constraint.

### Scenario B: Preserve User Constraints

1. First request states moderate risk tolerance and valuation focus.
2. Reload the browser.
3. Send “Use the same constraints and focus on downside.”
4. Assert retained risk tolerance, valuation focus, and new downside focus.

### Screenshot Evidence

```text
docs/features/assets/uaw-003/
  01-prior-thesis-challenged.png
  02-horizon-preserved.png
  03-constraints-restored-after-reload.png
  04-context-metadata-visible-in-history.png
```

Each screenshot is captured after assertions pass and records the shipping
commit in this document.

## 12. Validation

```bash
cd backend
python -m pytest \
  tests/test_deep_research_context.py \
  tests/test_deep_agent_adapter_context.py \
  tests/test_deep_agent_context_integration.py \
  tests/test_deep_agent_streaming.py \
  tests/test_symbol_resolver.py

make test-e2e-uaw003
make test
make lint
```

## 13. Acceptance Criteria

- [x] Deep Research receives bounded prior context.
- [x] Current request is present in every specialist prompt.
- [x] Previous thesis and verdict are available to follow-up analysis.
- [x] Investment horizon and risk tolerance persist across turns.
- [x] Explicit current constraints override historical constraints.
- [x] Explicit current symbol overrides prior symbol.
- [x] Historical symbol is validated before reuse.
- [x] Context does not exceed configured limits.
- [x] No hidden reasoning or raw tool payload is persisted as context.
- [x] Context metadata is persisted with the assistant response.
- [x] Playwright challenge and reload scenarios pass.
- [x] Four screenshot artifacts are linked.
- [x] Full regression tests, Ruff, frontend validation, and isolated changed-module
  mypy pass.

## 14. Risks

| Risk | Mitigation |
| --- | --- |
| Previous report consumes too much context | Hard per-turn and total limits |
| Stale thesis overrides current request | Label current request separately and give it priority |
| Wrong symbol leaks from old conversation | Use current chat only and validate historical symbol |
| Full transcript duplicated in every subagent | Render one bounded structured block |
| Tests replace too much production behavior | Stub only expensive Deep execution, not handler/context/persistence |
| Context extraction invents constraints | Deterministic parsing only in UAW-003 |

## 15. Follow-Up

After UAW-003:

1. UAW-004 Watchlist persistence wiring.
2. Agent-task cancellation.
3. Honest streaming semantics.
4. Durable Research Job checkpoints.
