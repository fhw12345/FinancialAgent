---
title: Backend Type Safety and Contract Convergence
status: planning
version: backend@0.51.1
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
8. Run strict mypy over all 274 backend source files.
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

- [ ] `mypy src/` returns zero errors.
- [ ] No blanket module-wide ignore is introduced for project code.
- [ ] Every real contract defect has a regression test.
- [ ] Full backend suite passes.
- [ ] Affected browser workflows pass.
- [ ] CI executes the same mypy command.
- [ ] Type-error baseline artifact is removed or shows zero.

## Risks

Pydantic's default extra handling can make invalid constructor parameters look
harmless. Treat unexpected fields as domain decisions, not annotation cleanup.
Large mechanical edits should be separated from semantic fixes for review.
