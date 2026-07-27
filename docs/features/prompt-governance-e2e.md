---
title: Prompt Governance Browser Evidence
status: shipped
version: backend@0.47.1, frontend@0.28.1
last_updated: 2026-07-27
owner: maintainer
related_paths:
  - frontend/e2e/prompt-governance.spec.ts
  - backend/tests/e2e/agent_events_app.py
  - docs/features/assets/prompt-governance
---

# Prompt Governance Browser Evidence

The Playwright scenario exercises real frontend interactions against FastAPI,
MongoDB, and Redis:

1. Send a Direct chat and verify `financial-system@3` on the durable run.
2. Send a Deep request and verify conditional Deep prompt versions.
3. Navigate to Portfolio through the UI.
4. Click **Analyze My Holdings**.
5. Verify the background task reaches visible `done` state.

The Portfolio execution is deterministic in the E2E app; canonical Phase 2 and
Consistency Gate prompt rendering is covered by backend runtime tests.

## Evidence

```text
docs/features/assets/prompt-governance/
  01-chat-prompt-versions.png
  02-portfolio-flow-completed.png
```

## Acceptance Criteria

- [x] Browser drives chat and Portfolio UI interactions.
- [x] Real backend, MongoDB, and Redis boundaries are exercised.
- [x] Chat durable runs expose governed prompt versions.
- [x] Portfolio background lifecycle visibly completes.
- [x] Curated screenshots are committed only after assertions pass.

## Implementation Record

Shipped in E2E/provenance commit `0c00a48`.
