---
title: Deep Agent Symbol Clarification
status: in-progress
version: backend@0.32.0, frontend@0.25.0
last_updated: 2026-07-15
owner: maintainer
related_paths:
  - backend/src/agent/deep_agent_adapter.py
  - backend/src/api/chat/streaming/deep_agent.py
  - backend/src/api/market/search.py
  - frontend/src/components/EnhancedChatInterface.tsx
  - frontend/src/services/api.ts
---

# UAW-001: Deep Agent Symbol Clarification

## Implementation Record

The implementation and validation are complete in the current working tree.
The feature remains `in-progress` until the change set is committed.

Delivered:

- typed symbol candidates and resolution states;
- reusable local/provider symbol search service;
- rules-first resolver with structured LLM candidate generation;
- removal of every silent AAPL fallback;
- persisted `clarification_required` SSE events;
- frontend clarification card, candidate selection, and chat restoration;
- Playwright harness with mocked and real-stack browser scenarios;
- four curated screenshot artifacts.

Validation summary:

```text
Backend feature tests: 20 passed
Frontend feature tests: 6 passed
Playwright mocked scenarios: 2 passed
Playwright real-stack scenarios: 1 passed
Full backend suite: 1733 passed, 27 deselected
Full frontend suite: 212 passed
```

### Screenshot Evidence

| Evidence | Scenario | Stack | Commit | Result |
| --- | --- | --- | --- | --- |
| [Ambiguous candidates](assets/uaw-001/01-ambiguous-symbol-candidates.png) | Multiple validated candidates render without starting research | Mocked SSE | pending | PASS |
| [Unresolved request](assets/uaw-001/02-unresolved-symbol-real-stack.png) | Unknown company stops before Deep Agent execution | Real local stack | pending | PASS |
| [Candidate selected](assets/uaw-001/03-candidate-selected-follow-up-ready.png) | Selection updates chart context and prepares a follow-up without submitting | Mocked SSE | pending | PASS |
| [Restored clarification](assets/uaw-001/04-restored-clarification.png) | Persisted clarification survives reload and chat restoration | Real local stack | pending | PASS |

## 1. Task Summary

Remove the Deep Agent's silent fallback to `AAPL`. When the requested security
cannot be resolved with sufficient confidence, stop before any research tool
or specialist agent runs and ask the user to confirm a symbol.

This is the first implementation task from the
[Unified Agent Workflow Improvement Roadmap](../architecture/unified-agent-workflow-roadmap.md).

## 2. Why This Task Is First

The current failure mode is unsafe:

```text
symbol extraction fails
  -> silently choose AAPL
  -> run expensive research
  -> return a confident report about the wrong company
```

This is worse than a visible error because the response can look complete,
well-researched, and financially credible while answering a different
question.

The task is first because it:

- prevents incorrect financial analysis;
- removes a high-risk live-demo failure;
- establishes the first structured human-clarification event;
- creates reusable symbol-resolution infrastructure for the unified workflow;
- can ship independently of the later run-state and checkpoint redesign.

## 3. Current Behavior

Symbol resolution currently happens inside `DeepAgentAdapter`:

```text
current_symbol from frontend
  -> explicit uppercase ticker regex
  -> LLM extracts one ticker
  -> AAPL if the LLM returns UNKNOWN, invalid output, or raises
```

Current limitations:

1. `AAPL` is returned for unresolved requests.
2. LLM output is parsed as unstructured text.
3. A ticker inferred by the LLM is not validated against the symbol directory.
4. Multiple plausible companies are forced into one answer.
5. Regex accepts many two-to-five-letter uppercase words as tickers.
6. The symbol-search provider chain is implemented in the API module and is
   not reusable from the agent layer.
7. The SSE protocol has no clarification event.
8. The frontend can display errors but cannot render candidate symbols.
9. Clarification state is not persisted or restored with chat history.
10. The repository has no active Playwright configuration for browser-level
    workflow validation and screenshot evidence.

## 4. Goal

Introduce a typed symbol-resolution boundary that produces one of:

```text
resolved
ambiguous
unresolved
```

Only `resolved` may start Deep Agent research.

`ambiguous` and `unresolved` produce a `clarification_required` event, a
persisted assistant clarification message, and a normal stream completion.
They are not system errors.

## 5. Non-Goals

This task does not:

- implement the complete unified `Run` model;
- resume the same Deep Agent graph after clarification;
- add durable LangGraph checkpoints;
- fix Deep Agent conversation-history propagation;
- merge v2 and v3;
- redesign frontend symbol search;
- support non-US securities or asset classes;
- verify that a company is financially suitable for analysis;
- guarantee that an external provider has complete data for every valid symbol.

Automatic resume after a candidate is selected belongs to the later Research
Job human-in-the-loop and checkpoint tasks. For this task, selecting a
candidate prepares an explicit follow-up request.

## 6. User Experience

### 6.1 Resolved Request

User:

```text
请对 TSLA 做完整投资分析并加入反方质疑
```

System:

```text
resolution = TSLA
Deep research starts normally
```

### 6.2 Ambiguous Request

User:

```text
请深度分析 Apple
```

If the resolver finds one validated, high-confidence match:

```text
AAPL - Apple Inc.
```

research may start without clarification.

If a query has multiple similarly ranked candidates:

```text
请选择要分析的股票：

[ABC - Company A]
[ABD - Company B]
[搜索其他股票]
```

No research starts until the user submits a follow-up request with a confirmed
symbol.

### 6.3 Unresolved Request

User:

```text
请完整分析我昨天看到的那家公司
```

System:

```text
我无法确定你要分析的股票。请在右侧选择股票，或在消息中输入 ticker。
```

No fallback symbol is selected.

### 6.4 Candidate Selection

For the first implementation:

1. The user selects a candidate.
2. The frontend updates `current_symbol` and company name.
3. The composer is populated with an explicit localized follow-up, for
   example:

   ```text
   请使用 AAPL 继续进行上述深度分析。
   ```

4. The user confirms and sends the request.

The frontend must not silently submit a duplicate expensive request.

## 7. Resolution Contract

### 7.1 Backend Models

Add reusable Pydantic models:

```python
from typing import Literal

from pydantic import BaseModel, Field


class SymbolCandidate(BaseModel):
    symbol: str
    name: str
    exchange: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    match_type: str


class SymbolResolution(BaseModel):
    status: Literal["resolved", "ambiguous", "unresolved"]
    source: Literal[
        "ui_context",
        "explicit_ticker",
        "local_directory",
        "provider_search",
        "llm_assisted",
    ]
    reason_code: str
    symbol: str | None = None
    company_name: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    candidates: list[SymbolCandidate] = Field(default_factory=list)
```

Invariants:

- `resolved` requires `symbol`.
- `ambiguous` requires at least two candidates.
- `unresolved` must not contain a selected symbol.
- candidates are deduplicated by normalized symbol.
- candidate count is capped at five.

### 7.2 Clarification SSE Event

Add a stable event:

```json
{
  "type": "clarification_required",
  "clarification_type": "symbol",
  "reason_code": "ambiguous_symbol",
  "message": "Please select the company you want to analyze.",
  "original_request": "Please deeply analyze ABC",
  "candidates": [
    {
      "symbol": "ABC",
      "name": "AmerisourceBergen example",
      "exchange": "NYSE",
      "confidence": 0.82
    }
  ]
}
```

The actual candidate data must come from the symbol directory or market search,
not directly from unvalidated LLM output.

Supported reason codes:

```text
ambiguous_symbol
symbol_not_found
symbol_missing
symbol_resolution_invalid
```

Provider or infrastructure failures are not clarification cases. They continue
to use an error event such as:

```text
SYMBOL_RESOLUTION_FAILED
```

### 7.3 Persisted Metadata

Persist the event under the assistant clarification message:

```json
{
  "raw_data": {
    "clarification_required": {
      "type": "clarification_required",
      "clarification_type": "symbol",
      "reason_code": "ambiguous_symbol",
      "candidates": []
    },
    "route_selected": {}
  }
}
```

Persist a human-readable assistant message so older clients still show useful
content even if they do not understand the structured event.

Do not persist an invented final research answer or a fake tool execution
count.

## 8. Resolution Algorithm

### 8.1 Resolution Priority

```text
1. selected UI symbol
2. explicit ticker in the user message
3. deterministic company-name search
4. LLM-assisted candidate generation
5. unresolved clarification
```

### 8.2 Selected UI Symbol

- Normalize whitespace and case.
- Validate ticker syntax.
- Require an exact symbol-directory or provider-search match.
- Return `resolved` with source `ui_context`.
- If invalid, continue to message-based resolution rather than trusting it.

### 8.3 Explicit Ticker

- Support normal US ticker forms, including class-share separators.
- Exclude known stop words.
- Validate the extracted ticker against reusable symbol search.
- If one valid exact match exists, return `resolved`.
- If the token does not exist, return `unresolved`; do not ask an LLM to
  reinterpret an explicit invalid ticker as another company.

### 8.4 Deterministic Company Search

Reuse the existing search ranking:

```text
exact symbol
symbol prefix
name prefix
fuzzy name or symbol
```

Resolution is automatic only when:

- there is one validated candidate above the high-confidence threshold; and
- the score margin over the next candidate is sufficiently large.

Initial policy:

```text
auto-resolve confidence >= 0.90
minimum margin over second candidate >= 0.15
```

These values are policy constants and must be covered by tests. They may later
move into the unified execution policy.

### 8.5 LLM-Assisted Candidate Generation

The LLM is used only when deterministic search cannot resolve the company name,
for example a Chinese company name or alias.

Use structured output:

```python
class LLMSymbolCandidates(BaseModel):
    query: str
    candidates: list[str]
```

Rules:

- return at most three ticker candidates;
- return an empty list when uncertain;
- never choose a final symbol directly;
- validate every candidate against the symbol search service;
- resolve automatically only when the validated ranking policy permits it;
- otherwise return `ambiguous` or `unresolved`.

LLM timeout, malformed output, or provider failure produces `unresolved`, not
`AAPL`.

### 8.6 Symbol Normalization

Introduce one normalization helper for symbol-resolution comparisons:

- uppercase;
- trim whitespace;
- preserve a canonical class-share separator;
- reject spaces and unsupported punctuation;
- cap length;
- do not silently remove arbitrary invalid characters.

Provider-specific conversion such as `BRK.B` versus `BRK-B` remains inside the
provider adapter. The resolution layer should use one documented internal
canonical form.

## 9. Reusable Symbol Search Service

The existing `/api/market/search` endpoint owns reusable search logic inside an
API module. Extract that logic into a service so agents and routes share the
same ranking and provider fallback.

Proposed component:

```text
backend/src/services/symbol_search_service.py
```

Responsibilities:

- search local universe and ticker directory;
- query configured provider fallbacks when local results are insufficient;
- normalize and deduplicate results;
- expose exact-symbol validation;
- return typed candidates;
- keep API-specific `HTTPException` handling out of the service.

The existing market search endpoint delegates to this service and retains its
current API response schema.

This avoids importing the private `_search_local_universe` helper from an API
module into the agent layer.

## 10. Backend Implementation Scope

### 10.1 New Components

| Component | Responsibility |
| --- | --- |
| `SymbolResolution` models | Typed resolution result and candidates |
| `SymbolSearchService` | Reusable local/provider symbol search |
| `SymbolResolver` | Resolution priority, thresholds, and LLM assistance |
| `create_clarification_event` | Stable SSE event formatting |

Suggested locations:

```text
backend/src/agent/symbol_resolver.py
backend/src/services/symbol_search_service.py
backend/src/api/schemas/symbol_resolution.py
```

The final paths may be adjusted to match existing module boundaries, but the
resolver must not depend directly on FastAPI.

### 10.2 Modified Components

#### `backend/src/agent/deep_agent_adapter.py`

- remove both `return "AAPL"` branches;
- remove inline symbol-extraction policy;
- receive or own a reusable `SymbolResolver`;
- expose symbol resolution before `deep_agent.analyze`;
- guarantee that `analyze` receives only a validated resolved symbol.

#### `backend/src/api/chat/streaming/deep_agent.py`

- resolve the symbol before creating the research task;
- emit and persist `clarification_required`;
- send `done` after clarification;
- do not create the deep event queue or call the graph for unresolved requests;
- preserve `route_selected` metadata.

#### `backend/src/api/market/search.py`

- delegate search behavior to `SymbolSearchService`;
- keep current endpoint response compatibility;
- remove duplicated or API-private search implementation after migration.

#### `backend/src/api/chat/streaming/helpers.py`

- add a clarification-event formatter or use the generic event formatter with
  a typed schema;
- do not represent clarification as an error.

#### Dependency Wiring

- build one resolver/service through FastAPI dependencies or application state;
- inject it into `DeepAgentAdapter`;
- keep construction testable without MongoDB, Redis, or live LLM access.

### 10.3 Persistence Behavior

The order is:

```text
persist user message
  -> prepare context
  -> resolve symbol
  -> if unresolved:
       persist assistant clarification
       emit clarification_required
       emit done
       return
  -> if resolved:
       start Deep Agent
```

The clarification assistant message should not be counted as a failed
analysis.

## 11. Frontend Implementation Scope

### 11.1 API Types

Add:

```typescript
export interface SymbolCandidate {
  symbol: string;
  name: string;
  exchange?: string;
  confidence: number;
}

export interface ClarificationRequiredEvent {
  type: "clarification_required";
  clarification_type: "symbol";
  reason_code:
    | "ambiguous_symbol"
    | "symbol_not_found"
    | "symbol_missing"
    | "symbol_resolution_invalid";
  message: string;
  original_request: string;
  candidates: SymbolCandidate[];
}
```

Include it in `StreamEvent` and `ChatMessage`.

### 11.2 Stream Client

Extend `sendMessageStreamPersistent` with:

```text
onClarificationRequired
```

The callback is invoked before `done`. Clarification must not call the error
callback or reject the request mutation.

### 11.3 Chat State

`useAnalysis` should:

- attach clarification metadata to the assistant placeholder;
- use the event message as the visible assistant content;
- resolve the mutation normally after `done`;
- avoid displaying the generic red error message;
- retain the original request for preparing a follow-up.

### 11.4 Clarification Card

Add a focused component:

```text
frontend/src/components/chat/SymbolClarificationCard.tsx
```

Behavior:

- show the clarification message;
- list up to five candidate buttons;
- display symbol, company name, and exchange;
- provide a “Search another symbol” action;
- remain accessible by keyboard;
- work in Chinese and English;
- render again after restoring chat history.

On candidate selection:

- update chart symbol and company name through the existing selection path;
- populate the composer with an explicit follow-up;
- do not automatically send.

### 11.5 Restoration

Update `messageParser` to extract:

```text
metadata.raw_data.clarification_required
```

Filter it out of generic `analysis_data`, just as with `deep_events` and
`route_selected`.

## 12. Localization Scope

Add Chinese and English keys for:

- unable to identify symbol;
- multiple possible companies;
- select a company;
- search another symbol;
- selected symbol confirmation;
- continue deep analysis;
- symbol-resolution service unavailable.

Do not return provider exception text directly to the user.

## 13. Logging and Observability

Log structured fields:

```text
resolution_status
resolution_source
reason_code
selected_symbol
candidate_count
confidence
duration_ms
```

Do not log the complete user request. A short sanitized preview may be retained
only if consistent with existing logging policy.

Metrics to expose later through the shared run model:

- resolution source distribution;
- clarification rate;
- unresolved rate;
- LLM-assistance rate;
- resolution latency;
- selected-candidate follow-up rate.

## 14. Error Handling

| Condition | Result |
| --- | --- |
| Valid UI symbol | Start research |
| Valid explicit ticker | Start research |
| One high-confidence validated company match | Start research |
| Multiple plausible matches | Clarification event |
| No candidates | Clarification event |
| LLM returns `UNKNOWN` | Clarification event |
| LLM output validation fails | Clarification event |
| LLM request times out | Clarification event |
| Local directory load fails but provider search works | Continue with provider |
| All symbol-search infrastructure fails | Error event |
| Deep Agent fails after successful resolution | Existing Deep Agent error path |

Expected uncertainty is not an exception. Infrastructure failure remains an
explicit error.

## 15. Detailed Implementation Steps

### Phase 1: Shared Search Foundation

- [ ] Define typed symbol search and resolution models.
- [ ] Extract local-universe search from the API module.
- [ ] Add exact-symbol validation.
- [ ] Preserve `/api/market/search` behavior.
- [ ] Add canonical symbol normalization.

### Phase 2: Resolver

- [ ] Implement UI-symbol resolution.
- [ ] Implement explicit-ticker resolution.
- [ ] Implement deterministic company-name ranking.
- [ ] Implement structured LLM candidate generation.
- [ ] Add confidence and score-margin policy.
- [ ] Remove all AAPL fallback branches.

### Phase 3: Backend Chat Integration

- [ ] Resolve before starting the deep graph.
- [ ] Add typed clarification SSE event.
- [ ] Persist clarification metadata and text.
- [ ] Finish the stream normally after clarification.
- [ ] Ensure zero deep tool or model calls occur after unresolved resolution.

### Phase 4: Frontend Integration

- [ ] Add TypeScript event types.
- [ ] Add stream callback.
- [ ] Render a symbol clarification card.
- [ ] Connect candidate selection to existing symbol context.
- [ ] Populate, but do not automatically submit, the follow-up message.
- [ ] Restore persisted clarification cards.
- [ ] Add localized strings.

### Phase 5: Validation and Documentation

- [ ] Add unit, integration, frontend, and manual tests.
- [ ] Add Playwright browser tests using deterministic SSE fixtures.
- [ ] Add a real local frontend-to-backend unresolved-symbol scenario.
- [ ] Capture and link curated screenshot evidence.
- [ ] Update automatic-routing documentation.
- [ ] Update chat-symbol-context documentation.
- [ ] Add a case study for the silent wrong-symbol failure.
- [ ] Update changelogs and component versions when implementation ships.

## 16. Test Plan

### 16.1 Backend Unit Tests

Create:

```text
backend/tests/test_symbol_resolver.py
```

Cases:

1. Valid `current_symbol` resolves without LLM.
2. Invalid `current_symbol` falls through to message resolution.
3. Explicit `TSLA` resolves without LLM.
4. Stop words such as `CEO` are not treated as tickers.
5. Class-share ticker normalization is deterministic.
6. Exact company-name search resolves one candidate.
7. Two close candidates return `ambiguous`.
8. Low-confidence candidates return `unresolved`.
9. LLM candidate output is validated against search results.
10. LLM `UNKNOWN` returns `unresolved`.
11. LLM malformed structured output returns `unresolved`.
12. LLM timeout returns `unresolved`.
13. No path returns `AAPL` unless AAPL was actually resolved.
14. Candidate output is deduplicated and capped at five.
15. Resolution thresholds behave correctly at boundary values.

### 16.2 Symbol Search Service Tests

Create or extend:

```text
backend/tests/test_symbol_search_service.py
```

Cases:

- local exact-symbol match;
- symbol-prefix and name-prefix ranking;
- deterministic tie ordering;
- duplicate removal across local data sources;
- provider fallback;
- provider failure with local success;
- complete infrastructure failure;
- API endpoint compatibility.

### 16.3 Deep Streaming Tests

Create:

```text
backend/tests/test_deep_agent_streaming.py
```

Cases:

- unresolved request emits `clarification_required` then `done`;
- ambiguous request includes validated candidates;
- assistant clarification message is persisted;
- route metadata is preserved;
- `deep_agent.analyze` is not called;
- no deep lifecycle events are emitted;
- resolved request continues through the existing deep path;
- resolver infrastructure failure emits an error rather than clarification.

### 16.4 Frontend Tests

Create or extend:

```text
frontend/src/services/__tests__/api.test.ts
frontend/src/components/chat/__tests__/SymbolClarificationCard.test.tsx
frontend/src/utils/__tests__/messageParser.test.ts
```

Cases:

- SSE parser dispatches clarification callback;
- clarification does not call the error callback;
- candidate card renders symbol, name, and exchange;
- keyboard selection works;
- selecting a candidate updates symbol context;
- selecting a candidate prepares but does not send the follow-up;
- no-candidate state displays symbol-search guidance;
- persisted clarification is restored;
- Chinese and English labels resolve.

### 16.5 Playwright End-to-End Tests

The implementation must establish or extend a standard Playwright harness:

```text
frontend/playwright.config.ts
frontend/e2e/uaw-001-symbol-clarification.spec.ts
```

Add scripts:

```json
{
  "test:e2e": "playwright test",
  "test:e2e:uaw-001": "playwright test e2e/uaw-001-symbol-clarification.spec.ts"
}
```

Because the current frontend image is Alpine-based and does not contain
Chromium system dependencies, the implementation uses a dedicated Docker
Compose profile based on the official Playwright image:

```text
mcr.microsoft.com/playwright
```

Expose a repository command:

```bash
make test-e2e
```

#### Deterministic Browser Scenarios

Use `page.route()` to return controlled SSE streams for states that are
difficult to reproduce reliably:

1. Ambiguous symbol renders multiple candidate buttons.
2. Unresolved symbol renders search guidance and no generic error.
3. Selecting a candidate updates chart context.
4. Selecting a candidate prepares a follow-up but does not submit it.
5. Restoring a chat renders the persisted clarification card.
6. A clarification stream contains no Deep Agent accordion or tool state.

These tests validate frontend behavior but must be labeled as mocked evidence.

#### Real Local-Stack Scenario

Run Chromium against the real Vite frontend and FastAPI backend:

1. Configure symbol-resolution LLM assistance off for deterministic testing.
2. Submit an unresolved deep-research request through the visible chat UI.
3. Allow the browser request to reach the real `/api/chat/stream` endpoint.
4. Assert that the clarification card appears.
5. Assert that no `deep_start`, tool progress, or error card appears.
6. Verify the clarification remains after reloading and restoring the chat.

The self-contained E2E profile starts an isolated backend on port `18081` with
MongoDB database `financial_agent_e2e`, Redis database `1`, symbol-resolution
LLM assistance disabled, and the E2E browser origin explicitly allowed.

The test may rewrite the outgoing debug request to the temporary
`v4-deep` compatibility override so routing-model availability does not make
the safety test flaky. It must not mock the backend clarification response.

#### Required Selectors

Add stable selectors:

```text
data-testid="symbol-clarification"
data-testid="symbol-candidate-<symbol>"
data-testid="symbol-search-another"
data-testid="chat-composer"
data-testid="deep-agent-accordion"
data-testid="chat-error"
```

Tests should combine `data-testid` with role-based assertions where practical.

### 16.6 Screenshot Evidence

Raw Playwright artifacts:

```text
frontend/test-results/
frontend/playwright-report/
```

These directories should be gitignored.

Curated acceptance evidence:

```text
docs/features/assets/uaw-001/
  01-ambiguous-symbol-candidates.png
  02-unresolved-symbol-real-stack.png
  03-candidate-selected-follow-up-ready.png
  04-restored-clarification.png
```

Screenshot rules:

- viewport: `1440x1000`;
- Chromium;
- animations disabled;
- mask timestamps, chat IDs, and provider-generated dynamic values;
- wait for all expected assertions before capture;
- capture the relevant application region, not the entire desktop;
- do not include API keys, tokens, logs, or environment values.

Screenshots are supporting evidence. Each scenario must still contain explicit
Playwright assertions.

### 16.7 Manual End-to-End Scenarios

Run from the frontend:

| Input | Expected result |
| --- | --- |
| `请深度分析 TSLA` | Research starts for TSLA |
| `Please deeply analyze Apple` | Resolves AAPL or asks to confirm if ranking is ambiguous |
| `请完整分析腾讯` | No AAPL fallback; candidate or unresolved clarification |
| `分析我昨天看到的公司` | Unresolved clarification |
| `Deeply analyze INVALID` | Invalid-symbol clarification |
| Selected chart symbol `NVDA` + `全面分析这家公司` | Research starts for NVDA |
| Resolver LLM unavailable | Clarification if deterministic search is insufficient |
| All search services unavailable | Explicit service error |

For every unresolved case, verify that no Deep Agent tool event appears.

## 17. Validation Commands

During implementation, run the smallest relevant commands first:

```bash
cd backend
python -m pytest \
  tests/test_symbol_resolver.py \
  tests/test_symbol_search_service.py \
  tests/test_deep_agent_streaming.py \
  tests/test_chat_symbol_context.py
python -m ruff check src/agent src/services src/api/chat src/api/market
python -m black --check src/agent src/services src/api/chat src/api/market
```

Frontend:

```bash
docker compose exec frontend npm test -- \
  src/services/__tests__/api.test.ts \
  src/components/chat/__tests__/SymbolClarificationCard.test.tsx \
  src/utils/__tests__/messageParser.test.ts
docker compose exec frontend npm run type-check
docker compose exec frontend npm run lint
```

Playwright:

```bash
make test-e2e
docker compose --profile e2e run --rm e2e \
  npm run test:e2e:uaw-001
```

Before completion:

```bash
make fmt
make test
make lint
```

Runtime verification:

```bash
curl -N -X POST http://localhost:18080/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "请完整分析我昨天看到的那家公司",
    "agent_version": "v4-deep",
    "language": "zh-CN"
  }'
```

The response must contain `clarification_required` and must not contain
`deep_start` or tool events.

## 18. Acceptance Criteria

The task is complete when:

- [ ] No code path defaults an unresolved symbol to `AAPL`.
- [ ] Deep research starts only with a validated symbol.
- [ ] Ambiguous and unresolved input produces a clarification event.
- [ ] Clarification is not treated as an error.
- [ ] Clarification text and metadata persist with chat history.
- [ ] Candidate symbols come from validated search results.
- [ ] The frontend renders and restores clarification cards.
- [ ] Candidate selection updates symbol context without automatic submission.
- [ ] Chinese and English clarification flows work.
- [ ] No Deep Agent model or tool call runs after unresolved resolution.
- [ ] Playwright covers deterministic clarification and candidate-selection
      scenarios.
- [ ] Playwright covers at least one real frontend-to-backend unresolved-symbol
      scenario.
- [ ] Required screenshot evidence is saved under
      `docs/features/assets/uaw-001/` and linked from this document.
- [ ] Existing valid-symbol Deep Agent behavior remains compatible.
- [ ] Targeted and full repository checks pass.
- [ ] Feature, architecture, case-study, changelog, and version docs are updated
      when implementation ships.

## 19. Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Resolver asks too many clarification questions | Poor UX | Calibrate confidence and margin thresholds with golden cases |
| Resolver auto-selects the wrong candidate | Incorrect analysis | Require validated search result and conservative thresholds |
| Search extraction changes existing API ranking | Frontend regression | Preserve endpoint contract and add compatibility tests |
| Chinese company names do not match English directory names | High unresolved rate | Use structured LLM candidate generation followed by validation |
| Candidate selection accidentally duplicates requests | Extra cost and duplicate history | Populate composer only; do not auto-submit |
| Provider outage prevents validation | Unavailable deep analysis | Prefer local directory, distinguish unresolved from infrastructure failure |
| Class-share ticker normalization breaks providers | Data-fetch failure | Keep provider-specific conversion inside provider adapters |
| Clarification metadata bloats messages | Storage noise | Cap candidates at five and omit unnecessary provider payloads |
| Mocked browser test passes while backend integration is broken | False confidence | Require one real local-stack Playwright scenario |
| Screenshot evidence becomes stale | Misleading review evidence | Capture from the shipping commit and record its hash |

## 20. Rollout and Rollback

This local application does not require a percentage rollout.

Rollout:

1. Ship backend resolver and compatibility tests.
2. Ship frontend event support in the same change set.
3. Restart backend and refresh the Vite frontend.
4. Run the manual scenarios above.
5. Monitor clarification and unresolved logs during normal use.

Rollback:

- revert the feature commit;
- do not restore silent AAPL fallback;
- if the UI must be rolled back independently, the persisted human-readable
  clarification message still provides a usable fallback.

Backend and frontend should ship together because older frontends do not render
candidate buttons, although they can still display the persisted text.

## 21. Dependencies

Required:

- existing local ticker directory and symbol search endpoint;
- existing `current_symbol` request field;
- existing SSE stream parser;
- existing chat-message persistence;
- configured router/simple LLM for LLM-assisted candidate generation.

Not required:

- unified Run model;
- research checkpointing;
- Langfuse;
- cloud services;
- new external data provider.

## 22. Follow-Up Tasks

The following are intentionally deferred:

1. Resume the original research run after candidate confirmation.
2. Store clarification as `waiting_for_input` in the unified Run model.
3. Propagate compacted conversation context into the Research Job.
4. Evaluate clarification resolution rate and threshold calibration.
5. Reuse the resolver from the future unified Conversational Engine.

## 23. Implementation Deliverables

Expected implementation change set:

```text
Backend:
  symbol resolution models
  reusable symbol search service
  symbol resolver
  Deep Agent integration
  clarification SSE and persistence
  backend tests

Frontend:
  event and message types
  stream callback
  clarification card
  composer/symbol integration
  restoration support
  localization
  frontend tests
  Playwright configuration and E2E specification

Documentation:
  feature status/version update
  architecture and symbol-context update
  case study
  curated Playwright screenshots
  backend/frontend changelogs
```
