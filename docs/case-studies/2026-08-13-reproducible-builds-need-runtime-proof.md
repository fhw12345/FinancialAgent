---
title: Reproducible Builds Need Runtime Proof
status: shipped
version: backend@0.51.4, frontend@0.32.4
last_updated: 2026-08-13
owner: maintainer
related_paths:
  - backend/Dockerfile
  - frontend/Dockerfile
  - backend/requirements.lock
  - frontend/package-lock.json
  - frontend/e2e/project-hardening.spec.ts
  - docs/features/project-hardening-reproducible-builds.md
---

# Reproducible Builds Need Runtime Proof

> **TL;DR (EN)**: PH-008 looked like a dependency-lock task, but the real risk
> was treating exported Docker images as proof. The build could fail on package
> registry TLS, npm could mutate lock formatting, and a frontend healthcheck
> could be unhealthy even after Vite served the app. The fix kept lock files as
> dependency authority, used mirrors only as transport, verified lock semantics,
> inspected final images, and required fresh-image Playwright before shipment.
>
> **TL;DR (中文)**：PH-008 表面上是依赖锁定任务，真实风险却是把“Docker 已导出镜像”
> 当成了证明。构建会被包仓库 TLS 阻塞，npm 可能改写 lock 文件格式，前端即使已经由
> Vite 提供页面，healthcheck 仍可能失败。最终修复把 lock 文件作为唯一依赖权威，把镜像
> 源只当传输通道，校验 lock 语义，检查最终镜像，并要求 fresh-image Playwright 通过后才
> 允许出货。

## 1. Context

Project Hardening PH-008 要求两次 clean build 解析相同依赖图，并证明运行镜像使用
non-root 用户、没有复制本地 secret、能通过健康检查和浏览器烟测。此前基础实现已经有
`backend/requirements.lock`、`frontend/package-lock.json` 和非 root frontend 用户，
但 clean build 卡在：

- `files.pythonhosted.org` TLS `SSLV3_ALERT_HANDSHAKE_FAILURE`；
- npm registry TLS 同样握手失败；
- npm CLI 曾经出现内部失败，提醒我们不能只看 BuildKit 是否导出了镜像。

## 2. Investigation

第一步不是直接改 Dockerfile，而是复现网络边界：

- host 和 Linux container 均能访问 `pypi.org/simple`，但无法从
  `files.pythonhosted.org` 下载 wheel；
- `registry.npmjs.org` 与部分 npm 镜像同样握手失败；
- Tsinghua PyPI mirror 和 Tencent npm mirror 在当前本地网络中可达。

这说明问题不是 Python lock 本身，而是包文件传输路径。为了不把镜像源变成新的依赖
权威，Dockerfile 只把 mirror 作为 build arg transport default：版本仍来自
`requirements.lock` 和 `package-lock.json`。

第二个问题来自 npm：`npm install` 会把 CRLF lock 文件规范化为 LF，字节级 `cmp` 会失败，
但依赖语义没有变化。因此校验从 byte compare 改为 JSON semantic compare，再运行
`npm ls --depth=0` 显式证明安装树存在且可解析。

第三个问题只有 fresh-image runtime 才发现：frontend healthcheck 使用
`http://localhost:3000/`，Alpine `wget` 优先尝试不可用地址时返回 connection refused；
改成 `127.0.0.1` 后容器健康状态与实际 Vite readiness 一致。

## 3. Root Cause

1. Clean build 依赖外部包文件域名，而本地网络对这些域名 TLS 握手失败。
2. Reproducibility 证明混淆了“lock 文件语义一致”和“文件换行字节一致”。
3. Docker image export 不是 runtime proof；健康检查和浏览器路径必须从最终镜像启动后
   验证。
4. 默认 E2E 套件中有部分 events-backend 场景硬编码了 `18089`，在默认 `3001 -> 18081`
   栈中会被 CORS 拦截，说明浏览器证据必须和端口/后端契约绑定。

## 4. Fix

实现提交：`4742bc8`。

- Backend Docker build:
  - `ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`；
  - `pip install --index-url "$PIP_INDEX_URL" -r requirements.lock`；
  - local package install remains `--no-deps`.
- Frontend Docker build:
  - `ARG NPM_CONFIG_REGISTRY=https://mirrors.cloud.tencent.com/npm/`；
  - `npm install --ignore-scripts --registry "$NPM_CONFIG_REGISTRY"`；
  - semantic JSON compare proves `package-lock.json` did not change as a dependency graph;
  - `npm ls --depth=0` proves the installed tree is valid;
  - frontend healthcheck uses `127.0.0.1:3000`.
- Browser proof:
  - added `@ph008 @real-stack` Playwright smoke;
  - started final images plus MongoDB, Redis, and deterministic Anthropic stub;
  - asserted `/api/health`, Docker health, non-root users, UI Health, and deterministic chat completion;
  - captured `docs/features/assets/ph-008/01-clean-build-runtime.png`.
- E2E contract cleanup:
  - version diagnostic fixtures now track current component versions;
  - prompt-governance events-backend test is excluded from the generic suite and remains available through its dedicated target;
  - persistence tests can choose backend URL based on the active browser stack.

## 5. Evidence

Final two clean builds produced matching dependency manifests:

- backend locked dependency install hash:
  `d841833feb3ca0904f52b0010268f356e95a7f7583fd63fe8e4397c243088415`;
- frontend top-level `npm ls --depth=0` hash:
  `a84fd7fdf983705b5d58818ebbbcd189ce6338edeccf52d4d8f3aa0ae4c22a9d`;
- backend package wheel:
  `financial_agent_backend-0.51.4`,
  `sha256=4d26c6f23d0d233656f1670fda4618acbd009d94faa76c07c4c62b8299923ba1`.

Final images:

- backend: `sha256:464b27b0fef10c78342e7836e362979fbcb9a731ead476905b91a7891b37fdd9`, user `app`;
- frontend: `sha256:ee32bd50ff23195f7e53fc1d5d1468f96fe8d74bb5511d94877b12f0aeb1ca5b`, user `node`.

Quality gates passed: backend ruff/black/mypy/pytest/critical coverage, frontend
Vitest/lint/type-check/build, deterministic eval, default Playwright suite, and
PH-008 fresh-image Playwright.

## 6. Lessons

- A lock file is not enough; the build must prove it consumed the lock without
  resolving a different graph.
- Mirrors should be transport choices, not dependency authority. Keep versions in
  committed lock metadata.
- Compare lock semantics when tools normalize formatting.
- Do not accept a Docker export as proof of a usable runtime image. Inspect users,
  healthchecks, image history, and run a browser through the final image.
- Browser E2E tests that hardcode backend ports must either be excluded from the
  generic suite or derive the backend URL from the active stack.
