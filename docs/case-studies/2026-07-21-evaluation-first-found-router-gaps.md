---
title: The First Golden Suite Found Router Gaps
status: shipped
version: backend@0.42.0
last_updated: 2026-07-21
owner: maintainer
related_paths:
  - backend/src/evals/cases_v1.py
  - backend/src/evals/runner.py
  - backend/src/agent/flow_router.py
---

# The First Golden Suite Found Router Gaps

> **TL;DR (EN)**: The first evaluation harness initially looked healthy only
> because explicit overrides and accidental live classifier calls inflated
> the score. After isolating automatic routing and forbidding model access, the
> honest baseline was 74.5%. Unknown-symbol safety remained 100%.
>
> **TL;DR (中文)**：首版 evaluation 因 explicit override 和意外 live
> classifier 调用而显得分数很好。隔离 auto routing 并禁止模型访问后，真实
> baseline 是 74.5%，unknown-symbol safety 保持 100%。

## 1. Context

The project had many unit tests but no versioned cross-workflow baseline.

## 2. Investigation

The first runner reused the production router without injecting a classifier.
Ambiguous cases silently invoked a live model. Explicit Deep overrides also
counted as router successes even though no routing decision occurred.

## 3. Root Cause

The metric mixed rules, live classification, and explicit user overrides.
The symbol-safety check also tested only the selected flow rather than the
actual resolver.

## 4. Fix

Deterministic evaluation now injects a classifier that cannot call a model,
scores only automatic-routing cases, and executes the real symbol resolver
with empty validated search results and LLM resolution disabled.

## 5. Lessons

An evaluation that cannot fail independently is documentation, not a gate.
Baselines should expose current weaknesses rather than edit cases to produce a
perfect score.
