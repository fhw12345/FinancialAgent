---
title: Native GitHub Copilot Provider
status: shipped
version: backend@0.52.0, frontend@0.33.0
last_updated: 2026-09-16
owner: maintainer
related_paths:
  - backend/src/agent/llm_factory.py
  - backend/src/core/config.py
  - backend/src/main.py
  - frontend/src/pages/HealthPage.tsx
  - docker-compose.yml
---

# GHC-001：Python 原生 GitHub Copilot 登录与模型连接

> 本页保留0.52.0/0.33.0的初始出货范围与证据。后续多厂商协议、角色覆盖和当前配置说明
> 见 [GHC-002](copilot-multivendor-role-routing.md)；下文“v1仅GPT/所有角色同模型”是历史范围。

## Scope

方案 A：保留 FastAPI/LangGraph，在 Python 中直接完成 GitHub device OAuth、Copilot
短期token刷新、账号模型发现和Responses调用。不依赖pi进程、copilot-bridge或Node
sidecar，不复制pi/gh CLI凭据。仅支持github.com账号；v1支持具备tool calls的GPT
Responses模型，其他协议明确不支持。所有角色使用用户选中的一个模型。

Health页面提供登录、设备码、状态、可用模型选择、显式消耗额度的连接测试和本地退出。
`LLM_PROVIDER=github_copilot`启用应用路由；原maestro/anthropic/copilot_reverse保持原样。
未配置native模式时仍可授权/测试，但必须明确应用尚未切换，不能假装聊天已走新provider。

PH-009及IDQ功能均不实施。Copilot权益、模型许可、组织政策与额度由上游决定；不绕过
限流、不自动启用未获许可的模型、不承诺官方第三方服务SLA。

## Contracts

- 独立私有本地凭据目录，Linux目录0700/文件0600；Docker专用持久卷，非root用户。
  凭据不存Mongo、浏览器、Git、镜像或普通artifacts。不声称应用层加密；主机账户是信任边界。
- GitHub device_code只留后端，UI仅收到user_code、固定GitHub验证地址、随机attempt ID。
  尊重interval/slow_down/expiry；重试不重复启动，取消/退出后迟到授权不能恢复登录。
- GitHub授权和Copilot订阅可用是不同状态。token/模型请求失败不假报连接成功。
- 刷新single-flight，持久化原子；短期token过期前刷新，401最多在输出前重取一次。
  429/403/网络/截断流是明确错误，不在已输出后透明重播模型请求。
- 只向固定GitHub授权地址和严格允许的Copilot HTTPS域发送凭据，无重定向凭据泄露。
  用户不能通过API自定义上游URL；外部错误体不写日志/API。
- 模型必须存在于当前账号可用catalog并支持本adapter；不硬编码“任意模型名均可用”。
  使用Responses `store=false`；保留tool IDs、工具结果、opaque reasoning replay及usage。
- 兼容LangChain普通/流式调用、bind_tools和Pydantic structured output；不引入coding工具。
  GPT reasoning模型不发送不兼容temperature。stop sequences/不支持的输入明确拒绝。
- 请求/后台run绑定模型与账号generation，改模型不改变已开始的请求；logout使旧绑定失效。
- 控制API要求本地action header并检查Origin，拒绝跨站登录/切换/退出；状态响应no-store。
- 本地退出清除本应用凭据，不宣称撤销GitHub端授权，也不影响pi登录。

## Implementation Slices

1. 协议与安全边界、凭据store、device flow和catalog；先写录制HTTP正/负例。
2. Native BaseChatModel adapter与request-local绑定；接factory，不改研究策略。
3. Health连接面板、状态机和API；无静默付费测试、无自动打开授权页面。
4. 真实API/存储/Chat/LangGraph测试，仅外部GitHub/Copilot传输使用fixture。
5. 用户单独浏览器授权；显式小token smoke记录实际兼容性，不公布任何真实凭据。
6. 全套门禁、两次clean build、fresh-image browser、截图、版本/changelog/案例、双提交与PR。

## Validation / Acceptance

- [x] device pending/slow_down/deny/expiry/cancel/logout/restart和迟到响应不会错写状态。
- [x] 并发刷新不重复exchange；token写失败不报成功；安全路径/权限/重定向/URL域限制通过。
- [x] 模型disabled/无tool/不支持协议/消失/变更/未选择都有可判定错误。
- [x] 消息转换覆盖user/system/assistant/tool、Unicode、多个工具、reasoning replay。
- [x] 增量tool JSON与text流正确，usage不双计；failed/incomplete/断流不能显示完成。
- [x] cancel关闭HTTP流；无late成功、无泄露prompt或token的异常。
- [x] 真LangGraph执行工具→回传→最终回复；Pydantic结构化输出通过且非法输出拒绝。
- [x] 旧三个provider路由测试及全量backend/frontend/安全门禁不回退。
- [x] Playwright：Health登录pending→授权→选模型→显式连接测试→真实Chat回复→刷新恢复→退出；
  另测deny/expired/不支持模型/错误测试。固定viewport，截图在断言后保存至
  `docs/features/assets/ghc-001/`，录制外部传输但真实路由与存储，不冒充live权限证明。
- [x] 实际登录/小额度推理证据与fixture证据分开；实际账号与最终镜像推理已验证。
- [x] 版本、镜像、curated截图、实现hash、CI链接、changelog和双语案例已记录。

## Risks / Rollback

Copilot非静态API可能变化；依照pi公开provider实现核对OAuth与headers，但本应用独立维护
Python adapter。账号可能没有Responses模型或受组织限制，需原样提示，不能改写策略。
凭据目录丢失需重新授权；logout后旧token可能已发往上游，不能撤回已执行的请求。
切回原LLM_PROVIDER并force-recreate backend可回滚；不删除用户pi/gh凭据，不修改账号模型政策。

## Evidence

Initial investigation: current pi selects github-copilot with Responses; existing FinancialAgent
factory always constructs ChatAnthropic, so native transport requires an adapter, not merely a URL change.
Reference: [pi Copilot OAuth](https://github.com/earendil-works/pi-mono/blob/main/packages/ai/src/auth/oauth/github-copilot.ts)
and [Copilot headers](https://github.com/earendil-works/pi-mono/blob/main/packages/ai/src/api/github-copilot-headers.ts).
Shipped through protected PR #4 on 2026-09-15 after local, image-only, live-account and hosted CI validation.

- Implementation: `5b097d086ec109a7720ab8afcb8443bc2c85d10a`.
- Additional browser negatives: `6e5ba294cfb733674d2f54a5de26af87c174b4cc` (tests only; application inputs unchanged).
- Merge: `94a190f2d1838de198eb4a9e94b85c2e15ede495`, [PR #4](https://github.com/fhw12345/FinancialAgent/pull/4).
- [Hosted run](https://github.com/fhw12345/FinancialAgent/actions/runs/34953213465) passed every gate,
  including 6 hardening and 3 native browser cases. Both reports were downloaded and checked;
  [hosted receipts](assets/ghc-001/hosted-validation.json) record artifact identities/hashes and no credential files.
- [Live receipts](assets/ghc-001/live-validation.json) are separate from recorded browser proof.

## 2026-09-15 Implementation and Live Verification

Implemented private SQLite credential state/CAS, serialized refresh and rejection-aware single-flight,
OAuth pending/slow-down/denial/expiry/cancellation, strict endpoint allowlisting, model catalog filtering,
request-local and tool-loop model/account binding, native Responses streaming, and a bilingual Health panel.
Stream failures and invalid tool arguments fail explicitly; OAuth state never enters API responses or traces.

Local gates: backend **2051 passed / 27 deselected**, aggregate coverage rounds to 71%; Ruff/Black,
strict mypy across **288** source files, Bandit, actionlint passed. Frontend **258 passed**, production
lint zero warnings, total warning budget **131**, types and build passed. Recorded browser acceptance
passed login → select → native structured test → real Chat/Mongo reload → logout, and denial handling.

The maintainer separately authorized the real account. Account catalog discovery exposed permitted
GPT Responses models, and **gpt-6-astra** passed a real structured-output connection test. A second,
bounded two-request test called a local integer tool with value 2, returned its result through the native
Responses tool-result protocol, and received `3`. Usage: first request 63 input / 19 output tokens;
second request 58 input / 5 output tokens. These are inference tokens, not credentials or a dollar-cost
claim. No pi/gh credentials were read for authentication and no bridge endpoint was used.

Real credentials live only in the dedicated `financialagent-copilot-live_credentials` Docker volume.
The isolated live stack uses UI `http://localhost:3013` and backend `http://localhost:18095`; it has its
own Mongo database and does not move or overwrite the default stack's portfolio data.

## Run / Reproduce

After building the normal backend/frontend images:

```bash
# Real account, separate from the recorded acceptance stack:
docker compose -f docker-compose.copilot-live.yml up -d --force-recreate
# Open localhost:3013 -> Health -> GitHub Copilot.
# Sign in, approve on GitHub, refresh models, select one, explicitly test.

# Recorded external OAuth/LLM, but real app/API/storage; never real credentials:
docker compose -f docker-compose.copilot.yml -f docker-compose.copilot-images.yml up -d --no-build backend frontend mongodb redis
UPDATE_E2E_EVIDENCE=true docker compose -f docker-compose.copilot.yml -f docker-compose.copilot-images.yml run --rm --no-deps browser
```

For the normal default stack, set `LLM_PROVIDER=github_copilot` in the ignored local env file and
force-recreate backend. The default stack has its own dedicated credential volume, so its first login
is independent of the isolated live stack. No automatic credential copying is performed.

CI runs `scripts/run-ci-browser.sh` then `scripts/run-ci-browser.sh copilot`. The latter uses a private
`mktemp` credential directory outside artifacts and preserves earlier browser reports before running
its own suite. The CI tests do not log in to GitHub or consume real inference allowance.

Curated screenshots are recorded fixtures, not proof of real account entitlement:

- [Native login/model/structured-test panel](assets/ghc-001/01-native-copilot-connected.png).
- [Denied authorization remains disconnected](assets/ghc-001/02-native-copilot-denied.png).
- [Rate-limited inference is not reported successful](assets/ghc-001/03-native-copilot-rate-limit.png).

Final local acceptance passed: two clean builds have matching full installed manifests and frontend
assets; both app image users are UID 1000 and no credentials/env files are baked in.
[Image receipts](assets/ghc-001/clean-build-validation.json) identify the final backend/frontend images.
Fresh-image tests passed **3 native Copilot + 6 hardening smoke + 11 default E2E** cases, with backend
mounting tests only and frontend mounting nothing. The screenshots above were regenerated on those images.
The real-account stack was then recreated without application/dependency mounts: authorization/model
selection survived in its private volume and the real structured inference test passed again.

Protected hosted validation and implementation merge are complete; this shipment documentation
records their immutable identities. PH-009 and all IDQ runtime work remain unstarted.
