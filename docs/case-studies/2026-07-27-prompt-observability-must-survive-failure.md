---
title: Prompt Observability Must Survive Failure
status: shipped
version: backend@0.45.0
last_updated: 2026-07-27
owner: maintainer
related_paths:
  - backend/src/agent/deep_react_agent.py
  - backend/src/api/chat/streaming/deep_agent.py
---

# Prompt Observability Must Survive Failure

> **TL;DR (EN)**: Recording prompt versions only from a successful final graph
> state loses the prompts used before a later failure or cancellation.
> Request-local prompt-used signals now persist versions on every terminal
> path without blocking cleanup.
>
> **TL;DR (中文)**：只从成功的 final graph state 记录 prompt，会丢失失败或
> 取消前已经执行的 prompt。现在使用 request-local prompt-used 信号，在所有
> 终态路径保存版本，同时不阻塞清理。

## Lesson

Observability emitted only at successful completion systematically hides the
most important failed executions.
