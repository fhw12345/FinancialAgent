---
title: A Green Eval Can Still Be Fiction
status: shipped
version: backend@0.51.0, frontend@0.32.0
last_updated: 2026-08-04
owner: maintainer
related_paths:
  - backend/src/evals/
  - backend/src/api/evaluations.py
  - backend/src/agent/symbol_resolver.py
  - frontend/src/pages/EvaluationPage.tsx
  - frontend/e2e/evaluation-governance.spec.ts
---

# A Green Eval Can Still Be Fiction

> **TL;DR (EN)**: The deterministic dashboard was green, but it did not run
> production Prompts, autonomous tools, model answers, or paid-call accounting.
> Building a replay-live lane exposed additional false-green paths: injected
> tickers were excluded rather than resisted, provider failures looked like
> successful tools, invalid Judge output lost billed usage, and multi-step
> ReAct calls could cross a budget between checks.
>
> **TL;DR (中文)**：原有 deterministic Dashboard 虽然全绿，但没有真正执行生产
> Prompt、自主工具选择、模型回答或付费调用记账。构建 replay-live Lane 后又发现
> 多个 false-green 路径：注入 ticker 被绕开而不是被生产逻辑抵抗、Provider 失败
> 文本被当作成功工具证据、无效 Judge 输出会丢失已计费 Token、多步 ReAct 可能在
> 两次预算检查之间越过成本上限。

## 1. Context

The first governance layer was intentionally deterministic. It was fast,
repeatable, free, and useful for router and symbol-safety regressions. Its
limitation became a problem when the report was interpreted as proof of full
Agent quality.

The next iteration needed to evaluate the actual boundaries that create risk:

- production Prompt rendering and model routing;
- autonomous selection of production-named tools;
- answer grounding against known evidence;
- an independent structured Judge;
- token, latency, and cost accounting;
- persistence of paid progress and browser-visible evidence.

## 2. Investigation

The first replay-live implementation passed unit tests and the browser
scenario, but a specialist review found that several tests could still be
green while production behavior was wrong:

- the Prompt Injection clarification case returned a hard-coded safe answer
  before the production symbol resolver ran;
- a tool returning `No quote data available for AAPL` was marked successful;
- the smoke case accepted only `get_stock_quote` even though production could
  correctly choose the equivalent `finnhub_quote`;
- router or Judge validation happened before raw-response usage was retained;
- one target reservation covered a ReAct graph that could make several model
  calls;
- MongoDB stored only the empty initial report and final report;
- the browser stopped polling after five minutes even though configured run
  limits could legitimately exceed that duration.

## 3. Root Cause

The evaluator originally modeled desired outcomes, not the complete lifecycle
that produces them. Several helpers generated success-shaped evidence instead
of observing production behavior.

Cost policy was also treated as a report-level calculation. A multi-step Agent
needs a guard immediately before every model call, and failures after a paid
response must retain that response's usage even when structured parsing fails.

Finally, tool invocation is not the same as successful evidence. Provider
tools commonly encode degraded or unavailable data as normal text, so the
evaluation layer must classify the output and require source identity.

## 4. Fix

- Added replay-live target and independent Judge calls using production Prompt
  and role routes.
- Routed clarification cases through the production symbol resolver with
  explicitly tagged untrusted evidence and valid ticker fixtures.
- Added deterministic replay tools with fixed source IDs and rejected unknown
  fixture symbols.
- Added tool capability aliases, failure-output detection, source requirements,
  arguments, outputs, provider identity, and latency evidence.
- Added preflight run/case reservations plus a model callback that blocks the
  next unaffordable ReAct call.
- Retained raw router/Judge usage before structured-output validation.
- Persisted a running report after each case and expired interrupted stale
  runs without deleting retained cost or evidence.
- Added backend capability discovery and run-aware browser polling.
- Added detailed localized UI evidence and three Playwright screenshots.

The implementation shipped in commit `4530fb3`.

## 5. Lessons

- A green evaluator is trustworthy only when it exercises the production
  boundary it claims to measure.
- Model validation errors can still be billable events.
- Tool-call presence is not evidence quality; success, source, and capability
  all matter.
- Budget enforcement belongs before every potentially paid call, not only in a
  final report.
- Long-running local tasks still need progress checkpoints and stale-run
  recovery.
- Fake-live browser tests are valuable when they exercise the same lifecycle
  without making paid provider calls.
