---
title: Backend Tests Are Not Browser Evidence
status: shipped
version: backend@0.47.1, frontend@0.28.1
last_updated: 2026-07-27
owner: maintainer
related_paths:
  - CLAUDE.md
  - frontend/e2e/prompt-governance.spec.ts
---

# Backend Tests Are Not Browser Evidence

> **TL;DR (EN)**: Prompt Governance was reported shipped after targeted and
> full backend tests, but the repository workflow requires Playwright evidence.
> The tasks were reopened, browser scenarios were added, and `CLAUDE.md` now
> explicitly blocks shipped status until E2E screenshots exist.
>
> **TL;DR (中文)**：Prompt Governance 在 targeted/full backend tests 后被
> 报告 shipped，但项目流程要求 Playwright 证据。任务被重新打开并补齐浏览器
> 场景，同时 `CLAUDE.md` 明确规定没有 E2E 截图不得标记 shipped。

## Lesson

Passing lower-layer tests proves implementation logic, not the user-visible
integration boundary. Workflow completion criteria must be enforced as gates,
not treated as optional documentation.
