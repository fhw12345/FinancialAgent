---
title: Singleton Prompt Metadata Crossed Requests
status: shipped
version: backend@0.44.0
last_updated: 2026-07-27
owner: maintainer
related_paths:
  - backend/src/agent/symbol_resolver.py
  - backend/src/agent/deep_agent_adapter.py
  - backend/src/api/chat/streaming/deep_agent.py
---

# Singleton Prompt Metadata Crossed Requests

> **TL;DR (EN)**: Tracking the last used prompt on a singleton resolver worked
> sequentially but concurrent Deep requests could clear or inherit each
> other's metadata. Prompt usage now travels on the request's typed
> `SymbolResolution` and is merged into that run only.
>
> **TL;DR (中文)**：把最后使用的 prompt 存在 singleton resolver 上，在并发
> Deep 请求中会互相清空或串用。现在 prompt usage 随请求自己的
> `SymbolResolution` 返回，只合并到对应 run。

## Lesson

Observability metadata is request state. Process-wide agent singletons may own
immutable configuration, but must not own mutable per-request facts.
