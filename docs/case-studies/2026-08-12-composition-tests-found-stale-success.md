---
title: Composition Tests Found Stale Failure After Success
status: shipped
version: backend@0.51.3
last_updated: 2026-08-12
owner: maintainer
related_paths:
  - backend/src/agent/langgraph_react_agent.py
  - backend/src/agent/portfolio/phase2_decisions.py
  - backend/tests/test_react_agent_composition.py
  - backend/tests/test_portfolio_flow_composition.py
---

# Composition Tests Found Stale Failure After Success

> **TL;DR (EN)**: Unit tests covered retry calculations and individual models,
> but not the complete ReAct and Portfolio lifecycles. Composition tests found
> that a transient exception remained set after a successful retry and was
> re-raised, while Phase 2 failure history silently used a Message source value
> rejected by the real Pydantic contract. Real internal composition plus outer
> fakes exposed both defects and established per-module coverage floors.
>
> **TL;DR (中文)**：单元测试覆盖了重试计算和独立模型，却没有覆盖完整 ReAct 与
> Portfolio 生命周期。组合测试发现，瞬时异常在重试成功后仍被保留并再次抛出；同时
> Phase 2 失败历史使用了真实 Pydantic 契约不接受的 Message source。通过“内部真实
> 组合、外部 fake”暴露并修复了两个问题，并建立关键模块覆盖率门禁。

## 1. Context

Backend 已有接近两千个测试，但 aggregate coverage 掩盖了关键编排模块的低覆盖：
ReAct 约 36%、Portfolio flows 约 12%、Phase 1/2/3 多数低于 40%。许多测试在
service method 入口就 mock 掉内部模块，因此不能证明输出能被下一阶段消费。

## 2. Investigation

新测试只 fake 最外层 model/provider/storage transport，真实执行：

- ReAct message conversion、retry、zero-tool guard、token/tool accounting；
- Portfolio dashboard flow、consistency metadata、translation 和 persistence；
- Phase 1 batching/dedup 到 Phase 2 message，再到 Phase 3 suggestion；
- DataManager Treasury、IPO、news、insider 和 historical-price fallback；
- deterministic SELL、short-cover、BUY scaling 和 message metadata。

瞬时 timeout 后第二次调用成功，但 `last_exception` 仍指向第一次 timeout。循环退出
后 post-loop guard 再次抛出旧异常，将成功结果改写成失败。另一个测试进入 Phase 2
无研究结果分支，真实 `MessageCreate` 立即拒绝 `source="system"`；原测试 mock
repository，未构造真实 Pydantic model，所以从未发现。

## 3. Root Cause

1. Retry loop 把“最后一次失败”当成跨 attempt 状态，却没有在成功时清空。
2. Failure-history 路径缺少真实 schema boundary。
3. Aggregate coverage 没有对高风险 orchestration 单独设 floor。
4. Mock 位于内部模块之间，而不是系统的外边界。

## 4. Fix

- ReAct 成功返回后立即清空 stale exception；
- Phase 2 assistant failure message 使用合法的 `source="llm"`；
- 新增四个 composition suites，覆盖 model retry、provider fallback、Mongo
  degradation、cancellation、structured validation 和 Phase 1→2→3 continuity；
- CI 生成 `coverage.json`，通过 `scripts/check-critical-coverage.py` 执行逐模块 floor；
- 浏览器重新验证 Portfolio completion 与 cancellation reload persistence。

实现提交：`54252dc`。

## 5. Lessons

- Retry success 必须显式覆盖之前的失败状态。
- Failure path 与 success path 一样需要真实 domain schema。
- Composition test 的 fake 应放在 HTTP、LLM、provider、database transport 外边界。
- Aggregate coverage 适合趋势观察，不适合保护关键 lifecycle。
- 覆盖率门禁应与持久化、terminal state、禁止副作用等不变量一起使用。
