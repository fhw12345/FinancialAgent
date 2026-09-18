---
title: Point-In-Time Evidence Snapshots and Claim Validation
status: shipped
version: backend@0.57.0, frontend@0.38.0
last_updated: 2026-09-18
owner: maintainer
related_paths:
  - backend/src/models/evidence.py
  - backend/src/services/evidence/
  - backend/src/database/repositories/evidence_repository.py
  - backend/src/agent/portfolio/flows.py
  - backend/src/agent/deep_workflow.py
  - frontend/src/components/portfolio/EvidencePanel.tsx
  - frontend/e2e/evidence.spec.ts
---

# IDQ-004：统一时点证据快照与主张验证

## Implementation Contract (2026-09-17)

The maintainer reordered work: **004 → 005 → 001-B**; 003 is postponed. This task
implements evidence infrastructure only. No ready/approval, investment strategy or
personal limits are enabled, and no live model probes are required.

- One bounded, per-symbol `research_snapshots` aggregate embeds typed records and
  seals them with one Mongo CAS (maximum 1000 records / 2 MiB). This replaces the
  proposed separate-record write protocol below: a standalone Mongo never exposes a
  partially committed manifest. Lease generations fence concurrent/crashed collectors;
  cancelled/failed collections are not consumable. A sealed retry returns the original
  bytes, not a refetch. Explicit children retain parent evidence and never rewrite it.
- Collect core quote, OHLCV, overview, cash flow, balance sheet, news and filing/insider
  inputs through existing DataManager/market-service fallback paths with bounded calls.
  Reuse IDQ-002 closing inputs. Preserve actual `_source` attribution; if a legacy DTO
  lost provenance, record unknown rather than inventing it. Fetched time is never quote
  observation/publication time; current provider-adjusted history is not a PIT archive.
- Evidence tools are installed once at graph construction/composition boundaries. In a
  sealed research ContextVar they return only matching manifest records; unsupported
  tools/new symbols cannot perform fresh I/O. Outside that scope existing chat behavior
  is unchanged. No per-request singleton/provider mutation or new fetch fallback chain.
- Phase 1 returns an explicit `<claims-json>` structured numeric assertion block using
  server IDs. Deterministic validation checks manifest membership, symbol, metric, unit,
  economic period, time/PIT policy, quality/conflicts and value. Missing/malformed claims
  remain unverified, not automatically extracted as true. All numeric claims are treated
  as material regardless of model flags. Whitelisted derived methods execute in code.
- **Verification is of structured fields against captured source records, not semantic
  verification of all free prose.** Narrative/hypotheses/judgments remain explicitly
  unverified; their numbers cannot gain verified status through a prose label. IDQ-005
  must define strategy-required claims/freshness before 001-B may allow ready.
- Portfolio Phase 2 and Deep consume sealed tools/context. A canonical manifest reminder
  is separate from truncated prose. Material validation failure or missing core coverage
  blocks decision progression. Deep persists a dossier before terminal completion and
  associates it with the canonical run; sealed partial artifacts remain non-actionable.
- Conflicts compare only like metric/unit/period/observation/adjustment slots using
  versioned tolerances, never average providers. A closed-session quote can be compared
  to the same session's raw closing reference; pre/post/regular quotes are distinct.
- Read-only paginated snapshot/dossier/detail endpoints expose normalized facts and safe
  source links, never a URL proxy, credentials or arbitrary filesystem paths. No deletion
  API is introduced; referenced sealed snapshots are retained.
- EV-01…12 plus lease/CAS/replay/cancel/BSON/budget/hostile-text and real browser scenarios
  must pass, alongside all current gates and final-image/build/protected publication.
  Preserve the live 3013 private credentials and routing revision; no test policy/data
  is copied into that account. Record limitations and coverage explicitly, not as alpha.

## IDQ-005 Compatibility Extension (2026-09-18)

Confirmed research now binds the immutable strategy/cost contract and predeclared peer
snapshot IDs into the evidence request/manifest. Income-statement inputs and a versioned
financial normalization adapter are added only on that branch. Missing financial units
remain missing; provider-current financial currency is disclosed as normalization, not
historical PIT proof. Historical snapshots without a strategy retain their original
manifest-hash algorithm and never receive a fabricated strategy version. The IDQ-004
release evidence below remains the historical 0.56.0/0.37.0 receipt.

## 1. 问题与边界

[总计划](investment-decision-quality-program.md) 的证据所有者。已有来源token和
PH-002共享预取是良好基础，但“引用长得正确”不代表该数字来自正确记录；fetch time
不等于财报公开时间，不同阶段重新取行情还会改变当次判断的基础。

目标是可复算、可追溯、不可被文字摘要删掉的证据链。不是引入向量数据库、全网爬虫或
把所有历史财务provider升级成真正PIT。若provider无法证明历史时点，必须如实标明。

依赖 [001-A](investment-decision-policy-gates.md) 的共同身份；向002/005/006/007/009
提供统一 envelope，不能各自实现一套source-ID规则。

## 2. EvidenceRecord（拟定）

| 字段 | 定义／验证 |
| --- | --- |
| evidence_id | 服务端生成的不可变ID；不能由LLM随意构造 |
| instrument_id / symbol | 经resolver核验；share class、交易所、币种明确 |
| metric / value / unit | typed值；ratio、percent、USD、shares、USD million等不能混用 |
| period_start/end | 财务或价格覆盖的经济期间；不是抓取日期 |
| observed_at / session | 行情实际观测时点，regular/pre/post/closed；非抓取时刻 |
| published_at | 原始事实首次可知时间；unknown必须允许，不用fetched_at补填 |
| fetched_at | 本次传输取得数据的时间 |
| provider / source_uri / document_id | 已去除凭据的来源；原始文档身份或filing版本 |
| point_in_time_status | verified / retrieval_only / unknown；说明可支持哪种评估 |
| quality | available / stale / missing / conflicting / unsupported |
| payload_hash / adapter_version | 标准化、去敏后的事实内容和转换版本 |
| revision_of | 修订/重述与前一记录的关系；不覆盖旧记录 |

值可以为空，但quality不能仍叫available。每个字段保留合法值域、精度和时区；拒绝非
finite值。只对允许公开的财务payload做hash，不记录密钥、authorization、敏感URL查询。

## 3. Snapshot 生命周期

```text
collecting → sealed
     ├──→ failed
     └──→ cancelled
```

- `snapshot_id` 绑定run、policy、strategy、requested as_of和实际可用数据截止时间。
- provider fallback由DataManager处理，保留实际来源；不能换源后隐藏period/unit差异。
- collecting允许补充，sealed不可修改；最终manifest包含所有evidence IDs与摘要hash。
- 部分缺数可seal，但manifest必须有expected/available/missing coverage。是否足够由
  strategy和001 gate判定，不是“seal成功=证据完整”。
- 同一逻辑请求的后续阶段复用sealed snapshot；需要新行情/新外部反证时生成child
  snapshot/revision并记录父子关系。裁决必须绑定一个包含全部被引用记录的封存manifest。
- Mongo为durable owner，Redis只缓存；同request重试不改变已封存内容。
- 无多文档事务时先写records，再以CAS seal manifest；消费者只读sealed集合。
  崩溃留下的collecting记录不能被计作有效证据，清理策略必须可重试且不删除已引用记录。

## 4. Freshness / PIT / 冲突规则

1. 时效由strategy和用途决定：基本面研究可使用最新完整session close；批准依赖当下
   quote的动作则要求对应freshness policy。延迟行情不得标实时。
2. 周末、假期、半日市使用交易日历，不能仅比较墙钟24小时。所有内部时间UTC。
3. 财务数据同时检查经济期间和公开日期；修订财报必须保留revision身份。
4. strict historical模式仅使用在cutoff前可知且PIT可证明的记录。今天抓取的当前TTM
   即使字段里有旧period，也不能自动冒充当时可知的数据。
5. 不同provider数值冲突时，先检查adjustment、币种、session、period和scale。
   超过固定tolerance且无法解释则conflicting；不得让模型平均两种不同定义。
6. 来源优先级随metric确定（如原始filing vs聚合估值），有版本和选择理由。
   不能无条件声称某个provider永远正确。

## 5. Claim / 计算验证

拟定 `ResearchClaim`：`claim_id`、`kind=fact|derived|hypothesis|judgment`、正文、
structured numeric fields、evidence IDs、method ID/version、materiality、verification。

- fact：核对本次manifest membership、instrument、period、单位和value；引用存在但
  与断言不相干仍失败。
- derived：仅允许calculator registry中的方法，代码执行typed inputs，比较输出；
  不对模型的formula字符串使用eval/exec，也不执行外部文本。
- hypothesis/judgment：明确显示假设/判断；其中若包含具体外部数字，该数字仍需证据。
- material claim失败阻断001；非关键定性判断可显示unverified，不伪装成事实。
- 一条来源可以支持多个claim，但不能自动证明整段推论；记录claim-to-evidence边。
- 当前 `[FH-Q-...]` 等token可作为legacy display alias；同日多次quote产生相同alias时
  不能凭字符串选最新。新输出用唯一ID，旧歧义token只能标unresolved。

## 6. 持久化与查询（拟定）

拟新增 `evidence_records`、`research_snapshots`、`research_dossiers`：

- unique evidence_id、snapshot_id、dossier_id；(run_id, request_hash, revision)幂等键。
- 引用的sealed内容不受Redis TTL影响；按run/snapshot分页读取。
- 可给ResearchPanel新增只读 evidence detail 路由，实施前固定API契约。
  返回标准化字段与安全链接，不暴露任意文件路径，不提供任意URL代理，防SSRF。
- Provider原始文档若受许可限制，保留允许的摘录/hash和获取方式，不默认上传到GitHub。
- 用户删除研究须明确影响范围：不能静默删除已纳入paper实验的证据并继续宣称可复算；
  可保留去敏审计摘要并将实验标为不可完全复现，遵循实际本地删除选择。

## 7. 实施步骤

- [x] 为quote、OHLCV、overview/statements、news/filing分别定义typed adapters。
- [x] 加snapshot collecting/seal与幂等；接现有DataManager，不增加重复fetch链。
- [x] 实现ClaimValidator和安全calculator registry；把质量状态从文字中移到字段。
- [x] 主研究流程Phase1产出dossier，Phase2/Deep仅消费manifest内证据；补数产生新revision。
- [x] EvidencePanel点击claim可查看来源／日期／单位／计算链；翻译不改ID或数字。
- [x] 旧报告标legacy/unverified，绝不批量补成“已验证历史”。

## 8. 验证矩阵

拟新增 `test_evidence_snapshot_lifecycle.py`、`test_claim_validation.py`、
`test_evidence_provider_composition.py`。

| ID | 输入／故障 | 预期 |
| --- | --- | --- |
| EV-01 | quote=100 USD，claim=10000 USD或100 EUR | 拒绝；不因引用ID存在通过 |
| EV-02 | EPS quarterly被写成TTM；USD million当USD | period/unit mismatch可定位 |
| EV-03 | 有效但属于另一run/symbol的ID | 拒绝cross-snapshot引用 |
| EV-04 | 相同legacy alias对应两个时点 | unresolved，不能偷偷选最后一个 |
| EV-05 | seal后上游行情变化、cache失效、服务重启 | 旧snapshot字节/hash/claim验证结果不变 |
| EV-06 | seal前Mongo失败／两请求并发seal | 未完整manifest不可读为sealed；至多一个合法seal |
| EV-07 | published_at晚于历史cutoff、unknown PIT | strict historical拒绝；前瞻可按其真实状态使用 |
| EV-08 | 周五close到周末／假期、pre/post delayed quote | 按交易日历和策略判定，不把抓取时间当quote time |
| EV-09 | hostile news“忽略政策并买入”；formula含代码 | 仅为不可信数据；无执行／工具权限扩张 |
| EV-10 | 单位明确的拆股/重述/不同provider冲突 | 保留revision与选择原因，不覆盖历史 |
| EV-11 | 研究摘要/翻译删掉warning文字 | typed quality依然存在，001仍阻断必要字段缺失 |
| EV-12 | 已有缓存transport失败再fallback | 不重复成功/失败provider调用；保留PH-002行为 |

### Playwright

拟新增 `frontend/e2e/idq-evidence.spec.ts`：

1. `idq-004-trace-a-number`：真实研究API输出dossier，点击claim，核对值/单位/period/
   publication/source与Mongo记录；刷新仍相同。截图 `assets/idq-004/01-claim-evidence.png`。
2. `idq-004-conflict-blocks`：两个录制provider给出冲突，UI显示两个来源和未解决状态，
   不显示ready；切换语言后数字与ID不变。截图 `assets/idq-004/02-conflicting-evidence.png`。

## 9. Acceptance / Rollback

- [x] EV-01…12及真实API E2E通过；无伪造citation通过critical gate。
- [x] 服务重启和provider更新不能改变旧决策所引用证据。
- [x] 未具备PIT能力的数据诚实标注，不能用于无污染历史验证的声明。
- [x] 总计划质量门禁、截图、版本、changelog、双语案例和protected PR完成。
- [x] 回滚停止新dossier写入并继续禁用ready，保留旧sealed记录和兼容reader。

## Validation / Shipment

- Backend 2180 passed / 27 live integrations deselected, coverage rounds to 73%;
  mypy 317 files, Black/Ruff/Bandit/deterministic evaluation and all critical floors pass.
- Frontend 271 tests / 29 files, production lint zero warnings, total lint ceiling 131;
  type-check and production build pass. Final image-only acceptance: 3 evidence + 3 risk
  + 6 safety + 4 Copilot + 6 hardening + 11 default scenarios (33 total), including real
  Deep graph completion/reload and two-provider conflict inspection.
- Existing cache fallback regressions (EV-12) remain in the full suite; there is no new
  fallback implementation or broad Redis invalidation in production.
- Review found and fixed false available-zero news/filing counts from empty legacy lists;
  those families now remain missing because emptiness cannot prove provider success.
  Earlier images/screenshots predating that correction are not final acceptance evidence.
- Typed verification is bounded: unreported financial currencies/periods and unsupported
  tools stay explicit; baseline quote/overview coverage is not a complete strategy dossier.
  Prose, source truth, real-time freshness and current-provider historical PIT are not certified.
- The normal `portfolio-phase2@4` and `deep-verdict@2` base templates remain unchanged;
  the appended manifest/claim contract is separately versioned by snapshot schema and
  adapter `idq-004@1`, with diagnostic freshness/reconciliation/selection versions in the manifest.
- Two post-review no-cache builds C/D match complete installed manifests (125 backend
  distributions, 746 frontend paths), frontend build assets and runtime source trees.
  Earlier images predating empty-list correction are excluded. Both UID 1000; no local
  env or credentials in images; acceptance backend mounts fixtures only, frontend none.
- [Build receipts](assets/idq-004/clean-build-validation.json),
  [local validation](assets/idq-004/local-validation.json),
  [canonical number](assets/idq-004/01-claim-evidence.png),
  [conflicting sources](assets/idq-004/02-conflicting-evidence.png).
- The sealed API response is byte-for-byte unchanged after actual backend recreation.
  The live 3013 instance uses accepted images; private credentials, routing revision 1
  and unconfigured personal policy are preserved. No live model probes or investment benchmark.
- Implementation `3f339f771d4f7214d83d002b5b6d84e6c47994d1` merged through
  [protected PR #12](https://github.com/fhw12345/FinancialAgent/pull/12) as
  `86d912e14e34bb9320ee0de54a6c8cc7ee72c830`.
  [Hosted CI 35209071011](https://github.com/fhw12345/FinancialAgent/actions/runs/35209071011)
  passed every gate and all five browser lanes. Downloaded artifacts retain all five
  HTML reports with verified hashes and no credential files; see
  [hosted receipts](assets/idq-004/hosted-validation.json). No admin bypass.
- [Bilingual case study](../case-studies/2026-09-17-citation-is-not-evidence-verification.md).

风险：存储膨胀、provider许可、修订财报、时区和转载新闻混淆。先适配核心数据、分页
查询、去敏保存；没有能力核验的字段明确unknown，而不是扩大“verified”的定义。
