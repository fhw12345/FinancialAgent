---
title: Authoritative Runtime Version Metadata
status: in-progress
version: backend@0.51.1, frontend@0.32.1
last_updated: 2026-08-06
owner: maintainer
related_paths:
  - backend/pyproject.toml
  - backend/src/main.py
  - frontend/package.json
  - docs/architecture/overview.md
---

# PH-010: Authoritative Runtime Version Metadata

## Objective

Remove hard-coded and stale version strings so API responses, OpenAPI,
frontend diagnostics, documentation, screenshots, and changelogs identify the
same tested release.

## Version Contract

- backend package metadata is authoritative for backend version;
- frontend package metadata is authoritative for frontend version;
- runtime code reads generated/imported metadata rather than duplicating it;
- `/`, health diagnostics, and OpenAPI expose the backend version;
- the UI exposes frontend and backend versions in an appropriate diagnostics
  view;
- feature evidence records the tested commit in addition to semantic versions.

## Ownership and Parallel Safety

Agent J owns version plumbing and stale architecture metadata. Avoid unrelated
architecture rewrites. Coordinate package version bumps with every task before
final integration so this task does not overwrite another component bump.

## Implementation Plan

1. Add one backend version accessor based on installed package metadata with a
   safe editable-development fallback.
2. Use it in FastAPI/OpenAPI, root, health, logs, and evaluation reports.
3. Expose frontend version through a build-time constant sourced from
   `package.json`.
4. Display both versions in Health or Help without cluttering primary workflows.
5. Update stale architecture version metadata.
6. Add a consistency script comparing runtime endpoints and package files.
7. Document bump ownership for parallel branches.

## Test Plan

### Unit/integration

- installed and editable backend metadata paths;
- OpenAPI and root/health report the package version;
- frontend build constant equals `package.json`;
- consistency script fails on an intentional mismatch;
- eval report includes backend version and commit where available.

### Playwright E2E — required

Scenario `ph-010-version-diagnostics`:

1. Start the real local stack from the tested commit.
2. Open the visible Health or Help diagnostics.
3. Assert frontend `0.32.1` baseline/updated version and backend
   `0.51.1` baseline/updated version match package metadata.
4. Assert the backend health response reports the same backend version.
5. Capture `docs/features/assets/ph-010/01-version-diagnostics.png`.

Use the actual bumped versions at implementation time rather than freezing the
planning baseline above.

## Acceptance Criteria

- [ ] No runtime `0.1.0` placeholder remains.
- [ ] Package metadata and runtime diagnostics agree.
- [ ] Architecture overview reflects current component versions.
- [ ] Consistency test prevents drift.
- [ ] Browser diagnostics scenario and screenshot pass.
- [ ] Changelogs and feature docs contain final versions and commit hashes.

## Implementation and Test Record

Added an authoritative backend version accessor that prefers bind-mounted
`pyproject.toml` metadata and falls back to installed package metadata. FastAPI,
root, and health now use it. Vite injects the frontend package version, and the
Health UI displays both component versions. A real restarted backend reported
`0.51.1`, replacing the stale image metadata value.

Playwright scenario `health diagnostics show matching component versions`
asserted frontend `0.32.1` and backend `0.51.1` before capturing
[`assets/ph-010/01-version-diagnostics.png`](assets/ph-010/01-version-diagnostics.png).
The screenshot used deterministic API fixtures; PH-001 separately proves the
real backend Health page. The tested implementation commit is `960d29a`.

## Risks

Parallel version bumps commonly conflict. Assign one integration owner to
perform final component bumps after implementation branches merge, and require
other agents to state which component needs a major/minor/patch bump without
editing the same version line concurrently.
