---
title: Prompt Registry Foundation
status: shipped
version: backend@0.43.0
last_updated: 2026-07-21
owner: maintainer
related_paths:
  - backend/src/agent/prompt_registry.py
  - backend/src/agent/flow_router.py
  - backend/src/evals/runner.py
---

# P1: Prompt Registry Foundation

## Goal

Create a truthful prompt registry and migrate the first machine decision,
automatic routing, to a versioned registry prompt with Pydantic structured
output.

## Delivered

- stable `router@1` identity and renderer;
- router no longer parses JSON from free-form Markdown;
- invalid structured output uses the existing explicit fallback;
- evaluation reports list only prompt versions actually covered;
- no un-migrated Deep or Portfolio prompt receives a misleading registry
  version.

## Acceptance Criteria

- [x] Registry lookup, rendering, versioning, and unknown-ID errors are tested.
- [x] Router uses registry rendering.
- [x] Router decision uses Pydantic structured output.
- [x] Structured-output failure falls back explicitly.
- [x] Evaluation reports only `router@1` as covered.
- [x] Existing run prompt-version compatibility remains unchanged.
- [x] Full backend validation passes.

## Follow-Up

Migrate symbol extraction, shared financial system prompt, Deep planning,
debate/verdict, Portfolio phase 2, and consistency gate one at a time with
their related golden cases.

## Implementation Record

Shipped in implementation commit `463aaef`, backend `0.43.0`.
