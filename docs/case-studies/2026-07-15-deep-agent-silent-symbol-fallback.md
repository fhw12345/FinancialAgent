---
title: Deep Agent Silent Symbol Fallback
status: shipped
version: backend@0.32.0, frontend@0.25.0
last_updated: 2026-07-15
owner: maintainer
related_paths:
  - backend/src/agent/deep_agent_adapter.py
  - backend/src/agent/symbol_resolver.py
  - backend/src/api/chat/streaming/deep_agent.py
  - frontend/src/components/chat/SymbolClarificationCard.tsx
---

# Deep Agent Silent Symbol Fallback

> **TL;DR (EN)**: Deep research silently analyzed AAPL whenever ticker
> extraction returned `UNKNOWN` or failed. We replaced the default with a
> validated resolution boundary and a persisted clarification workflow,
> verified through unit tests and real-stack Playwright screenshots.
>
> **TL;DR (中文)**：Deep Agent 无法识别股票时会静默改为分析 AAPL，生成内容完整
> 但对象错误的报告。修复后只有经过验证的 ticker 才能启动研究；不确定输入会要求用户
> 确认，并通过真实 Playwright 浏览器路径和截图验证。

## 1. Context

Deep research needs one concrete US stock symbol before it can launch technical,
financial, news, and adversarial sub-agents. The original adapter tried UI
context, an uppercase regex, and one LLM extraction call.

The implementation treated extraction uncertainty as availability:

```text
UNKNOWN or exception -> AAPL
```

This kept demonstrations moving, but it converted missing information into a
confidently wrong company selection.

## 2. Investigation

The architecture review followed the complete execution path:

```text
chat router
  -> deep streaming handler
  -> DeepAgentAdapter
  -> symbol extraction
  -> DeepReActAgent.analyze
```

The important discovery was that the fallback happened before any tool call.
Every downstream component behaved correctly for the symbol it received, so
additional tool validation or debate rounds could not recover from the wrong
initial identity.

The existing symbol-search endpoint already had a useful local/provider
fallback chain, but that logic lived inside the FastAPI module and could not be
reused cleanly by the agent.

## 3. Root Cause

Three design choices combined:

1. Symbol extraction returned a plain string rather than a typed resolution
   state.
2. LLM output was accepted without validating the ticker against the market
   directory.
3. Uncertainty was represented by a default value instead of a user-visible
   control-flow state.

The tests covered known tickers and UI context but did not assert the negative
requirement:

> No research work may start when the symbol is unresolved.

## 4. Fix

The fix introduced:

- `SymbolCandidate` and `SymbolResolution`;
- reusable `SymbolSearchService`;
- `SymbolResolver` with UI, explicit ticker, deterministic search, and
  structured LLM-assisted candidates;
- mandatory candidate validation;
- `clarification_required` SSE and persistence;
- a frontend candidate card and restoration support.

The Deep Agent handler now resolves the symbol before creating the graph task.
For ambiguous or unresolved requests it persists the clarification, emits
`done`, and returns without invoking `DeepReActAgent`.

Playwright verifies:

- ambiguous candidate rendering;
- selection without automatic duplicate submission;
- real frontend-to-backend unresolved behavior;
- clarification restoration after reload.

Evidence is linked from
[Deep Agent Symbol Clarification](../features/deep-agent-symbol-clarification.md).

## 5. Lessons

### Uncertainty is a state, not a default

Expected ambiguity should use a typed state such as `waiting_for_input`, not an
exception and never an unrelated default.

### Validate identity before expensive reasoning

Grounding tools cannot correct an analysis that starts with the wrong entity.
Identity resolution belongs before the agent graph.

### LLM extraction should propose, not authorize

The LLM may translate aliases or multilingual company names into candidates.
The deterministic directory/provider layer decides whether those candidates
exist.

### Browser evidence catches integration gaps

The first real-stack Playwright run reached FastAPI but failed in the browser
because the isolated E2E origin was not covered by the active CORS override.
Unit and API tests could not reveal that browser boundary. The final scenario
proved SSE, persistence, CORS, frontend rendering, and restoration together.
The final Compose profile starts its own backend, database namespace, Redis
database, CORS policy, Vite frontend, and Chromium runner so the proof no
longer depends on an externally started process.
