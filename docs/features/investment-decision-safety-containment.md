---
title: Decision Safety Containment Stage A
status: shipped
version: backend@0.54.0, frontend@0.35.0
last_updated: 2026-09-16
owner: maintainer
related_paths:
  - backend/src/agent/portfolio/flows.py
  - backend/src/agent/portfolio/consistency_gate.py
  - backend/src/database/repositories/portfolio_order_repository.py
  - backend/src/services/order_execution_service.py
  - backend/src/agent/deep_react_agent.py
  - frontend/src/components/portfolio/DecisionTracker.tsx
---

# IDQ-001-A：先阻止不可靠建议变成行动

## Boundary

本次仅交付 [IDQ-001](investment-decision-policy-gates.md) 的A阶段。IDQ-002/004/005尚未
接入，因此**任何新AI结果都不具备ready/approved/actionable资格**。不假装已实现组合优化、
PIT证据、用户确认policy或paper审批。完整IDQ-001仍保持in-progress。

继续提供研究、模型草稿和可见评估原因，但不新写入可操作PortfolioOrder。旧AI订单/信号
只读且标legacy/unverified；独立的用户手工买卖登记、持仓编辑不受本次门禁阻断。
用户如要记录实际交易，使用Add Transaction，而不是从未验证AI建议Mark Executed。

## Root Cause / Integration Scope

- consistency gate异常会passed=True；异常被外层吞掉，Phase2仍可给建议。
- pa缺失时两条Dashboard流程直接调用无工具证据的LLM shortcut。
- legacy TradingDecision允许缺字段；多个出口直接写suggested/signal，甚至写失败仍回报成功。
- 现有Mark Executed入口能把旧未验证建议变成持仓/现金修改。

统一出口：新`DecisionAssessment`批次文档及repository/service，portfolio_orders的旧新建/
upsert/batch/fill入口拒绝AI写入，防遗漏旁路。迁移holdings/picks/single-symbol、Deep、
watchlist、legacy optimizer/Phase3到评估记录；不接券商。

仅做必要边界整理：flows的持久化helpers抽出，DecisionTracker的历史显示/统计/研究
展示抽出并去掉执行dialog，使所有被修改source ≤500行。不是恢复PH-009全仓库重构。
legacy TradingDecision和Phase2不做大规模改写。Phase1只抽出原有prompt并拒绝error/empty
研究envelope；旧prompt规则测试改为捕获实际传给agent的文本，不改写研究规则。

## Contracts

- 新批次schema extra=forbid、数值finite；严格草稿与legacy reader分开。
- `readiness`: research_only / insufficient_evidence / needs_review / blocked；A不接受ready。
  `actionable=false`、`action=null`为服务端固定值。BUY/SELL只是可选的untrusted proposal。
- 记录assessment ID、request key/hash、source、run ID、版本、每symbol的研究/草稿/原因。
  allowed symbols与持仓来自调用上下文，不相信LLM扩展股票范围。未知/重复/非法symbol阻断。
- 同一逻辑请求批次原子upsert；同key同payload复用，不同payload冲突。写失败必须失败。
- 用单文档batch避免standalone Mongo跨文档事务假设。取消/失败run的关联评估只作partial/
  needs_review展示，即使有迟到保存也不能显示成完成或可执行；未结束run不显示成功评估。
- 核心研究缺失/报价缺失/明确数据降级→insufficient_evidence；check不可用→needs_review；
  违规草稿/越范围/不支持short→blocked；其他全部research_only，解释B阶段依赖未完成。
- no degraded markers不等于事实已核验。Gate超时/结构异常不可通过，不返回原始异常细节。
- 无研究shortcut不再调用LLM；失败/缺失的symbol也保留诊断，不从批次悄悄丢失。
- 新评估不进入旧PnL命中率/方向收益统计。历史数字不改写成新方法。
- A阶段approve/mark-executed均拒绝，没有后台开关可以跳过此限制。

## Validation Cases

- [x] Empty BUY仍可legacy读取，但严格新草稿拒绝；伪造ready/approved/actionable不能写入。
- [x] 有完整研究/草稿也只能research_only；缺002/004/005不会提前ready。
- [x] check timeout/invalid output/known violation显示正确非HOLD状态；无错误信息泄露。
- [x] pa缺失与部分研究失败不调用裸LLM shortcut，不漏记缺失symbol。
- [x] 超范围/重复股票、SELL非持仓、非法short/size/非finite数值均明确阻断。
- [x] 所有AI出口只写评估；旧create/upsert/create_many/mark_filled无法绕过。
- [x] 同key并发和重试至多一份批次；不同payload冲突；DB失败无保存成功反馈。
- [x] cancellation/failed/in-progress关联run的读投影不能显示completed/ready。
- [x] legacy原文/来源/时间/PnL仍可读，approve与旧Mark Executed无法变更持仓/现金。
- [x] 独立Add Transaction仍可正常登记真实交易，不能被标AI validated。

### Required Playwright

真实API、Mongo、Redis与内部编排，录制最外层市场/模型传输：

1. 缺研究/quote或check unavailable：可见Analyze→进度→不足/待复核评估；不是HOLD，
   没有批准/执行按钮；reload与API/Mongo一致。`assets/idq-001-a/01-insufficient-evidence.png`。
2. 完整草稿：显示research-only与未接好门禁，APIapprove拒绝，无新order/transaction。
   `assets/idq-001-a/02-research-only.png`。
3. legacy只读＋手工交易：旧BUY仍可展开研究但无执行按钮；Add Transaction独立成功。
   `assets/idq-001-a/03-legacy-readonly.png`。
4. 故障/取消/重试：持久化失败不显示成功；相同key无重复；取消后不产生行动资格。

实际投研试运行必须是小样本、明确预算、研究用途，单独标明live/recorded边界；不能
把模型接口探针当作投资质量验证，也不能为了验收伪造ready。未获得真实数据则记录降级。

## Implementation / Evidence

- Backend: 2100 passed / 27 live integrations deselected, coverage rounds to 72%;
  mypy 299 files, Black/Ruff/Bandit and all critical floors pass. New floors:
  contract 90%, builder 85%, repository 85% (actual 98.18% / 90.36% / 100%).
- Frontend: 266 tests / 27 files; production lint 0 warnings, test/E2E 131 maximum;
  type-check and production build pass. Final image-only acceptance: six decision-safety,
  four Copilot, six hardening and eleven default browser scenarios pass.
- Browser fixture uses real graph/tools, Copilot structured transport adapter,
  DataManager/cache, API and Mongo; provider data is synthetic/recorded. Storage
  failures are fault-injected. This is not live-market or investment-effectiveness evidence.
- No new live paid model requests or strategy benchmark were performed for this task.
  The live instance at localhost:3013 was recreated onto the final images: private
  credentials, default Astra and the entire role map/revision 1 were preserved.
- Two no-cache builds have identical complete installed dependency manifests and
  frontend build assets; UID 1000, no local env/credential files in images. Final
  acceptance backend mounts test fixtures only; frontend mounts nothing.
- [Local validation](assets/idq-001-a/local-validation.json),
  [clean builds](assets/idq-001-a/clean-build-validation.json), and
  [case study](../case-studies/2026-09-16-completed-run-is-not-approved-decision.md).
  Curated screenshots: [missing evidence](assets/idq-001-a/01-insufficient-evidence.png),
  [research only](assets/idq-001-a/02-research-only.png),
  [legacy + manual transaction](assets/idq-001-a/03-legacy-readonly.png).
- Implementation `75e2431779b631b74077b033544197296152c9c2`, protected
  [PR #8](https://github.com/fhw12345/FinancialAgent/pull/8), merge
  `5ce5d8a14bfbefe74e1d71968409d1502d02397d`.
- [Hosted CI](https://github.com/fhw12345/FinancialAgent/actions/runs/35087643908)
  passed all gates, including all three browser lanes. Downloaded artifact retains
  three HTML reports with verified hashes and no credential files; see
  [hosted receipts](assets/idq-001-a/hosted-validation.json). No admin bypass.

## Completion and Rollback

- [x] 先失败回归，再目标测试；全backend/frontend/types/lint/security/critical coverage通过。
- [x] 真实浏览器、curated截图、clean builds/最终镜像、版本/changelog/案例/索引齐全。
- [x] 实现提交与记录其hash的出货文档，protected CI/merge/push同步完成后才ship A。
- [x] 父IDQ-001/总计划仍in-progress；B所需DP-02/03/06/07/10等未实现验收不勾选。

回滚只能停用新研究入口/保持只读，不恢复旧AI写入放行。新评估与旧记录分开保存；
原始持仓/现金不批量修改，不把B阶段风险阈值凭空补入用户设置。
