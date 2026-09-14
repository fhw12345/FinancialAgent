---
title: Hosted CI Needs Failure Proof
status: shipped
version: backend@0.51.5, frontend@0.32.5
last_updated: 2026-09-14
owner: maintainer
related_paths:
  - .github/workflows/pr-checks.yml
  - scripts/ci-negative-control.py
  - scripts/tests/test_ci_negative_control.py
  - docs/features/assets/ph-004/hosted-ci-validation.json
---

# Hosted CI Needs Failure Proof

> **TL;DR (EN)**: Local green gates did not prove runner compatibility or merge
> enforcement. A real PR exposed a Compose env-file difference. After a minimal
> secret-free fix, explicit mypy/eval/browser probes failed at their real gates
> and retained useful artifacts. A restored normal PR run passed, and the
> implementation merged through enforced checks—not an administrator bypass.
>
> **TL;DR (中文)**：本地全绿不等于 hosted runner 兼容，更不等于失败会阻断合并。
> 真实 PR 暴露了 Compose 对 env 文件存在性的版本差异。最小无密钥修复后，分别让
> mypy、eval、浏览器在真实门禁失败，并下载核验报告／trace。最后正常 PR 重跑全绿，
> 通过强制检查合并，没有使用管理员绕过。

## 1. Context

PH-001/002/005/010 已有提交的截图、完整本地门禁、两次 clean build 及 fresh-image
Playwright。剩余 PH-004 必须拿到真实 Actions 证据，而不是把本地终端截图改名为 CI。
Git push 已可用，但 GitHub CLI API 授权是独立前提；用户在浏览器完成授权与 2FA，
凭据没有进入仓库或文档。

## 2. Investigation and Root Cause

[PR #1](https://github.com/fhw12345/FinancialAgent/pull/1) 的第一个
[run](https://github.com/fhw12345/FinancialAgent/actions/runs/34818319625) 在
Compose config 阶段失败。相同 `--no-env-resolution` 参数在本地允许服务 env 文件
缺失，runner 上的 Compose 仍检查该文件是否存在。

这不是需要把本地秘密复制到 CI 的证据。端口契约只需要 Compose 可渲染；正确修复是
仅在缺失时创建 **空的 ignored 占位文件**，保留 `--no-env-resolution`，不覆盖已有
文件，也不改真实应用运行配置。

仓库最初没有 required check。配置 main 要求 GitHub Actions app 15368 的
`Unit Tests`，严格要求与 base 同步并对管理员生效后，失败的 PR 被观察为 `BLOCKED`。
修复后的正常 PR 则执行全部声明门禁并通过。

## 3. Failure Proof, Not Just a Green Badge

`workflow_dispatch` 提供显式 `probe` 选择，普通 PR 固定为 `none`。脚本在临时
checkout 中、目标门禁之前注入一个故障；非 Actions 或 pull-request 事件拒绝激活。
这避免把故意错误提交进应用代码，也避免并发探针取消普通 PR 的执行。

| 探针 | Run | 核验结果 |
| --- | --- | --- |
| mypy | `34819876537` | 实际 strict mypy 报赋值类型错误并退出 1；下载的 JUnit 含失败 |
| eval | `34819884649` | 将 router threshold 设为不可能的 1.1；CLI 退出 1，JSON/Markdown 记录 observed=1 与 failed gate |
| Playwright | `34819891538` | 六个正常场景通过，故意失败的第七个断言失败；下载 HTML、trace、截图、视频及前后端日志 |

三个 run 都在预期门禁失败，`always()` artifact 上传成功，保留期 14 天。
原始文件不入库；[curated receipt](../features/assets/ph-004/hosted-ci-validation.json)
保存 run/head、artifact ID、到期时间与核验文件哈希。

**边界必须说清**：dispatch 探针不是普通 PR required check，故意失败不会把已绿色
的 PR 变红。它们证明真实命令的失败退出与报告链路；真实 PR 阻断则由最初失败的
required check 单独证明。没有把两种证据混写成“每个手动探针都阻断了 PR”。

## 4. Restoration and Publication

探针后重跑正常 [PR run 34819419375](https://github.com/fhw12345/FinancialAgent/actions/runs/34819419375)
的 attempt 2，全绿且可合并：backend 2,014 tests、mypy 279 source files、frontend
254 tests、六个真实 API browser cases，以及全部 policy/security/coverage/eval gates。
Production lint 仍为零 warning，test/E2E 的 131-warning 上限没有降低。

CI-only 修复 `1e78a4a0e684604dd7467938905fe29d83dfa37e` 没有改变已通过两次 clean build
的应用输入。实现 `db1e4b8739c21fb160e6eadda65dab53617522aa` 和证据提交 `a115fd2`
随 PR #1 正常合并为 `7cc3789b291cfb71865d3cb7a368a965957db5ca`。Backend `0.51.5` /
frontend `0.32.5` 的 PH-001/002/004/005/010 至此满足出货条件。PH-009 尚未开始。

## 5. Lessons

1. Compare runner/tool versions before changing application semantics.
2. Secret-file absence should not be solved by copying secrets.
3. A green workflow badge does not prove failure exits or artifact retention.
4. Verify artifacts by downloading them, not by assuming an upload step is enough.
5. Distinguish dispatch probe outcomes from PR merge-check outcomes.
6. Re-run the unmodified normal path after probes and merge without bypass.
7. Artifact expiry is real; preserve curated identities/hashes and executable probes.
