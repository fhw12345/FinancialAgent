---
title: Reproducible Local Runtime Builds
status: shipped
version: backend@0.51.4, frontend@0.32.4
last_updated: 2026-08-13
owner: maintainer
related_paths:
  - backend/pyproject.toml
  - backend/Dockerfile
  - frontend/package-lock.json
  - frontend/Dockerfile
  - frontend/e2e/project-hardening.spec.ts
  - docs/features/assets/ph-008/01-clean-build-runtime.png
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

## Implementation Summary

Implementation commit `4742bc8` shipped the final runtime-build hardening:

- backend installs the committed `requirements.lock` without dependency
  re-resolution and exposes `PIP_INDEX_URL` only as a transport mirror;
- frontend installs from the committed `package-lock.json` using `npm install`
  (not `npm ci`), disables lifecycle scripts during image dependency install,
  verifies the lock remains semantically unchanged, and runs `npm ls --depth=0`;
- frontend runtime uses the non-root `node` user and a real Vite readiness
  healthcheck against `127.0.0.1:3000`;
- PH-008 has a real-stack Playwright smoke tagged `@ph008 @real-stack` that
  checks backend Health and a deterministic chat flow from freshly rebuilt
  images;
- default deterministic E2E routing now keeps events-backend scenarios out of
  the generic `test:e2e` suite and lets persistence checks choose the backend
  URL that matches the active browser stack.

The package-registry TLS blocker was reproduced against
`files.pythonhosted.org` and `registry.npmjs.org`. The final image build keeps
versions pinned by committed lock metadata while using reachable mirror URLs as
transport defaults. The mirrors are not dependency authority; the lock files
remain the authority.

## Validation Record

### Clean builds

Final validation ran two clean builds from the same working tree after the
version bump and E2E contract fixes:

```bash
docker compose build --no-cache backend frontend
docker compose build --no-cache backend frontend
```

The two builds produced different image IDs, as expected for non-bit-reproducible
Docker layers, but matching dependency manifests:

| Manifest | Build 1 hash | Build 2 hash |
| --- | --- | --- |
| Backend locked dependency install list | `d841833feb3ca0904f52b0010268f356e95a7f7583fd63fe8e4397c243088415` | `d841833feb3ca0904f52b0010268f356e95a7f7583fd63fe8e4397c243088415` |
| Frontend `npm ls --depth=0` tree | `a84fd7fdf983705b5d58818ebbbcd189ce6338edeccf52d4d8f3aa0ae4c22a9d` | `a84fd7fdf983705b5d58818ebbbcd189ce6338edeccf52d4d8f3aa0ae4c22a9d` |
| Backend package wheel | `financial_agent_backend-0.51.4`, `sha256=4d26c6f23d0d233656f1670fda4618acbd009d94faa76c07c4c62b8299923ba1` | `financial_agent_backend-0.51.4`, `sha256=4d26c6f23d0d233656f1670fda4618acbd009d94faa76c07c4c62b8299923ba1` |

Final image identifiers after the second clean build:

| Image | ID | Runtime user | Healthcheck |
| --- | --- | --- | --- |
| `financialagent-backend:latest` | `sha256:464b27b0fef10c78342e7836e362979fbcb9a731ead476905b91a7891b37fdd9` | `app` | `/api/health` |
| `financialagent-frontend:latest` | `sha256:ee32bd50ff23195f7e53fc1d5d1468f96fe8d74bb5511d94877b12f0aeb1ca5b` | `node` | `http://127.0.0.1:3000/` |

`docker history --no-trunc` for both images was scanned for `.env`, secret,
token, password, and API-key patterns; no local secret file or secret-looking
layer command was present.

### Fresh-image browser proof

Scenario: `ph-008-clean-build-smoke`

Runtime stack:

- final `financialagent-backend:latest` and `financialagent-frontend:latest`;
- MongoDB `7.0` and Redis `7.2-alpine`;
- deterministic Anthropic-compatible test stub mounted from `backend/tests/e2e`;
- frontend opened at `http://host.docker.internal:3010` with
  `VITE_API_URL=http://host.docker.internal:18090`.

Assertions:

1. backend `/api/health` returned HTTP 200 with backend `0.51.4`;
2. live backend and frontend containers reported Docker health `healthy`;
3. live backend ran as `app`, live frontend ran as `node`;
4. browser Health UI rendered `HEALTHY`;
5. deterministic chat request `Remember CLEAN-008 for the clean build smoke.`
   completed with `Acknowledged CLEAN-008.`;
6. curated screenshot was captured only after the assertions passed.

Evidence:

- `assets/ph-008/01-clean-build-runtime.png`.

### Quality gates

Backend:

```text
Ruff: passed
Black: passed
mypy: zero errors in 275 source files
pytest: 1,985 passed, 27 deselected
aggregate backend coverage: 69%
critical coverage floors: passed
```

Frontend:

```text
Vitest: 249 passed
production ESLint: 0 warnings
full ESLint warning budget: 131 warnings, 0 errors
TypeScript: passed
Vite build: passed
```

Agent/browser:

```text
Agent deterministic evaluation: passed
Default deterministic Playwright suite: 11 passed
PH-008 fresh-image Playwright: 1 passed
```

## Acceptance Criteria

- [x] Backend dependency resolution is committed and deterministic.
- [x] Frontend build verifies the committed lock and follows repository policy.
- [x] Both application containers run as non-root.
- [x] Two clean builds have matching dependency manifests.
- [x] Fresh-image Playwright smoke passes.
- [x] Screenshot and image identifiers are recorded.
- [x] Full quality gates pass.

## Risks and Follow-ups

- The current no-`npm ci` Docker rule still differs from common immutable-build
  practice. PH-008 preserves the project policy by using `npm install` with a
  lock semantic check rather than silently changing policy.
- Mirror defaults are transport fallbacks for this local development network;
  lock files remain authoritative. If the network path changes, override
  `PIP_INDEX_URL` or `NPM_CONFIG_REGISTRY` at build time without changing the
  dependency manifests.
- The frontend audit still reports npm vulnerability metadata during install.
  This is not a lock-drift failure and should be handled by a separate
  dependency-remediation task.
