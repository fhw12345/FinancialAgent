---
title: One Stream Had Many Event Shapes
status: shipped
version: backend@0.40.0, frontend@0.28.0
last_updated: 2026-07-21
owner: maintainer
related_paths:
  - backend/src/api/schemas/agent_events.py
  - backend/src/api/chat/streaming/handlers.py
  - frontend/src/types/agentEvents.ts
  - frontend/src/services/api.ts
---

# One Stream Had Many Event Shapes

> **TL;DR (EN)**: Routing, tools, Deep progress, chunks, and terminal state all
> used unrelated SSE shapes and only Deep had local sequence numbers. Wrapping
> the unified endpoint at its outer boundary produced one run-wide ordering
> without rewriting three engines. The frontend now unwraps and deduplicates
> envelopes while retaining existing callbacks.
>
> **TL;DR (中文)**：routing、tool、Deep progress、chunk 和终态使用不同 SSE
> 结构，只有 Deep 拥有局部序号。最终在 unified endpoint 最外层统一封装，
> 不重写三个 engine 就获得了 run 级全局顺序；前端负责解包和去重，同时保留
> 现有 callback。

## 1. Context

The frontend needed a separate branch for every legacy event. Events could not
be safely deduplicated or correlated across routing, tools, research, and the
final response.

## 2. Investigation

Changing every producer would have duplicated sequence ownership across
callbacks and sub-agents. The shared lifecycle also did not see every tool and
Deep event.

The one place that sees the complete ordered stream is the outer unified
response wrapper.

## 3. Root Cause

Event formatting evolved inside individual features rather than at the API
contract boundary. Deep's `seq` described only Deep progress, not the complete
user request.

## 4. Fix

The outer stream now assigns one contiguous sequence and canonical type to
every internal SSE block. The original event remains in `payload`.

The frontend recognizes schema `1.0`, rejects duplicate/lower sequence events,
and normalizes the payload into existing callbacks.

Envelope-processing failures are persisted as failed before the inner
generator is closed, preventing cancellation cleanup from changing the result
to cancelled.

## 5. Lessons

### Ordering needs one owner

Sequence numbers allocated by multiple engines or callbacks cannot guarantee a
single stream order.

### Standardization belongs at the boundary

An outer adapter can provide a stable contract while internal implementations
migrate independently.

### Cleanup errors need terminal precedence

Failure persistence must finish before generator closure triggers cancellation
cleanup.
