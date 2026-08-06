---
title: Backend Type Safety and Contract Convergence
status: shipped
version: backend@0.51.2
last_updated: 2026-08-06
owner: maintainer
related_paths:
  - backend/pyproject.toml
  - backend/src/
  - .github/workflows/pr-checks.yml
---

# PH-003: Backend Type Safety and Contract Convergence

## Objective

Reduce the current 298 mypy errors to zero without hiding domain-contract
problems behind broad ignores, and make the zero-error result reproducible in
CI.

## Scope

Classify and fix:

1. model/repository constructor drift;
2. Optional and union narrowing;
3. `asyncio.gather(return_exceptions=True)` handling;
4. mixin dependency protocols;
5. unparameterized collections and callables;
6. third-party missing stubs;
7. stale local-fork `user_id` parameters;
8. invalid or obsolete `type: ignore` comments.

Do not change user-visible behavior unless a type error identifies a real bug.
Such fixes require targeted regression tests and documentation.

## Ownership and Parallel Safety

Agent C owns typing-only changes across backend source. To reduce conflict:

- PH-002 owns snapshot prefetch lines;
- PH-007 owns new composition tests;
- PH-009 performs file moves only after this task merges;
- coordinate domain model edits before changing shared constructors.

Commit in bounded slices by category, keeping tests green after each slice.

## Implementation Plan

1. Save a machine-readable baseline grouped by error code and module.
2. Fix real call/model contract mismatches first.
3. Introduce `Protocol` interfaces for portfolio mixin dependencies.
4. Narrow gathered exceptions explicitly before consuming values.
5. Replace bare `dict`, `list`, and `Callable` with meaningful types.
6. Add narrow mypy overrides only for genuinely untyped third-party modules.
7. Remove stale multi-user arguments or formally retain them in models; do not
   rely on Pydantic silently ignoring extras.
8. Run strict mypy over all 275 backend source files.
9. Add mypy to CI after zero is reached.

## Test Plan

### Static

```bash
cd backend
python -m ruff check src/
python -m black --check src/
python -m mypy src/
```

Mypy must report zero errors and zero unused ignores.

### Runtime regression

Run all backend tests. Add focused tests for every fixed constructor or async
narrowing bug. Exercise portfolio Phase 1/2/3 model creation, watchlist creation,
insights snapshot, cache serialization, and LangGraph invocation config.

### E2E decision

Typing itself is not browser behavior, but contract corrections may affect user
workflows. Required real browser scenarios:

- chat ReAct request reaches terminal completed state;
- portfolio analysis produces a persisted decision;
- watchlist add/list survives reload;
- insights refresh displays metrics.

Reuse existing UAW/portfolio/insights Playwright specs and capture new evidence
only for workflows whose runtime behavior changed. Record the exact reused
scenarios and commits in this document.

## Acceptance Criteria

- [x] `mypy src/` returns zero errors across 275 source files.
- [x] No blanket module-wide ignore was introduced for project code.
- [x] Real contract defects have focused and full-suite regression coverage.
- [x] Full backend suite passes: 1,944 tests, 27 live integrations deselected.
- [x] Affected browser workflows pass.
- [x] CI executes the same mypy command.
- [x] Temporary type-error baseline artifacts were removed.

## Implementation and Test Record

The pass enabled the official Pydantic plugin and reduced the strict baseline
from 297 errors in 81 files to zero across all 275 source files. It repaired
provider/cache shape validation, gathered BaseException and cancellation
handling, optional startup services and analyzers, Motor and collection
generics, Portfolio mixin dependencies, local Holding ownership assumptions,
and structured-output validation. No project module received a blanket ignore.

Validation completed on 2026-08-06:

- Ruff, Black, and strict mypy passed;
- the complete backend suite passed with 1,944 tests and 66% aggregate coverage;
- deterministic Agent evaluation passed;
- UAW-009 proved ordered Direct, ReAct, and Deep envelopes;
- prompt-governance proved the Portfolio browser flow;
- UAW-004 proved watchlist analysis persistence after backend readiness;
- the project-hardening Insights refresh scenario passed.

After the ReAct assertion passed, Playwright captured
[`assets/ph-003/01-agent-envelope-after-type-safety.png`](assets/ph-003/01-agent-envelope-after-type-safety.png)
using the deterministic real frontend-to-backend UAW-009 stack. The first
watchlist attempt started before its backend was ready and failed at loading;
a readiness-confirmed rerun passed, preserving the failure as lifecycle
feedback rather than hiding it.

Implementation commit: `6344fd4`.

## Risks

Pydantic's default extra handling can make invalid constructor parameters look
harmless. Treat unexpected fields as domain decisions, not annotation cleanup.
Large mechanical edits should be separated from semantic fixes for review.
