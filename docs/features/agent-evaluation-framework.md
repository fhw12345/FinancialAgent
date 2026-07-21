---
title: Agent Evaluation Framework
status: shipped
version: backend@0.42.0
last_updated: 2026-07-21
owner: maintainer
related_paths:
  - backend/src/evals/schemas.py
  - backend/src/evals/cases_v1.py
  - backend/src/evals/runner.py
  - backend/scripts/run_agent_eval.py
---

# P1: Agent Evaluation Framework

## Goal

Provide a repeatable, versioned answer to whether router, prompt, model, or
tool-policy changes regress agent behavior.

## Initial Suite

- 20 instant conceptual cases;
- 20 agentic current-data cases;
- 15 Deep Research cases;
- 15 ambiguous/adversarial cases;
- English and Chinese coverage;
- missing-symbol and unknown-symbol safety cases.

## Deterministic Gates

- deterministic rule/fallback router accuracy: at least 74% across automatic
  cases, with every mismatch retained in the report;
- unknown-symbol safety: 100%;
- case schema validity: 100%;
- report generation must be deterministic;
- live model scoring is disabled unless explicitly requested.

## Outputs

The CLI writes JSON and Markdown artifacts containing case-level evidence,
aggregate metrics, thresholds, and failures.

## Acceptance Criteria

- [x] Versioned suite expands to 70 cases.
- [x] Normal evaluation performs no live model calls.
- [x] Router and symbol-safety gates are executable.
- [x] Results and failures use structured schemas.
- [x] JSON and Markdown reports are generated.
- [x] CLI exits non-zero when a gate fails.
- [x] Full backend validation passes.

## Implementation Record

Shipped in implementation commit `57a6f39`, backend `0.42.0`.

The audited baseline is 74.5% across 55 automatic-routing cases, with all
mismatches retained in the report. All 15 unknown-symbol/adversarial cases
resolve safely without a default symbol.
