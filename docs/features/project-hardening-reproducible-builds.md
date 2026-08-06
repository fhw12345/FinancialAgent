---
title: Reproducible Local Runtime Builds
status: in-progress
version: backend@0.51.1, frontend@0.32.1
last_updated: 2026-08-06
owner: maintainer
related_paths:
  - backend/pyproject.toml
  - backend/Dockerfile
  - frontend/package-lock.json
  - frontend/Dockerfile
---

# PH-008: Reproducible Local Runtime Builds

## Objective

Ensure two clean builds from the same commit resolve the same dependency graph
and produce functionally equivalent non-root runtime images.

## Contract

- committed lock/constraint metadata is the dependency source of truth;
- Docker builds do not silently resolve newer package versions;
- daily development reuses the existing frontend image and dependency volume;
- `npm ci` is never run inside the normal development container or image build,
  per repository policy;
- production/runtime processes use non-root users;
- healthchecks reflect actual service readiness.

## Ownership and Parallel Safety

Agent H owns Dockerfiles, backend lock/constraints, package installation
strategy, and build documentation. Agent A owns Compose bindings. Coordinate
healthcheck-related Compose edits rather than modifying the same lines.

## Implementation Plan

1. Select and document a Python lock strategy compatible with editable local
   development and Docker builds.
2. Constrain fast-moving LangChain, LangGraph, DeepAgents, Pydantic, and FastAPI
   compatibility ranges.
3. Make the frontend image install exactly the committed lock without violating
   the no-`npm ci`-in-image policy; use an approved lock-respecting alternative
   such as `npm install --package-lock-only` outside the image plus
   `npm install --ignore-scripts` with lock verification, or document an
   explicit policy amendment before implementation.
4. Add a non-root frontend user.
5. Separate development serving from an optional built static runtime if useful
   for E2E stability.
6. Add/repair healthchecks and image metadata.
7. Compare dependency manifests and build outputs across two clean builds.

## Test Plan

### Build and security

```bash
docker compose build --no-cache backend frontend
docker compose build --no-cache backend frontend
docker image inspect <image>
```

Assert lock hashes/dependency manifests match, processes are non-root, health
checks pass, and no secret is copied into an image layer.

### Unit/integration

Run backend and frontend full suites in the rebuilt images. Verify hot reload
and mounted dependency volumes still work in development.

### Playwright E2E — required

Scenario `ph-008-clean-build-smoke`:

1. Start only freshly rebuilt images plus MongoDB and Redis.
2. Open the frontend.
3. Assert Health and one deterministic chat/analysis workflow.
4. Capture `docs/features/assets/ph-008/01-clean-build-runtime.png`.

## Acceptance Criteria

- [ ] Backend dependency resolution is committed and deterministic.
- [ ] Frontend build verifies the committed lock and follows repository policy.
- [ ] Both application containers run as non-root.
- [ ] Two clean builds have matching dependency manifests.
- [ ] Fresh-image Playwright smoke passes.
- [ ] Screenshot and image identifiers are recorded.
- [ ] Full quality gates pass.

## Implementation Progress

Added a Linux/Python 3.12 production dependency lock, installed the backend
package without dependency re-resolution, copied the frontend lock into its
image, added explicit npm dependency-tree validation, and changed the frontend
runtime to the non-root `node` user.

Implementation commit `960d29a` added the lock/install safeguards. Clean builds
are currently blocked by TLS handshake failures to `files.pythonhosted.org`;
an npm CLI failure also demonstrated why the new `npm ls` validation is required. These external failures mean PH-008 has not
met its clean-build or browser acceptance criteria and remains in progress.

## Risks

The current no-`npm ci` Docker rule conflicts with common immutable-build
practice. Do not bypass it silently. Propose and approve a policy change if no
lock-respecting installation method satisfies both reproducibility and the
existing dependency-volume workflow.
