---
title: A Typewriter Effect Was Reported as Model Streaming
status: shipped
version: backend@0.37.0, frontend@0.26.1
last_updated: 2026-07-17
owner: maintainer
related_paths:
  - backend/src/api/chat/streaming/simple_agent.py
  - backend/src/api/chat/streaming/react_agent.py
  - backend/src/api/chat/streaming/deep_agent.py
  - frontend/src/components/EnhancedChatInterface.tsx
  - frontend/e2e/uaw-006-streaming-semantics.spec.ts
---

# A Typewriter Effect Was Reported as Model Streaming

> **TL;DR (EN)**: Direct chat consumed real provider chunks, but ReAct and Deep
> generated the full answer and split it into ten-character pieces with
> artificial delays. The UI and telemetry treated both as streaming. We now
> declare `model_tokens` versus `buffered`, use truthful latency names, and
> removed the typewriter simulation.
>
> **TL;DR (中文)**：Direct chat 使用真实 provider chunk，但 ReAct 和 Deep
> 先生成完整答案，再按十字符切分并人工延迟。UI 与 telemetry 却把两者都称为
> streaming。修复后明确区分 `model_tokens` 与 `buffered`，使用真实 latency
> 名称，并移除 typewriter 模拟。

## 1. Context

All chat flows visually appeared to stream text.

This suggested that users were seeing model output as it was generated and
that “time to first token” represented provider latency.

## 2. Investigation

Direct chat used:

```python
async for chunk in agent.stream_chat(...):
    yield chunk
```

ReAct and Deep used:

```python
for i in range(0, len(final_answer), 10):
    yield final_answer[i : i + 10]
    await asyncio.sleep(0.03)
```

The model or graph had already finished before the first answer character was
sent.

Deep also mixed its first live sub-agent progress event with response TTFT.

## 3. Root Cause

The transport contract had only one generic `chunk` shape and no declaration
of where those chunks came from.

Presentation animation and model streaming were therefore indistinguishable.

## 4. Fix

Every handler now emits:

```text
response_stream_mode=model_tokens
```

or:

```text
response_stream_mode=buffered
```

Direct retains true provider streaming and records `first_model_token`.

ReAct and Deep:

- keep tool/sub-agent progress live;
- send one complete final response chunk;
- record `first_response_chunk`;
- remove artificial response sleeps.

Deep records `first_progress_event` separately.

The frontend renders a transparent mode badge and clears it when switching or
creating chats.

## 5. Lessons

### Chunked transport is not necessarily model streaming

The origin and timing of each chunk matter more than its SSE envelope.

### Progress and response streams are independent

A Deep graph can provide useful live progress while its final verdict remains
buffered.

### Metrics need semantic names

`first_model_token`, `first_progress_event`, and `first_response_chunk` answer
different operational questions. A generic TTFT number hides that difference.

### Honest UX is better than animation

One buffered response chunk with a clear label is more trustworthy than an
artificial typewriter effect.
