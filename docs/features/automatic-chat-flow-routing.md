---
title: Automatic Chat Flow Routing
status: shipped
version: backend@0.32.0, frontend@0.25.0
last_updated: 2026-07-15
owner: maintainer
related_paths:
  - backend/src/agent/flow_router.py
  - backend/src/api/chat/streaming/handlers.py
  - frontend/src/components/EnhancedChatInterface.tsx
  - frontend/src/services/api.ts
---

# Automatic Chat Flow Routing

The Platform page no longer asks users to select or lock an execution mode.
Every free-form user message sends `agent_version=auto`; the backend chooses the
appropriate flow from the utterance and frontend symbol context.

## Hybrid Routing

Rules handle unambiguous requests without an extra model call:

- explicit comprehensive/deep investment research → `v4-deep`
- current prices, news, fundamentals, or technical tools → `v3`
- concept explanations and summaries without a live-data intent → `v2`
- references such as “this stock” use `current_symbol` only when the utterance
  actually requests analysis

Ambiguous requests are classified by the `router` LLM role with temperature
zero and a small output budget. Invalid output, timeouts, or provider errors are
logged and fall back to `v3`, the safest tool-capable flow.

## Transparency and Persistence

Before the selected handler streams its own events, the backend emits:

```json
{
  "type": "route_selected",
  "flow": "v3",
  "source": "rule",
  "reason_code": "live_data_or_tool_request"
}
```

The same object is stored under the assistant message's
`metadata.raw_data.route_selected`. The frontend displays a localized flow
badge and reason above the input, and restores the latest selection with chat
history. Deep-agent events remain independently persisted and replayed.

## Direct Analysis Buttons

Fibonacci, stochastic, overview, cash-flow, balance-sheet, macro, news, and
market-mover buttons continue to call deterministic `/api/analysis/*` routes.
Their message-persistence requests bypass the router and never incur a routing
LLM call.

## Deep-Research Symbol Clarification

Automatic routing may select deep research before a symbol is known. The Deep
Agent now validates UI context, explicit tickers, directory matches, and
LLM-assisted candidates before starting research. Ambiguous or unresolved
requests emit and persist `clarification_required`; they never silently default
to AAPL.

See
[Deep Agent Symbol Clarification](deep-agent-symbol-clarification.md).

## Compatibility

Explicit `v2`, `v3`, and `v4-deep` request values remain available for API
debugging and tests. The normal frontend does not expose them.
