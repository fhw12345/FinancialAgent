---
title: Two Conversation State Owners Meant One Was Fictional
status: shipped
version: backend@0.33.0, frontend@0.25.1
last_updated: 2026-07-16
owner: maintainer
related_paths:
  - backend/src/services/conversation_context_service.py
  - backend/src/agent/langgraph_react_agent.py
  - backend/src/api/chat/streaming/
  - frontend/src/components/EnhancedChatInterface.tsx
---

# Two Conversation State Owners Meant One Was Fictional

> **TL;DR (EN)**: The ReAct agent advertised LangGraph `MemorySaver` continuity
> while generating a fresh thread ID for every request and manually replaying
> MongoDB history. MongoDB was the real state owner. We removed the decorative
> checkpointer, prepared history by persisted message ID, and proved
> multi-turn continuity across browser reload and backend restart.
>
> **TL;DR (中文)**：ReAct Agent 声称使用 LangGraph `MemorySaver` 保持连续性，
> 但每次请求都会生成新 thread ID，同时又手工重放 MongoDB 历史。真正的状态权威一直
> 是 MongoDB。修复后移除了无效 checkpointer，按持久化 message ID 准备上下文，并通过
> 浏览器刷新和 backend 重启验证了多轮连续性。

## 1. Context

The conversational ReAct agent compiled with:

```python
checkpointer=MemorySaver()
```

but every invocation generated:

```text
thread_<timestamp>_<random UUID>
```

The streaming handler separately read every persisted chat message from
MongoDB and supplied it as `conversation_history`.

## 2. Investigation

Tracing one follow-up request showed:

```text
MongoDB messages
  -> compact_context_if_needed
  -> conversation_history
  -> HumanMessage / AIMessage conversion
  -> new LangGraph thread ID
```

Because no thread ID was reused, `MemorySaver` never restored previous graph
state. Removing Mongo history made the model forget prior turns; removing
MemorySaver changed nothing across requests.

The current user message was removed from v3 history by comparing text:

```python
history[-1]["content"] == request.message
```

That was also unsafe because identical consecutive user messages are valid.

## 3. Root Cause

The code mixed two different kinds of state:

- user-visible conversational history;
- transient graph execution state.

MongoDB correctly owned the first. `MemorySaver` was intended for the second
but was described as if it also owned the first.

## 4. Fix

UAW-002 established:

```text
MongoDB = cross-request conversation authority
LangGraph = within-request ReAct execution
```

The new `ConversationContextService`:

- excludes the current turn by persisted `message_id`;
- preserves an earlier identical message;
- applies symbol context once;
- reports history and token metrics;
- persists a compaction summary before deleting explicit BODY IDs.

The ReAct graph now compiles without a checkpointer or thread ID.

A deterministic Anthropic-compatible stub drove real browser tests:

1. remember `ORBIT-742`;
2. recall it on the next turn;
3. reload the page and restore the chat;
4. repeat identical user text without dropping the earlier turn;
5. restart only the backend;
6. recall the codeword again from MongoDB.

The restart test also exposed a frontend race: the restored messages could
appear before the selected chat ID reached the send mutation. The composer now
stays disabled during restoration and the selected ID is bound immediately.

## 5. Lessons

### State needs one authority per lifecycle

Conversation messages and resumable research execution are different state.
They should not share an ambiguous “memory” label.

### Message identity beats content equality

Two identical messages are still two distinct events. Exclusion and deletion
must use IDs.

### Restart tests reveal architectural truth

An in-memory feature can look correct until the process is recreated. The
two-phase Playwright test demonstrated that continuity survives with no graph
checkpoint.

### E2E infrastructure can expose product races

The backend restart proof found a real restored-chat synchronization bug that
unit tests and ordinary page reload tests had not caught.
