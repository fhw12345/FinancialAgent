---
title: Aggregate Gates Can Hide Router Gaps
status: shipped
version: backend@0.50.0, frontend@0.31.0
last_updated: 2026-08-03
owner: maintainer
related_paths:
  - backend/src/evals/runner.py
  - backend/src/evals/cases_v2.py
  - backend/src/agent/flow_router.py
  - frontend/src/pages/EvaluationPage.tsx
  - frontend/e2e/evaluation-governance.spec.ts
---

# Aggregate Gates Can Hide Router Gaps

> **TL;DR (EN)**: The original suite passed its aggregate router threshold,
> but the browser report retained twelve obvious Deep Research failures. Cost
> gates also exposed two conceptual questions routed to the tool agent. Fixing
> intent phrases and replacing `\b` ticker boundaries for Chinese-adjacent
> symbols moved suite v2 from 68/80 to 80/80 without lowering thresholds.
>
> **TL;DR (中文)**：原有 suite 虽然通过聚合路由阈值，但浏览器报告仍保留了
> 12 个明显的 Deep Research 失败；成本 Gate 还发现两个概念问题被错误路由到
> tool agent。补齐 intent 短语，并修复中文字符紧贴 ticker 时 `\b` 无法识别的
> 边界问题后，suite v2 从 68/80 提升到 80/80，且没有降低任何阈值。

## 1. Context

The first evaluation framework answered a narrow question: did deterministic
routing stay above the audited 74% baseline, and did unknown symbols avoid a
silent AAPL fallback?

The next governance layer needed to answer more:

- did execution mode match the expected cost class;
- did Prompt Injection text invent or override symbol context;
- did deterministic latency remain bounded;
- which prompt versions and model routes were evaluated;
- did a new report regress specific previously passing cases?

## 2. Investigation

Suite v2 added ten bilingual Prompt Injection symbol-override cases and
structured quality, latency, cost, and safety gates. The aggregate gates passed,
but the first browser report showed only 68 of 80 cases passing.

The retained failures were more useful than the green aggregate badge:

- “What does free cash flow mean?” was not recognized as a concept request.
- “投资中的贝塔是什么？” did not match the existing `什么是` phrase.
- phrases such as “full investment research”, “bull and bear thesis”, and
  “完整投资结论” did not match Deep Research markers.
- `\b[A-Z]+` did not recognize `NVDA` when Chinese characters touched the
  ticker because both sides were Unicode word characters.

## 3. Root Cause

The evaluation threshold described acceptable aggregate behavior, but it was
not a substitute for case-level evidence. The router also assumed English word
boundaries around ticker symbols, an assumption that does not hold in mixed
Chinese and Latin text.

Cost-policy evaluation made the concept misses visible: routing an explanation
to `v3` was not only inaccurate, it selected a more expensive execution class.

## 4. Fix

- Preserved the historical 70-case v1 suite and added an 80-case v2 suite.
- Added executable gates for quality, execution mode, unknown-symbol safety,
  Prompt Injection symbol safety, p95 latency, cost policy, and live calls.
- Added prompt registry and deterministic model-route snapshots.
- Added legacy-compatible JSON loading and baseline comparison reports.
- Added exact English and Chinese concept and Deep Research intent markers.
- Replaced Unicode `\b` ticker matching with ASCII alphanumeric lookarounds.
- Added a local FastAPI endpoint and browser Evaluation page.
- Kept case failures visible even when aggregate gates pass.
- Proved the final 80/80 result with Playwright screenshot evidence.

## 5. Lessons

- A passing aggregate gate can coexist with obvious, actionable failures.
- Cost classes can reveal routing mistakes that accuracy alone understates.
- Multilingual token boundaries require explicit assumptions and tests.
- Prompt/model comparison reports must identify exact versions without
  implying that a live model was called.
- Security metrics should state their precise scope; this delivery verifies
  Prompt Injection resistance for symbol invention and override, not a general
  content sandbox.
