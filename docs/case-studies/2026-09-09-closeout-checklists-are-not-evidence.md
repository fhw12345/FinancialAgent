---
title: Closeout Checklists Are Not Evidence
status: in-progress
version: backend@0.51.5, frontend@0.32.5
last_updated: 2026-09-09
owner: maintainer
related_paths:
  - frontend/src/components/chat/AssistantMarkdown.tsx
  - backend/src/services/insights/snapshot_inputs.py
  - backend/src/services/data_manager/cache.py
  - backend/src/core/provenance.py
  - backend/src/agent/tools/sec_edgar/form4.py
  - .gitleaks.toml
  - .github/workflows/pr-checks.yml
---

# Closeout Checklists Are Not Evidence

> **TL;DR (EN)**: Re-running hardening acceptance found gaps that old green
> screenshots could not prove: Markdown images still loaded remotely, Insights
> refresh bypassed snapshot prefetch, and Redis fallback repeated provider failures.
> Test-first fixes, explicit eval provenance, real browser/provider-count proof,
> and clean-image comparisons now pass locally. GitHub authorization and hosted
> PR evidence are still required before shipment.
>
> **TL;DR (中文)**：复核 hardening 验收发现，旧的绿色截图没有证明真正契约：Markdown
> 图片仍会联网，Insights 刷新绕过 snapshot prefetch，Redis fallback 还会重复失败的
> provider 调用。通过失败测试驱动修复、明确 eval provenance、真实浏览器/provider
> 计数和 clean-image 对比，本地门禁已通过；GitHub 授权及真实 PR 证据仍是出货前提。

## 1. Context

本轮从已同步且 clean 的 `ddf4284` 开始，复核 PH-001/002/005/010 并补齐 PH-004。
最初 Docker Desktop 没有启动，`18081` 无监听是引擎不可用的结果，不是后端回归。
执行 `docker desktop start` 后恢复引擎，并改用有边界的 readiness 检查。

## 2. Investigation

- **网络边界**：旧脚本只识别特定短语法；改为渲染所有 Compose profiles，再检查
  published ports。`--no-env-resolution` 让 CI 不依赖本地秘密 env 文件。
- **Markdown**：旧语料只有 `<img>`，没有 `![image](https://...)`。新增回归先失败，
  再明确拒绝 `img`。只抽出 renderer，ChatMessages 降至 406 行；截图复查还发现
  fenced code 文字/背景同色，通过浏览器失败断言后修复 CSS 继承。
- **版本**：旧截图 mock 了 backend Health。本轮核对真实 root/Health/OpenAPI/UI，
  并补齐 source/installed/missing-package fallback。
- **共享预取**：UI refresh 原来走 registry，snapshot 是另一条 admin 路径；metric
  calculators 也没有消费预取结果。Python 签名测试不能替代这个缺失的调用链。

## 3. Fix the Boundary, Not the Screenshot

PH-002 现在先解析动态 AI basket，通过真实 DataManager 编排获取 full 日线、两种
Treasury、news、IPO，再创建只属于本次计算的 provider view。已有 calculators 消费
同一批 typed inputs，singleton 不被修改；非共享能力仍使用原 provider。

真实浏览器点击刷新，以可控 fixture barrier 验证 loading，再释放预取。随后检查一次
prefetch、每个共享来源一次请求、七项 metrics、Mongo snapshot，以及 API/UI composite
一致。旧 UI-mocked test 保留为渲染回归，但不再覆盖 PH-002 的真实证据截图。

最终复查把真实 `RedisCache.get_with_dedup` 也纳入组合测试后，又复现了失败来源被
请求两次：cache wrapper 捕获了 provider error，然后再执行 simple-fetch fallback。
修复跟踪 callback 的成功和失败，只在 fetch 之前的缓存 transport 错误允许 fallback；
fetch 成功后的 cache write/unlock 失败保留已有数据；被 dedup 吞掉的 provider error
重新抛出。未配置 Redis 时仍直接 fetch，programming errors 不被当作缓存降级。

外发及持久化的 `prefetch_errors` 保留 source identity，但不复制原始 provider URL/
credential 内容。存储失败也不会返回 refresh success。

## 4. New Security Gates Must Be Allowed to Fail

Bandit 的两处 SEC XML `B314` 与缓存 SHA1 `B324` 没有被豁免：

- 用固定版本 `defusedxml` 拒绝 DTD/entity，保留非法 XML 返回空结果的兼容行为；
- 为满足 touched-source 500 行约束，仅抽离兼容导出的 SEC transport，并跑原有
  fetch/parser tests，不启动整个 PH-009 分解计划；
- SHA1 明确 `usedforsecurity=False`，测试验证旧缓存键不变。

Gitleaks 最初的 5 个发现是 sanitizer tests 中 3 个已知人工字符串。例外必须同时匹配
rule、path 和精确值。负例测试发现固定版本的全局 `[allowlist]` 不支持预期 AND
语义；换成该版本支持的 `[[rules.allowlists]]` 后，在同一文件加入另一人工 token
会正确失败。没有忽略整个 tests 目录或建立泛化的历史发现 baseline。

## 5. Provenance Is Recorded on Execution, Not History Loading

Deterministic/live eval 在启动时捕获 backend version、可用的 commit/source/dirty
状态，live initial/progress/final/failure/budget reports 沿用同一个对象。读取旧 JSON
不补填今天的 provenance；缺失 Git 或慢挂载时明确 unknown，不能伪装成 clean。
JSON 与 Markdown exports 均包含新字段。浏览器验证真实 eval API report 的 backend
version 与 Health 一致；可见 Prompt 区域明确是 configured，而不是伪造 model use。

## 6. Final Local Evidence and Publication Boundary

- Backend: **2,014 passed**, 27 live tests deselected; Ruff/Black/mypy (279 source
  files), critical coverage floors and deterministic eval passed.
- Frontend: **254 passed**, production lint 0 warnings, total budget unchanged at
  131, types and build passed. Windows-mounted old `dist` denied deletion; a fresh
  temporary build directory passed as non-root.
- Two final clean backend/frontend builds have identical full installed manifests
  and frontend production-asset hashes. Both runtime users have UID 1000 and no
  app-local env files. Frontend build context explicitly excludes `.env*`.
- Final image-only browser run: **6 smoke tests and 11 default regressions passed**.
  Backend mounts only test fixtures; frontend mounts no source or dependencies.
- Bandit, Gitleaks, actionlint, policy tests and source-length/version checks pass.

[Build receipts](../features/assets/ph-004/clean-build-validation.json) and curated
screenshots live under PH-001/002/004/005/010 assets. Raw reports remain ignored.

Implementation: `db1e4b8739c21fb160e6eadda65dab53617522aa` (pushed on
`hardening/closeout-ci`).

GitHub CLI is not logged in and no reusable API credential is available. The Git
branch push succeeded, while `gh pr create` exited 4 asking for login. The Git
transport is not blocked merely because gh lacks an API login. There is still no
hosted PR run, verified failure artifact/branch protection, or final shipment
claim. All five tasks remain `in-progress` until the required workflow is complete.

## 7. Lessons

1. Test the real contract, not merely a test bearing its name.
2. Raw HTML blocking and remote-image blocking are distinct controls.
3. Include real internal cache/dedup orchestration; it can introduce hidden retries.
4. Use per-run inputs rather than mutating shared singleton providers.
5. Test scanner exceptions negatively; configuration syntax can silently widen them.
6. Export explicit unknown provenance for history; do not rewrite it on load.
7. Local green gates and clean images are not GitHub Actions shipment evidence.
