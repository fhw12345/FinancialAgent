---
title: One Logical Request Could Start Two Expensive Runs
status: shipped
version: backend@0.41.0, frontend@0.28.1
last_updated: 2026-07-21
owner: maintainer
related_paths:
  - backend/src/database/repositories/agent_run_repository.py
  - backend/src/api/chat/streaming/handlers.py
  - frontend/src/services/api.ts
---

# One Logical Request Could Start Two Expensive Runs

> **TL;DR (EN)**: Stable terminal message IDs prevented duplicate assistant
> rows only after execution had already happened. A unique client request ID
> now atomically selects one execution winner; retries replay the existing run
> instead of repeating routing, tools, or research.
>
> **TL;DR (中文)**：稳定 terminal message ID 只能在执行完成后避免重复
> assistant row，无法阻止昂贵任务被执行两次。现在由 client request ID
> 原子选出唯一执行者，重试只重放现有 run。

## 1. Context

Network retries or duplicate POSTs created new run IDs, duplicate user
messages, and repeated model/tool work.

## 2. Root Cause

Idempotency existed only at terminal assistant-message persistence. There was
no uniqueness gate before routing and execution.

## 3. Fix

`agent_runs.request_id` is a unique partial index. The first insert owns
execution; duplicate writers load the existing run and replay status or
terminal content.

Replay uses the same durable run ID and a new stream ID so sequence identities
cannot conflict with the original delivery.

## 4. Lessons

Idempotency must guard the expensive side effect, not only its final database
row. Run identity and stream-delivery identity are related but distinct.
