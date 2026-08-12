---
title: Typed Boundaries Restored Frontend Lint Signal
status: shipped
version: frontend@0.32.3
last_updated: 2026-08-06
owner: maintainer
related_paths:
  - frontend/src/services/api.ts
  - frontend/src/types/agentEvents.ts
  - frontend/src/components/chat/useAnalysis.ts
  - frontend/.eslintrc.cjs
---

# Typed Boundaries Restored Frontend Lint Signal

> **TL;DR (EN)**: ESLint technically passed while emitting 435 warnings, so new
> unsafe API and SSE regressions were indistinguishable from existing debt. The
> fix validated unknown network data, removed production `any`, repaired hooks
> and accessibility, enforced zero production warnings, and isolated the
> remaining 131 warnings to test/E2E code behind a non-increasing CI budget.
>
> **TL;DR (中文)**：ESLint 虽然退出成功，却输出 435 个 warning，新的 API/SSE
> 不安全回归会被既有债务淹没。本次修复为未知网络数据增加运行时验证，移除生产代码
> 中的 `any`，修复 Hook 与可访问性问题，对生产源码实行零 warning，并将剩余 131
> 个 warning 隔离到测试/E2E，通过 CI 预算禁止增长。

## 1. Context

Frontend 已启用 TypeScript strict、安全和性能插件，但绝大多数高风险规则仅为
warning。最大的集中点位于聊天 stream reducer、analysis formatter、chart overlay
和错误响应处理，这些位置恰好也是 Backend 数据进入 React state 的边界。

## 2. Investigation

按生产代码与测试代码分层后，435 个 warning 中有 135 个来自生产源码。主要机制
包括：Axios 未指定 response 类型、`JSON.parse` 后直接断言 `StreamEvent`、chat
message updater 使用 `any[]`、图表 raw data 使用多层 `any`，以及 typed dictionary
访问被 security plugin 报告但没有统一的安全访问模式。

浏览器测试还揭示了测试环境边界的重要性：UAW-005 必须连接 cancellation 专用
backend，不能把不同 fixture app 的失败解释为产品回归。

## 3. Root Cause

- TypeScript 类型只覆盖编译期，没有验证网络运行时 shape；
- 单个 435-warning 总预算没有区分生产风险与测试 fixture 债务；
- dynamic object access、Axios error 和 JSON payload 没有统一 helper；
- modal backdrop、label 和 resize handle 依赖鼠标行为，可访问性契约不完整；
- Hook dependency warning 被长期视作噪声。

## 4. Fix

- `unknown` SSE payload 通过 envelope/event validators 后才 dispatch；
- malformed optional event 记录 warning 并跳过，不终止后续有效 stream；
- API errors、portfolio responses、chart metadata 和 tool state 使用明确类型；
- 引入 audited typed-record accessors，替代任意对象注入；
- 修复 stale closure、Hook dependency 和 unsafe regex 长输入回归；
- modal backdrop 改用 button，所有 touched labels 绑定 control，resize handle 支持键盘；
- `lint:production` 对生产源码执行 `--max-warnings 0`；
- 测试/E2E warning ceiling 从 435 降到 131，并在 CI 中禁止增长。

实现提交：`1a35c1b`。

## 5. Lessons

- `as StreamEvent` 不是运行时验证，SSE/JSON 边界必须先检查 shape。
- 总 warning 数如果过高，就不再提供审查信号；应按信任边界分层。
- 测试代码可以保留显式预算，但生产代码必须有更严格的零 warning 门禁。
- 可访问性修复通常同时改善生命周期：button backdrop 和 keyboard resize 比 div
  mouse listener 更容易推理和测试。
- E2E fixture 必须与场景匹配，否则测试失败只能证明环境接错，而非功能错误。
