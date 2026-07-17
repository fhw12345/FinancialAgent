---
title: Deep Research Received History but Ignored It
status: shipped
version: backend@0.34.0, frontend@0.25.2
last_updated: 2026-07-17
owner: maintainer
related_paths:
  - backend/src/agent/deep_research_context.py
  - backend/src/agent/deep_agent_adapter.py
  - backend/src/agent/deep_react_agent.py
  - frontend/e2e/uaw-003-deep-context.spec.ts
---

# Deep Research Received History but Ignored It

> **TL;DR (EN)**: The Deep streaming handler loaded MongoDB history and passed
> it to the adapter, but the adapter only logged its length. The graph's
> specialist prompts were generic and did not even include the current user's
> detailed request. We added a bounded structured research context shared by
> every graph node and proved follow-up continuity through a browser reload.
>
> **TL;DR (中文)**：Deep handler 已从 MongoDB 读取历史并传给 adapter，但 adapter
> 只记录长度，没有把内容交给 graph。各 specialist prompt 甚至没有完整包含当前用户的
> 具体要求。修复后，每个 graph node 都共享有边界的结构化研究上下文，并通过浏览器
> reload 验证了 follow-up 连续性。

## 1. Context

The user-facing workflow supported multiple messages in one chat, but Deep
Research behaved as if every request were the first:

```text
User: Analyze SKHY over six months with moderate risk.
Assistant: [full Deep report]
User: Now challenge that thesis and focus on downside.
```

The second request launched a fresh generic research process.

## 2. Investigation

The streaming handler correctly prepared prior MongoDB history. The adapter
accepted `conversation_history`, then logged:

```text
received conversation history, not forwarded
```

`DeepReActAgent.analyze` placed the current request in an initial HumanMessage,
but `main_agent_node` constructed independent prompts:

```text
Analyze the technical setup for SYMBOL.
Analyze recent news for SYMBOL.
Analyze the fundamentals of SYMBOL.
```

Those prompts ignored both prior context and most current-turn constraints.

## 3. Root Cause

The API contract implied multi-turn support, but the graph had no typed
representation of conversational research intent.

Passing a transcript list into an adapter was not sufficient. The graph needed
explicit fields for:

- current request;
- prior thesis;
- horizon;
- risk tolerance;
- constraints;
- confirmed symbol.

## 4. Fix

`DeepResearchContext` now:

- keeps at most six recent turns;
- drops the oldest turns first when the total context budget is exhausted;
- caps each turn, current request, and complete rendered context;
- extracts English and Chinese horizon/risk expressions;
- gives current-turn horizon, risk, and focus constraints precedence;
- identifies valuation, downside, technical, fundamental, news-exclusion, and
  adversarial constraints;
- shares ticker parsing with the production resolver and validates historical
  candidates before reuse;
- renders compact specialist context and full synthesis context;
- filters specialist execution for technical-only, valuation/fundamental-only,
  and exclude-news requests;
- scopes extracted settings and prior reports to the latest validated-symbol
  segment;
- persists compact metadata rather than duplicating the full report.

The context block is included in every specialist and synthesis prompt.

A deterministic Deep adapter was used only for expensive graph execution in
Playwright. The browser, FastAPI handlers, MongoDB, context preparation,
streaming, persistence, reload, and routing remained real.

The E2E test also caught a semantic bug:

```text
challenge the thesis more aggressively
```

was initially parsed as aggressive investor risk tolerance. English risk
markers now require word boundaries, while `challeng*` maps to adversarial
review.

Final review also found that:

- oldest-first budget consumption dropped the newest assistant report;
- assistant acronyms such as `HOLD` could become ticker candidates;
- a UI-selected symbol incorrectly overrode an explicit ticker in the current
  request;
- ordinary financial acronyms could incorrectly override UI context while
  valid word-like tickers such as `LOW` could be suppressed;
- extracted exclusive constraints were recorded but did not initially prevent
  conflicting specialists from running;
- switching from one symbol to another initially retained the old symbol's
  thesis and settings;
- the multi-turn Playwright scenario needed an explicit test-level timeout;
- the dedicated UAW-003 runner needed `--no-deps` to avoid starting unrelated
  E2E services.

## 5. Lessons

### Accepting context is not using context

Trace the information to the actual model prompt, not merely through function
arguments.

### Structure prevents prompt ambiguity

Current request, historical thesis, and persistent constraints need explicit
labels and precedence.

### Context must be bounded before fan-out

Copying a full transcript into three specialists plus debate and verdict would
multiply token cost. One bounded context contract controls that fan-out.

### Recency must survive every budget

A context window that retains old turns while dropping the newest answer is
bounded but semantically wrong. Accumulate newest-first, then restore
chronological order for rendering.

### Validate candidates, not guesses

Uppercase text in financial reports contains actions and acronyms as well as
tickers. Shared parsing plus normal symbol validation prevents an untrusted
historical token from becoming UI context.

### Target history is not global history

When the resolved symbol changes, prior thesis text must be discarded. Only
structured settings that the user explicitly asks to reuse should cross the
symbol boundary.

### Natural language markers need semantic boundaries

“Aggressively review” and “aggressive risk tolerance” contain similar words
but represent different user intent.
