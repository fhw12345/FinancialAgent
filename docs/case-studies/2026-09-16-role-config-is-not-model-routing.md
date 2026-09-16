---
title: A Role Configuration Is Not Model Routing
status: shipped
version: backend@0.53.0, frontend@0.34.0
last_updated: 2026-09-16
owner: maintainer
related_paths:
  - backend/src/core/llm_roles.py
  - backend/src/services/copilot/context.py
  - backend/src/services/copilot/completions.py
  - backend/src/agent/portfolio/agent.py
  - frontend/src/components/CopilotRoleRouting.tsx
---

# A Role Configuration Is Not Model Routing

> **TL;DR (EN)**: The account exposed GPT, Gemini and Grok, but the original native
> adapter only supported GPT Responses and ignored role names. Supporting multiple
> vendors required protocol-aware streaming and real workflow bindings, not just a
> bigger dropdown. Recorded browser tests, bounded live probes and hosted CI passed;
> protected PR #6 completed the implementation release.
>
> **TL;DR (中文)**：账号有多厂商模型，不等于应用已会调用；有角色配置，也不等于真实
> workflow使用它。此次补上协议分流、真实角色scope与配置版本，并用浏览器、真实账号
> 验证，现已通过hosted CI并以受保护PR #6合并发布。

## 1. Context

用户希望研究使用不同厂商，并明确排除MAI。原始账号目录36条中17条可选；排除MAI后，
目标是GPT10、Gemini Flash4、Grok2。隐藏旧版/embedding不作为正常聊天候选。
GHC-001只实现GPT Responses，因此不能把Gemini名字塞进相同payload后宣布完成。

## 2. Root Causes

- Gemini需要Chat Completions；GPT/Grok用Responses，但Grok不应收到GPT专属reasoning include。
- 原native profile只有一个model，role参数没有改变请求目标。
- Portfolio Phase1/Phase2复用了同一个ReAct实例；仅新增portfolio_research配置不会生效。
- 翻译复用verdict，consistency复用simple_chat，无法独立控制这些成本/延迟边界。
- 同一模型的opaque协议状态不能无差别回放给另一个角色或厂商。

## 3. Implementation Boundaries

用共享角色目录和狭窄ContextVar scope，让实际Portfolio阶段选择research/decisions角色，
不修改595行Phase1实现或重新构建其昂贵单例。非native provider保留原有模型默认。

存储保留默认模型与role overrides，routing revision跨logout也单调增加。一次request
捕获完整不可变snapshot；每次调用记录role/model/API/revision，run也持久化对应元数据。
整个映射经过catalog验证后原子保存，MAI/unknown/stale更新不能部分生效。

Chat Completions适配器处理并行tool增量、finish_reason、独立usage块、reasoning replay、
取消和错误。reasoning不作为正文展示；只在相同model/API/role下携带。

## 4. What the Tests Exposed

浏览器最初看见GPT占位文本，容易误判为Gemini路由未生效。检查真实HTTP记录发现主
回答已走Chat Completions，但录制translation返回了另一种固定文本。修复外部fixture
并清除该已知标记的fixture缓存，而不是降低模型/协议断言。最终run记录与界面均证明
Gemini真实路径，翻译/consistency另有实际调用组合测试。

另一个真实UI竞态：role-save响应与logout响应同一render batch到达时，仅等组件unmount
取消还不够。父组件按单调routing revision拒绝旧结果，避免过期响应恢复已退出界面。

## 5. Evidence and Limits

- Backend 2061 passed / 27 deselected；mypy 291文件无错误；Ruff/Black/Bandit及coverage floors通过。
- Frontend 261 passed；production warnings 0，总test/E2E budget 131未增加。
- 两次clean build完整依赖和frontend资产manifest一致，最终image-only 4+6+11 E2E通过。
- 真实账号16/16小额度结构化探针通过，Gemini3.8与Grok4.6工具回传通过；MAI没有被调用。
- 默认Astra保留，在新镜像上显式应用建议角色映射后，news/debater/translation实际role测试通过。

单次探针延迟不代表性能排名；多厂商不代表独立事实，也不证明投资结果更好。
后续效果验证属于IDQ，PH-009与IDQ实现没有在本任务中启动。

实现 `0719b92389f211018ce93d8cd2573bd64a0b903d` 经
[CI 35055009845](https://github.com/fhw12345/FinancialAgent/actions/runs/35055009845)
验证后，通过PR #6合并为 `c00efe6d884eb8dd49090dd49aa47a54c3d28208`。
下载的artifact保留两套browser reports，不包含凭据文件。

See [feature contracts and receipts](../features/copilot-multivendor-role-routing.md).
