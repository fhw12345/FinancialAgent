---
title: Native Copilot Is Not a URL Change
status: in-progress
version: backend@0.52.0, frontend@0.33.0
last_updated: 2026-09-15
owner: maintainer
related_paths:
  - backend/src/agent/llm_factory.py
  - backend/src/agent/copilot_chat_model.py
  - backend/src/services/copilot/
  - frontend/src/components/CopilotConnection.tsx
  - scripts/run-ci-browser.sh
---

# Native Copilot Is Not a URL Change

> **TL;DR (EN)**: FinancialAgent previously constructed ChatAnthropic for every
> provider. Native Copilot required a distinct OAuth and Responses boundary, not
> copying pi's token or replacing the base URL. Request-local account/model binding,
> private durable credentials, exact tool-stream replay, and real browser plus live
> account tests establish the new path. Publication is still pending at this checkpoint.
>
> **TL;DR (中文)**：原工厂始终返回 ChatAnthropic，不能靠换 URL 变成 pi 那样的
> Copilot 直连。此次新增独立 OAuth、私有凭据存储和 Responses adapter，并验证
> 模型/账号绑定、工具流回放、真实浏览器和真实账号。当前检查点尚未完成最终发布。

## 1. Context

用户希望像 pi 的 GitHub Copilot provider 一样，登录自己的账号后直接使用模型，
不再依赖本地 copilot-bridge。检查发现 pi 的当前模型使用 Responses 协议，而
FinancialAgent 的旧工厂始终创建 Anthropic-compatible client。

没有读取 pi/gh token 用于认证，没有新增 coding-agent shell/file 工具，也没有启动
PH-009 或 IDQ 投资策略改造。GitHub CLI 的 PR 授权与 Copilot 的模型授权保持分离。

## 2. Investigation

直接连通要同时解决：设备 OAuth、短期推理凭据、账号模型可用性、工具 schema、
流式事件、结果回传、取消、usage 和结构化输出。只复制一个短期token既不能持续刷新，
也无法保证其适用于正在请求的模型／账号。

对照 pi 的公开协议实现后，采用固定 GitHub 授权端点及允许列表内 Copilot HTTPS
端点。v1 只处理账号允许的 GPT Responses 模型，不自动启用模型政策或假装支持全部协议。

## 3. Boundary and Race Findings

- **凭据边界**：GitHub token、推理 token、device_code只在后端私有SQLite状态中。
  API只返回授权状态、显示给用户的设备码和可用模型；不返回provider错误原文。
- **迟到授权**：logout不等待网络锁，立即换generation；旧poll/refresh通过CAS无法
  重新写入账号。浏览器也通过epoch和AbortController拒绝迟到响应。
- **刷新风暴**：普通expired刷新有single-flight；并发401还要比较被拒绝token的revision，
  否则每个等待者仍会重复exchange。新增十请求并发负例证明只刷新一次。
- **任务上下文**：LangGraph节点可能位于不同asyncio task，ContextVar不能单独证明
  每轮绑定。除request-local profile外，native AI消息也携带非秘密的model/generation。
- **流式回放**：函数ID、增量参数和最终参数必须一致；opaque reasoning只回放给同模型。
  非法JSON、incomplete、无terminal、重复terminal和变更tool ID都不能伪装成功。
- **取消**：HTTP流在取消时关闭；不在已有输出后静默重播请求或切换provider。

## 4. Validation

- Backend: 2051 passed, 27 live integrations deselected; coverage rounds to 71%,
  all critical floors passed; Ruff/Black/mypy (288 source files), Bandit/actionlint pass.
- Frontend: 258 passed, production warnings 0, total test/E2E warnings 131, types/build pass.
- Two clean builds have equal complete installed manifests and frontend asset hashes.
- Image-only validation: native browser 2 passed, existing hardening smoke 6 passed,
  default E2E regressions 11 passed. App source/dependencies were not bind-mounted.
- Curated screenshots explicitly show a **Recorded GPT** fixture, not real account entitlement.

用户随后在 GitHub 完成了独立授权。真实账号发现包含 gpt-6-astra 的模型列表，原生
Pydantic连接测试通过。另一组两次、有界的真实请求执行本地整数工具（2→3），回传
工具结果后得到3：first usage 63 input/19 output，final 58 input/5 output。
最终镜像重建/recreate后，登录与选择仍保留，真实结构化测试再次成功。

这些token数是使用量，不是API密钥，也不等于已知的美元费用。没有把fixture推理
冒充live推理；没有把登录成功等同于所有模型都有权限。

## 5. Lessons

1. A provider boundary includes authentication, protocol and lifecycle—not just URL/model.
2. Separate authorization, entitlement, selected model and verified inference in the UI.
3. Keep credentials out of browser storage, images, test artifacts and unrelated applications.
4. Refresh coordination needs to cover concurrent rejected tokens, not only expiration.
5. Preserve tool identities and opaque protocol state without granting new tool authority.
6. Recorded tests prove failure paths; actual account tests prove the available integration path.
7. Clean images, preserved login, hosted checks and publication remain distinct acceptance steps.

See [feature contract and evidence](../features/native-github-copilot-provider.md) and
[clean-build receipts](../features/assets/ghc-001/clean-build-validation.json).
