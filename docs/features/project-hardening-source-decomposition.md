---
title: Oversized Source Module Decomposition
status: planning
version: backend@0.51.2, frontend@0.32.3
last_updated: 2026-08-06
owner: maintainer
related_paths:
  - backend/src/services/data_manager/manager.py
  - backend/src/agent/langgraph_react_agent.py
  - backend/src/agent/portfolio/flows.py
  - frontend/src/components/portfolio/DecisionTracker.tsx
  - frontend/src/components/EnhancedChatInterface.tsx
---

# PH-009: Oversized Source Module Decomposition

## Objective

Bring production source files under the 500-line policy while preserving public
imports, runtime behavior, event order, persistence, and UI lifecycle.

## Dependency

This is a Wave 2 task. Start only after PH-002, PH-003, PH-005, PH-006, and
PH-007 merge. Moving files earlier creates avoidable conflicts and makes
semantic regressions hard to attribute.

## Decomposition Boundaries

Backend candidates:

- DataManager provider domains, prefetch, cache facade, and enrichment;
- ReAct construction, tool registration, invocation, streaming, and retry;
- portfolio phase orchestration versus compatibility adapters;
- AI-sector metric families;
- SEC client, parser, URL resolution, and mapping;
- trading decision schemas versus derivation logic.

Frontend candidates:

- DecisionTracker data model, filters, table, detail, and mutation dialogs;
- EnhancedChatInterface lifecycle, layout, input, and restoration;
- useAnalysis stream reducer, event handlers, and analysis actions;
- ChatMessages renderer and message variants;
- Deep accordion reducer and selectors.

## Ownership and Parallel Safety

Agent I owns moves and import compatibility after Wave 1. Split backend and
frontend into separate commits/worktrees if desired, but do not let two agents
move the same dependency graph concurrently.

## Implementation Plan

1. Freeze behavior with PH-007 tests and existing Playwright suites.
2. Produce an import/dependency map for each oversized file.
3. Extract cohesive modules one at a time with compatibility re-exports.
4. Avoid redesigning behavior during movement.
5. Run targeted tests after every extraction.
6. Remove compatibility aliases only after all imports migrate.
7. Make the file-length check scan all production source in CI, not only staged
   files.

## Test Plan

### Static

Assert every production `.py`, `.ts`, and `.tsx` file is at most 500 lines.
Run Ruff, Black, mypy, ESLint, TypeScript, and builds after each slice.

### Regression

Run all backend/frontend tests, deterministic eval, and the complete
deterministic Playwright suite. Compare canonical event sequences and persisted
records before and after extraction.

### Playwright E2E — required

At minimum rerun:

- Direct/ReAct/Deep chat;
- cancellation and restoration;
- request idempotency;
- Portfolio decision tracking;
- Insights refresh;
- chart analysis overlay.

Capture `docs/features/assets/ph-009/01-post-decomposition-chat.png` and
`02-post-decomposition-portfolio.png` only after full assertions pass.

## Acceptance Criteria

- [ ] No production source file exceeds 500 lines.
- [ ] Public API/import compatibility is preserved or migrated atomically.
- [ ] No event, persistence, or user-visible behavior changes unintentionally.
- [ ] Complete deterministic eval and Playwright suites pass.
- [ ] Curated browser evidence is committed.
- [ ] File-length CI gate scans the repository source set.

## Risks

Large moves obscure semantic diffs. Keep extraction commits mechanical, use
`git diff --color-moved`, and separate any discovered behavior fix into its own
task and test-first commit.
