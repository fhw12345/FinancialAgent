---
title: Local Network Perimeter Hardening
status: shipped
version: backend@0.51.5, frontend@0.32.5
last_updated: 2026-09-14
owner: maintainer
related_paths:
  - docker-compose.yml
  - backend/.env.example
  - README.md
  - docs/development/getting-started.md
---

# PH-001: Local Network Perimeter Hardening

## Objective

Make the documented local-only trust boundary true: frontend, backend, MongoDB,
Redis, LLM stubs, and E2E ports must bind to loopback unless a user explicitly
overrides that choice.

## Root Cause and Security Contract

Compose short-form ports such as `8000:8000` publish on every host interface.
CORS is not an access-control boundary for MongoDB, Redis, curl, or non-browser
clients.

Default contract:

- all published ports bind to `127.0.0.1`;
- backend containers may still listen on `0.0.0.0` inside the Docker network;
- inter-container traffic uses service names and is unaffected;
- remote access requires an explicit documented override;
- no authentication feature is added in this task.

## Ownership and Parallel Safety

Agent A owns `docker-compose.yml` port declarations and connectivity docs. Do
not edit Dockerfiles owned by PH-008. Coordinate with PH-004 before changing E2E
service names or ports.

## Implementation Plan

1. Inventory every `ports` entry, including profile-gated E2E services.
2. Convert host bindings to `127.0.0.1:<host>:<container>`.
3. Prefer `expose` over `ports` where the host never needs direct access.
4. Document the opt-in override for LAN access and its security implications.
5. Add a script/test that validates rendered Compose port host IPs.
6. Confirm `host.docker.internal` E2E connectivity still works.

## Test Plan

### Static and integration

```bash
docker compose config --format json
docker compose up -d --force-recreate backend frontend mongodb redis
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:3000
```

Assert every published binding has `HostIp` equal to `127.0.0.1`. Confirm the
backend can still reach MongoDB and Redis through the Compose network.

### Playwright E2E — required

Scenario `ph-001-local-stack-accessible`:

1. Start the real local stack with loopback bindings.
2. Open `http://127.0.0.1:3000` in a fixed viewport.
3. Navigate to Health.
4. Assert backend, MongoDB, and Redis are reported healthy.
5. Capture `docs/features/assets/ph-001/01-loopback-stack-healthy.png`.

The screenshot record must state that the real local stack was used. A host
binding assertion must pass before capture; the screenshot alone does not prove
network isolation.

## Acceptance Criteria

- [x] Every default published port is loopback-bound.
- [x] MongoDB and Redis are not reachable through a wildcard host binding.
- [x] Normal frontend/backend operation remains unchanged.
- [x] Real-stack Playwright health scenario passes.
- [x] Compose contract test prevents regression.
- [x] README and getting-started docs explain explicit remote-access opt-in.
- [x] Full quality gates pass.

## 2026-09-09 Closeout Plan

Recheck all profile-gated ports using rendered Compose JSON, not only the
short-form regex. Add negative tests for wildcard, omitted host IP and IPv6
bindings. Inspect live container publishers before the real Health/browser
capture. Document secure remote-access opt-in in getting-started as well as the
README. This plan kept the task in progress until the refreshed evidence and
publication recorded below were complete.

## Implementation and Test Record

Implemented loopback bindings for all 21 published Compose ports and added
`scripts/check-compose-loopback.py`. Rendered Compose JSON reported zero unsafe
bindings. MongoDB, Redis, frontend E2E, and backend E2E containers were
force-recreated and Docker reported only `127.0.0.1` host bindings.

Playwright scenario `loopback-bound real stack remains healthy` passed against
the real local MongoDB, Redis, backend E2E, and frontend E2E stack. After the
visible Health page asserted `HEALTHY` and backend version `0.51.1`, it captured
the initial screenshot (tested implementation `960d29a`). The current committed
asset was subsequently refreshed at `0.51.5`, as recorded below.

## Local Validation — 2026-09-09

Tested implementation: `db1e4b8739c21fb160e6eadda65dab53617522aa`, backend
`0.51.5` / frontend `0.32.5`. Code and refreshed screenshots are committed on the
pushed `hardening/closeout-ci` branch.

- Rendered all default profiles: 21 loopback bindings passed; isolated hardening
  profile: 2 loopback bindings passed. Empty/wildcard/implicit/IPv6 negative
  fixtures correctly fail.
- Inspected the isolated live stack: frontend `3011` and backend `18091` bind
  only to `127.0.0.1`; MongoDB/Redis/LLM publish no host ports.
- Real `/api/health` confirms MongoDB and Redis connectivity. Browser Health and
  matching component versions passed at a fixed 1440×1100 viewport.
- Refreshed [real-stack screenshot](assets/ph-001/01-loopback-stack-healthy.png).
  Agent responses in this stack are deterministic fixtures; Health and storage
  are real and not browser-mocked.
- README and getting-started now both explain safe remote-access opt-in.

Local and hosted perimeter/security gates passed. PR #1 merged normally on
2026-09-14 as `7cc3789b291cfb71865d3cb7a368a965957db5ca`; the task is shipped.
[PH-004](project-hardening-ci-agent-quality-gates.md) records the actual CI run,
required-check enforcement and retained artifact verification.

## Risks and Rollback

Docker Desktop host networking differs across platforms. Validate Windows and
the Linux CI representation of rendered Compose config. Roll back only the
specific binding that breaks a proven local workflow; never restore wildcard
database bindings as a convenience fix.
