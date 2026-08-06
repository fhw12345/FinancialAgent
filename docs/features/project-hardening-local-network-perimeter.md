---
title: Local Network Perimeter Hardening
status: in-progress
version: backend@0.51.1, frontend@0.32.1
last_updated: 2026-08-06
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

- [ ] Every default published port is loopback-bound.
- [ ] MongoDB and Redis are not reachable through a wildcard host binding.
- [ ] Normal frontend/backend operation remains unchanged.
- [ ] Real-stack Playwright health scenario passes.
- [ ] Compose contract test prevents regression.
- [ ] README and getting-started docs explain explicit remote-access opt-in.
- [ ] Full quality gates pass.

## Implementation and Test Record

Implemented loopback bindings for all 21 published Compose ports and added
`scripts/check-compose-loopback.py`. Rendered Compose JSON reported zero unsafe
bindings. MongoDB, Redis, frontend E2E, and backend E2E containers were
force-recreated and Docker reported only `127.0.0.1` host bindings.

Playwright scenario `loopback-bound real stack remains healthy` passed against
the real local MongoDB, Redis, backend E2E, and frontend E2E stack. After the
visible Health page asserted `HEALTHY` and backend version `0.51.1`, it captured
[`assets/ph-001/01-loopback-stack-healthy.png`](assets/ph-001/01-loopback-stack-healthy.png).
The tested implementation commit is `960d29a`.

## Risks and Rollback

Docker Desktop host networking differs across platforms. Validate Windows and
the Linux CI representation of rendered Compose config. Roll back only the
specific binding that breaks a proven local workflow; never restore wildcard
database bindings as a convenience fix.
