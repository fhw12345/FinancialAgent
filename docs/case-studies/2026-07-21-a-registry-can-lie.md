---
title: A Prompt Registry Can Lie
status: shipped
version: backend@0.43.0
last_updated: 2026-07-21
owner: maintainer
related_paths:
  - backend/src/agent/prompt_registry.py
  - backend/src/agent/flow_router.py
  - backend/src/evals/runner.py
---

# A Prompt Registry Can Lie

> **TL;DR (EN)**: Registering version names for prompts that still execute from
> unrelated inline strings creates false observability. The registry was
> narrowed to the router prompt actually rendered through it, and evaluation
> reports now list only versions they exercise.
>
> **TL;DR (中文)**：如果实际执行的 prompt 仍来自其他 inline string，只登记
> version 名称会制造虚假可观测性。最终 registry 只保留真正通过它渲染的
> router prompt，evaluation 也只报告实际覆盖的版本。

## Root Cause

Version metadata was treated as configuration documentation rather than proof
of the exact prompt used at invocation time.

## Fix

The router now renders `router@1` from the registry and uses Pydantic structured
output. Unmigrated prompts keep their existing compatibility metadata until
their call sites move behind the registry.

## Lesson

A smaller truthful registry is more useful than a comprehensive list detached
from runtime behavior.
