---
title: Chat Symbol Context
status: shipped
version: backend@0.30.x, frontend@0.23.x
last_updated: 2026-07-13
owner: maintainer
related_paths:
  - backend/src/api/chat/helpers.py
  - backend/src/api/chat/streaming/react_agent.py
  - backend/src/api/chat/streaming/simple_agent.py
  - frontend/src/components/EnhancedChatInterface.tsx
  - frontend/src/hooks/useUIStateSync.ts
---

# Chat Symbol Context

The selected chart symbol is sent with every chat request as
`current_symbol`. This avoids a race between the debounced UI-state write and
the next agent invocation.

## Flow

1. `EnhancedChatInterface` tracks the selected symbol.
2. `useAnalysis` passes it to `sendMessageStreamPersistent`.
3. `ChatRequest.current_symbol` carries it to the backend.
4. `get_active_symbol_instruction` appends a short symbol instruction to the
   user message.
5. The same symbol is persisted in the chat `UIState` for restoration.

The explicit request value takes priority over stored UI state. If it is
missing, the backend falls back to the chat's persisted symbol.

The deep agent receives the same value through `DeepAgentAdapter`, using it
before regex or LLM-based symbol extraction.

## Relevant Tests

- `backend/tests/test_chat_symbol_context.py`
- `frontend/src/hooks/useUIStateSync.ts`

See [Architecture Overview](../architecture/overview.md) for the complete chat
request flow.
