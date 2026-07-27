---
title: Skipped Prompts Are Not Used Prompts
status: shipped
version: backend@0.46.0
last_updated: 2026-07-27
owner: maintainer
related_paths:
  - backend/src/agent/portfolio/consistency_gate.py
  - backend/src/agent/portfolio/flows.py
---

# Skipped Prompts Are Not Used Prompts

> **TL;DR (EN)**: Portfolio runs previously advertised gate prompt versions
> even when clean research skipped the gate LLM entirely. Prompt usage now
> originates from the structured verdict only after the call executes.
>
> **TL;DR (中文)**：过去即使 clean research 完全跳过 gate LLM，也可能提前
> 声明 gate prompt version。现在只有实际执行后返回的 structured verdict
> 才携带版本。

## Lesson

Configuration availability and runtime usage are different observability
facts. Durable metadata should record the latter.
