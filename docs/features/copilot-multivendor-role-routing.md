---
title: Copilot Multi-Vendor Models and Role Routing
status: shipped
version: backend@0.53.0, frontend@0.34.0
last_updated: 2026-09-16
owner: maintainer
related_paths:
  - backend/src/services/copilot/
  - backend/src/agent/copilot_chat_model.py
  - backend/src/agent/llm_factory.py
  - backend/src/agent/portfolio/agent.py
  - backend/src/services/translation_service.py
  - frontend/src/components/CopilotConnection.tsx
---

# GHC-002：多厂商模型与真实角色路由

## Scope and Baseline

在 GHC-001 的原生 OAuth 上扩展账号目录中可选、支持工具的 GPT/Gemini/Grok 模型，
明确排除 MAI/Microsoft、隐藏旧版/embedding和不支持的协议。当前目录符合此范围的有
16款：GPT10、Gemini Flash4、Grok2；这不是永久硬编码数量，也不是每次workflow同时调用16款。
不启用未授权模型政策，不复制pi/gh凭据，不改投资策略，不启动PH-009或IDQ。

保留默认模型，新增可持久化角色override与版本；初始迁移保持旧默认gpt-6-astra，不因
部署自动改变已有用户配置。多厂商preset需显式应用；不能只改变展示而未改变实际请求。

## Model / Protocol Contract

- GPT/Grok使用目录声明的Responses；Gemini使用Chat Completions。没有支持的endpoint
  就不准调用；同endpoint也要按模型能力处理参数，不能盲目复用GPT专属reasoning字段。
- 接口适配普通/流式文本、并行工具增量JSON、tool result、结构化输出、usage、拒绝、
  incomplete、取消和断流。文本以外输入仍明确不支持。
- Chat Completions必须看到合法finish_reason，usage不得双计；缺失usage不得伪造为0。
- Gemini reasoning/signature等replay字段保留为私有协议状态，不展示为正文；仅相同
  model/API/role的工具循环回放。跨模型/角色只传可移植文本和工具事实，不搬opaque状态。
- 只重试输出前的一次401刷新；限流/权限/模型不兼容显式失败，不能静默换厂商。
- 每个请求记录实际绑定的role/model/API/routing revision；模型目录可选不等于完成live验证。

## Role Routing

统一角色源：router、simple_chat、react_agent、portfolio_research、portfolio_decisions、
sub_technical、sub_news、sub_financial、sub_debater、verdict、summary、translation、
consistency_check、eval_judge；deep_planner保留为reserved配置，不声称固定图中已执行。

- 翻译脱离verdict，consistency check脱离simple_chat，但非native provider保持原模型默认。
- Portfolio Phase1/Phase2通过小型scope wrapper选择research/decisions角色，复用原ReAct
  图和工具；不修改超长Phase1源文件，也不重新创建昂贵单例。
- 一个request/background run捕获完整routing snapshot，后续配置只影响新run；不同角色
  可以有不同模型，同角色tool loop不能在中途换模型。logout使旧account generation失效。
- 更新映射是whole-map、乐观版本校验；非法role、MAI、disabled/消失模型使整次更新失败，
  不部分写入。默认模型仍是未覆盖角色的fallback，但上游调用失败时不自动fallback。
- Health显示默认模型、每角色生效模型/协议及override；可以恢复全部使用默认模型。
  不把internal-only变体选为推荐默认，不承诺厂商品牌意味着更高研究质量或更低计费。

候选preset（仅在目标均可用时完整应用，缺任何一个就明确提示）：

| Roles | Candidate |
| --- | --- |
| router/simple_chat/summary/translation/consistency_check | gpt-5.4-mini |
| react_agent/portfolio_research/sub_financial/sub_technical/deep_planner | gpt-5.6-sol |
| sub_news | gemini-3.8-flash |
| sub_debater | grok-4.6 |
| portfolio_decisions/verdict | gpt-6-astra |
| eval_judge | gpt-5.4（独立可配置；评估该模型本身需另选judge） |

## Validation Plan

- [x] Catalog: 16代表条目均可识别正确协议，MAI/隐藏/disabled/embedding/未知协议拒绝。
- [x] Role map: 默认兼容、持久化/restart、非法值、stale revision、并发修改与logout均正确。
- [x] 一次run不同角色使用不同模型；同角色tool loop冻结；账号/角色/API变化不回放opaque。
- [x] Gemini Chat Completions text/并行tools/structured output/usage/reasoning metadata可回放。
- [x] Grok Responses不发送GPT专属include；旧GPT行为与GHC-001测试不回退。
- [x] 真实Portfolio Phase1/Phase2、translation/consistency调用点使用相应角色，不只是工厂单测。
- [x] Playwright通过Health配置→保存→reload→真实Chat/测试请求验证model/API；MAI不可选，
  stale配置保存不能覆盖，错误推理不显示成功；截图存于`assets/ghc-002/`。
- [x] 用独立已授权账号做少量、有界的逐模型兼容性请求，结果包含成功/失败和协议，不
  把catalog可见冒充成功；不进行16模型默认fan-out或投资效果宣传。
- [x] 全量backend/frontend/coverage/安全门禁、两次clean build与最终镜像E2E通过。
- [x] 版本/changelog/案例/索引、实现hash、protected PR CI、push及合并已记录。

## Failure / Security / Rollback

凭据仍只在原有私有卷；API控制保留Origin/header保护与限流。角色映射只包含模型ID，
不能配置上游URL、headers或工具权限。日志/截图/报告不包含tokens或原始OAuth响应。
取消关闭HTTP流，后台迟到结果不能恢复已退出账号。回滚为清空overrides并选一个已验证
默认模型；保留历史run所记录的模型/协议，不重标旧记录。旧GHC-001功能保留。

## Evidence

已于2026-09-16通过受保护的 [PR #6](https://github.com/fhw12345/FinancialAgent/pull/6) 合并，未使用管理员绕过。

- 实现：`0719b92389f211018ce93d8cd2573bd64a0b903d`。
- 合并：`c00efe6d884eb8dd49090dd49aa47a54c3d28208`。
- [Hosted CI](https://github.com/fhw12345/FinancialAgent/actions/runs/35055009845)全部门禁通过，
  包括6个既有与4个Copilot浏览器场景；两份报告已下载核验，artifact不含credential文件。
- [Hosted receipt](assets/ghc-002/hosted-validation.json)保存身份、artifact和report hashes。

- Backend **2061 passed / 27 deselected**；Ruff/Black/mypy（291 source files）、Bandit与所有关键coverage floors通过。
- Frontend **261 passed**；production lint 0 warnings、全量test/E2E warning ceiling 131、类型检查通过。
- 两次clean build完整依赖manifest一致（backend 120 distributions、frontend 746 package paths），
  frontend production asset hashes一致；[build receipts](assets/ghc-002/clean-build-validation.json)。
- 最终image-only浏览器：**4 Copilot + 6 hardening smoke + 11 default E2E passed**，
  后端仅挂载测试fixtures，前端没有应用或依赖mount。
- [角色分流截图](assets/ghc-002/01-multivendor-roles.png) 和
  [陈旧保存被拒绝](assets/ghc-002/02-stale-routing-rejected.png) 来自录制外部传输、真实API/存储。
- [真实账号验证](assets/ghc-002/live-validation.json)：16/16模型结构化调用通过；Gemini3.8与
  Grok4.6真实工具结果回传通过。每次最多512 output tokens，未调用MAI；单次延迟不是性能排名。
- 最终镜像保留原授权与默认Astra；随后通过版本化API显式应用建议分流，sub_news、
  sub_debater、translation的真实role测试分别请求Gemini/Grok/GPT并通过。

兼容性回归还验证了翻译/consistency真实调用点和实际Portfolio Phase1/Phase2的角色scope。
测试曾发现fixture把Gemini答案经翻译改成了GPT的固定占位文本；修复的是外部录制响应及
已知fixture缓存，而不是放宽真实模型路由断言。另一个UI竞态是晚到的角色保存可能覆盖
退出状态；以单调routing revision拒绝旧响应，并加入同一render batch回归。

模型目录依据为2026-09-16账号能力字段；Claude未出现在目录，不纳入本任务。
应用是否带来更好的投资决策仍需IDQ评估，此处不作收益或质量提升声明。
