---
title: Evaluation Governance
status: shipped
version: backend@0.51.0, frontend@0.32.0
last_updated: 2026-08-04
owner: maintainer
related_paths:
  - backend/src/evals/
  - backend/scripts/run_agent_eval.py
  - backend/src/api/evaluations.py
  - backend/src/agent/prompt_registry.py
  - backend/src/agent/llm_factory.py
  - frontend/src/pages/EvaluationPage.tsx
  - frontend/e2e/evaluation-governance.spec.ts
---

# Evaluation Governance

## Current Baseline

Backend `0.50.0` and frontend `0.31.0` shipped deterministic governance:

- a versioned v2 suite containing explicit Prompt Injection symbol-override
  cases;
- executable quality, execution-mode, symbol-safety, injection-safety,
  latency, cost-policy, and no-live-model gates;
- exact prompt-version and model-route snapshots;
- baseline comparison reports with case regression detection;
- a local browser page that runs and renders the same backend suite.

That baseline is useful for fast routing and symbol-safety regression, but it
does not execute production prompts, real model inference, autonomous tool
selection, answer-quality judging, or measured token cost.

## Delivery Scope

This iteration upgrades the system into a layered Agent evaluation platform.

### Lane A: Deterministic Gate

- remains the default for `make eval`, API, and browser runs;
- executes without network or paid model calls;
- retains versioned routing, execution-mode, symbol, and Prompt Injection
  symbol-override cases;
- must fail when any critical case fails;
- must enforce `required_tools` and `forbidden_tools` when tool evidence exists;
- must distinguish configured Prompt versions from Prompts actually exercised.

### Lane B: Replay-Tool Live Model Gate

- is opt-in through explicit CLI/API/UI controls;
- invokes the configured production target model;
- uses the production `financial-system` Prompt and production tool names;
- exposes deterministic replay tools with fixed quote, news, overview,
  financial-statement, and technical-analysis fixtures;
- records every selected tool, arguments, output identity, Prompt version,
  target model route, token usage, latency, and estimated USD cost;
- evaluates conceptual answers that should call no tools;
- evaluates current-data answers that must call required tools and avoid
  forbidden tools;
- evaluates whether the final answer includes required fixture facts and avoids
  unsupported claims.

### Independent Judge

- uses a separate `eval_judge` role and `eval-judge@1` structured Prompt;
- scores factual grounding, required-fact coverage, source consistency,
  relevance, completeness, uncertainty disclosure, contradiction handling,
  financial-risk language, and unsupported certainty;
- includes exact evidence quotes for failed criteria;
- runs in addition to deterministic rubric checks rather than replacing them;
- cannot judge its own output or reuse the target model response as hidden
  instructions.

### Lane C: Real-Provider Smoke

- is separately opt-in and never part of automated quality gates;
- runs a small allowlisted case set against real configured tools/providers;
- records provider/source metadata, tool latency, target-model usage, Judge
  usage, and cost;
- surfaces provider degradation explicitly;
- does not update the deterministic or replay baseline automatically.

### Out of Scope

- Portfolio outcome calibration and Decision Tracker performance analytics;
- production CI that spends paid model tokens automatically;
- claims that estimated token pricing exactly equals the provider invoice;
- general Prompt Injection isolation outside the cases and evidence boundaries
  explicitly exercised by the suite.

## Execution Contract

```text
Evaluation request
  -> resolve lane and case set
  -> validate explicit live consent and budget
  -> reserve worst-case per-case budget
  -> invoke target model with production Prompt
  -> execute replay or real tools
  -> collect messages, tool calls, usage, latency, and Prompt provenance
  -> apply deterministic rubric
  -> invoke independent structured Judge
  -> account target + Judge cost
  -> stop before the next call when budget is exhausted
  -> persist and render structured report
```

## Budget and Cost Contract

- deterministic lane always costs zero;
- live lanes require `enabled=true`, a positive `max_cost_usd`, and an explicit
  case limit;
- target and Judge calls have separate input/output token accounting;
- cost uses measured provider tokens and a versioned model-pricing catalog;
- unknown model pricing blocks live execution unless an explicit override is
  supplied;
- reports identify cost source as `catalog_estimate`, `override_estimate`, or
  `provider_reported`;
- each call uses bounded `max_tokens`, timeout, and sequential execution;
- the runner checks remaining budget before every target and Judge call;
- crossing the budget marks the run `budget_exhausted`, cancels remaining work,
  and never returns a success-shaped Gate result;
- automated tests and Playwright use fake models and must spend zero paid
  tokens.

## Prompt and Tool Provenance

- `configured_prompt_versions` is a registry snapshot;
- `used_prompt_versions` contains only Prompts actually rendered or invoked;
- model routes record provider, role, and model without exposing credentials;
- tool evidence contains tool name, normalized arguments, replay fixture ID or
  provider source ID, duration, and success/failure;
- Prompt Injection cases use a search environment containing real valid ticker
  fixtures so injected AAPL/TSLA/NVDA/MSFT symbols cannot pass merely because
  lookup always returns empty;
- quoted external instructions are tagged as untrusted evidence and cannot
  become user-selected symbol intent.

## Case Contract

Every live case declares:

```text
case_id
language
input
current_symbol
target_role
required_tools
forbidden_tools
required_facts
forbidden_claims
max_target_output_tokens
max_judge_output_tokens
max_latency_ms
max_cost_usd
minimum_deterministic_score
minimum_judge_score
```

Initial replay suite:

- conceptual explanation with zero tool calls;
- current quote requiring `get_stock_quote`;
- latest news requiring `get_news_sentiment`;
- company fundamentals requiring `get_company_overview`;
- technical analysis requiring `fibonacci_analysis_tool`;
- multi-source analysis requiring quote + news + overview;
- bilingual variants;
- Prompt Injection symbol-override cases using valid replay tickers.

## Gate Contract

- v1 remains loadable with 70 historical cases.
- v2 contains 80 cases, including 10 bilingual Prompt Injection cases that
  attempt to override or invent symbol context.
- deterministic evaluation never constructs a live model.
- every gate records observed value, operator, threshold, and pass/fail.
- baseline comparison retains metric deltas, prompt/model changes, regressed
  case IDs, and improved case IDs.
- deterministic and replay lanes fail on any critical-case failure;
- replay gates include tool precision/recall, deterministic answer score, Judge
  score, required-fact coverage, unsupported-claim rate, p95 latency, token
  usage, and total estimated cost;
- baseline policy evaluates every reported metric using direction-aware
  tolerances, including latency and cost;
- CLI exits non-zero for current Gate failures, baseline regressions, budget
  exhaustion, incomplete Judge results, or missing pricing.

## Risks

- real model output is nondeterministic, so live gates need explicit score
  margins and retained evidence rather than exact-string assertions;
- Judge models can be biased or agree with the target model, so deterministic
  required facts and forbidden claims remain authoritative;
- tool replay can drift from production schemas, so replay tool signatures
  must match production tool names and arguments;
- retries can spend more than expected unless every call is accounted for;
- a single call can consume its reserved budget, so preflight must use a
  conservative worst-case reservation;
- model pricing changes over time and must be versioned and overrideable;
- real-provider smoke tests can fail because of rate limits or outages and must
  not be confused with product regressions;
- old JSON reports must remain loadable after schema expansion;
- prompt/model metadata must describe evaluated configuration, not imply that
  live inference occurred;
- a passing aggregate threshold must not hide case-level failures.

## Test Plan

- v1/v2 deterministic suite compatibility;
- all-case, category, critical-case, latency, cost, and metric-regression Gates;
- Prompt provenance records only actually used Prompts;
- valid injected tickers remain unresolved unless selected by trusted user
  context;
- replay tool signatures and fixture identity;
- required/forbidden tool assertions;
- required facts, forbidden claims, citation/source consistency, and risk
  language deterministic rubrics;
- structured Judge success, invalid output, timeout, and disagreement paths;
- target and Judge token accounting;
- pricing catalog and explicit override behavior;
- budget preflight, mid-run exhaustion, cancellation, and skipped-case states;
- fake-model replay lane with zero network and zero paid cost;
- optional real-provider smoke behind explicit opt-in;
- legacy report loading and new report persistence;
- CLI success/failure exit codes for every terminal state;
- API validation and run-history retrieval;
- frontend deterministic/live/smoke controls and detailed evidence rendering;
- Playwright deterministic run and fake-live replay run with curated
  screenshots.

## Playwright Scenarios

### Scenario 1: Deterministic Gate

1. Open Evaluation.
2. Run deterministic suite v2.
3. Verify all critical cases and Gates pass.
4. Verify zero live model calls and zero cost.
5. Save `01-deterministic-governance.png`.

### Scenario 2: Fake Live Replay

1. Select replay-live mode.
2. Enable explicit live consent using the test fake-model backend.
3. Set a small visible budget.
4. Run the replay suite.
5. Verify required tools, Prompt provenance, target/Judge tokens, Judge score,
   and cost evidence.
6. Verify no external provider requests occurred.
7. Save `02-live-replay-quality-and-cost.png`.

### Scenario 3: Budget Exhaustion

1. Select replay-live mode with a deliberately insufficient budget.
2. Run the suite.
3. Verify the run terminates as `budget_exhausted`.
4. Verify remaining cases are skipped and the UI does not show a green Gate.
5. Save `03-budget-exhaustion.png`.

## Acceptance Criteria

- [x] The updated feature spec is complete before implementation begins.
- [x] v1 remains 70 cases and v2 remains 80 deterministic cases.
- [x] Ten bilingual Prompt Injection cases execute against valid ticker
      fixtures without symbol invention
      or override.
- [x] Any critical case failure makes the lane fail.
- [x] Required and forbidden tool contracts are executable.
- [x] Production Prompts are invoked and only used Prompt versions are reported
      as evaluated.
- [x] Replay live cases execute the configured target model and independent
      Judge model.
- [x] Deterministic and Judge quality scores both retain criterion evidence.
- [x] Target/Judge tokens, latency, and estimated USD cost are recorded.
- [x] Explicit hard budgets prevent additional calls and produce
      `budget_exhausted`.
- [x] Baseline comparison enforces direction-aware quality, latency, token, and
      cost regression policy.
- [x] Real-provider smoke remains separate and opt-in.
- [x] Legacy JSON reports remain loadable.
- [x] Evaluation run history is persisted and inspectable.
- [x] The local Evaluation page renders deterministic, fake-live replay, and
      budget-exhaustion evidence.
- [x] Full backend/frontend tests, Ruff, ESLint, frontend type-check, and
      changed-path mypy checks pass. Full-repository mypy remains historical
      debt but improves from 308 errors on `origin/main` to 298 with zero
      errors in changed paths.
- [x] Final code review finds no unresolved false-green, cost, cancellation,
      provenance, or compatibility issue.
- [x] Playwright passes and screenshots are stored under
      `docs/features/assets/evaluation-governance/`.

## Delivery Evidence

- Backend: 1,942 tests passed; the deterministic v1/v2 and live evaluation
  suites include budget, invalid-Judge, provider failure, progress persistence,
  legacy report, and Prompt Injection trust-boundary coverage.
- Frontend: 246 tests passed; ESLint and TypeScript checks pass.
- Browser: all three Playwright scenarios pass and refresh the curated
  deterministic, live quality/cost, and budget-exhaustion screenshots.
- Static analysis: Ruff passes; changed backend paths have zero mypy errors.
- Real-provider smoke remains cost-bearing and explicitly opt-in, so automated
  validation uses the fake-live model and spends no provider tokens.

## Previous Delivery

Deterministic governance v2 shipped in implementation commit `2540bbf`,
backend `0.50.0`, and frontend `0.31.0`. This document is reopened for the
live Prompt/tool/output/cost evaluation extension.

## Shipment

The layered live evaluation extension shipped in implementation commit
`4530fb3`, backend `0.51.0`, and frontend `0.32.0`.
