---
title: Live Model Acceptance Is Not Profitability / 真模型验收不是收益验证
status: in-progress
version: backend@0.60.1, frontend@0.41.1
last_updated: 2026-10-09
owner: maintainer
related_paths:
  - backend/tests/model_portfolios/
  - backend/tests/e2e/model_portfolios_app.py
  - frontend/e2e/live-model-portfolios.spec.ts
---

# Live Model Acceptance Is Not Profitability / 真模型验收不是收益验证

> **TL;DR (EN):** Synthetic holdings with a fixed model response test software, not actual
> model decisions. A separately authorized six-attempt native-model suite now exercises
> model output against known account/evidence constraints, reporting containment and model
> contract quality separately. Neither is source-truth or profitability verification.
>
> **TL;DR (中文)：** 模拟持仓配固定模型回答只能验证软件。独立授权的最多六次真实模型验收
> 对照固定账户／证据约束检查输出，并把代码阻断与模型契约质量分开报告；都不是收益保证。

## Context

User asked to fill the missing real-model layer, then explicitly authorized at most six
Astra inference requests, 4096 output tokens each, one 10-minute run. Inputs remain
synthetic; completed source receipts are precomputed through actual calculators and
repositories rather than spending extra calls on research, translation or a judge.

## Investigation

Counting six UI clicks is insufficient: native authorization refresh can retry a 401,
and the reused structured agent has a retry loop. A single model-decision request may
otherwise spend more than one upstream inference attempt. Restarting a test process
must not reset the approved budget. Existing fake-login fixture imports would replace
private credentials; the live fixture must be independent of those modules.

## Implementation

- A persistent test-run aggregate freezes manifest/mode/deadline and atomically reserves
  attempts at the upstream transport. Each case has one attempt, including failed/401
  attempts. Total ceiling is six; retry/reseed/restart cannot replenish it.
- Test database namespace is checked before startup writes. Live credentials stay inside
  the existing private volume. Fixture HTTP blocks credential/configuration/chat mutations;
  only the registered decision path may forward paid inference, to allowlisted hosts.
- Reports retain all case IDs, synthetic sealed inputs, actual prompt/output/usage hashes,
  failed cases and gate reasons. Successful rejection does not mark a known-bad model
  decision as a quality pass. HOLD-only does not imply existing concentration is cleared.
- Ordinary CI uses separate replay credentials and a no-real-network transport. Live and
  replay screenshots/report modes are explicitly labeled. Neither evidence mode includes
  live research quality or investment outcome measurement.

## Acceptance

Unit oracles include a known-bad BUY on a held position above its position limit: model
quality has findings even though the real gate safely blocks. Browser cases use the real
production decision and approval endpoints, immutable records and Mongo; no readiness or
model-gate result is mocked. Final-image/repeated-build and the one registered real batch
passed locally; [the spec](../features/investment-live-model-portfolio-tests.md) records
2360 backend/280 frontend tests, 60 deterministic image-browser executions and a separate
9-case native batch with exactly six requests. Protected publication remains pending.

The actual model returned five HOLD/WAIT outputs and one REDUCE-to-30% boundary proposal.
After costs and lot sizing, the latter was 30.0132%, so the real gate blocked it. Contract
quality is **5 conforming / 1 finding**, not nine green model-quality cases. No live positive
ready/approval sample occurred; the explicitly labeled replay ADD case covers that path.
Several rationales request risk data not included in the current production prompt; this
is recorded, not repaired or retested with unauthorized additional model calls.

Browser history can show stored model completion before separate review publication.
The acceptance wait now reads the original POST terminal response and explicitly requires
the replay-positive ready/approval path. The live run was not repeated. An artifact bind/
layout correction recovered the original durable report through read-only access; curated
live images render that report, not a new production UI/live-model execution.

The staged scanner identified five high-entropy synthetic source `request_key` values as
API keys. They are registered case identities, not credentials. Public report format now
labels them `synthetic_request_identity`; an exact reverse transformation recovers the
original report bytes/hash. No scanner exception or hidden output redaction was added.

## Lessons

Bound actual external attempts, not logical actions. Separate input origin from provider
mode; a live LLM consuming synthetic receipts is not a live research test. Keep failed,
blocked and abstaining decisions visible; avoid exact-profitable-action labels, paid judges,
reruns or winner selection. Even a fully contract-conforming model can make bad investments.
