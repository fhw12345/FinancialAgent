# Documentation Improvement PRD

**Created:** 2026-05-16
**Status:** Awaiting approval
**Owner:** Main orchestrator

> This PRD will be deleted after Implement + Review phases complete. It exists
> so the Review agent has a concrete artifact to score against.

---

## 0. `docs/superpowers/` 判断

实际读过前 30 行后确认：3 个文件**不是** Claude agent 内部任务记录，而是**真实的产品 / 架构设计文档**，只是用 superpowers:writing-plans skill 起草所以放在 `superpowers/` 子目录下。

| 文件 | 实际是什么 |
|---|---|
| `plans/2026-05-05-write-time-translation.md` (47 KB) | PRD：把 LLM 翻译从前端 lazy 改到写入 MongoDB 时持久化（`<field>_zh` 字段） |
| `plans/2026-05-06-prepost-market-support.md` (20 KB) | PRD：盘前盘后行情端到端支持（`QuoteData.session` → DB → API → 前端 chip） |
| `specs/2026-05-05-write-time-translation-design.md` (11 KB) | write-time-translation 的 design 文档 |

**推荐处置：**

1. 迁移 + 转化：
   - `specs/...-design.md` → `docs/features/write-time-translation.md`（加 frontmatter）
   - `plans/...-write-time-translation.md` 中"为什么 / 设计选择"段合入上面；checklist 丢弃
   - `plans/...-prepost-market-support.md` 与 `docs/features/extended-hours-trading-data.md` diff/合并
2. 删除空 `docs/superpowers/` 目录
3. 修所有指向 `docs/superpowers/*` 的内部链接

**遗留风险**：plans 描述的特性可能还没实现，迁移前 Implement 必须先 grep 代码验证。

---

## 1. Problem Statement

仓库当前有 51 个 `.md` / 12,165 行，跨 10 个目录。审计后发现三类系统性问题，使其与"公开发布质量"存在明显差距：

**（1）信任度问题**：CHANGELOG 引用已删除的代码（`api/auth.py`、Aliyun OSS、Langfuse `@observe`），多个文档存在死链（`coding-standards.md:74` 指向不存在的 `../project/versions/backend/v0.5.3.md`；`CONTRIBUTING.md:194` 指向不存在的 `VERSION_MATRIX.md`；`docs/features/README.md` 列举的 `langfuse-observability.md` 与 `llm-model-selection.md` 在目录里已不存在）。外人读到会怀疑整份文档的可信度。

**（2）一致性问题**：9 个 feature 文档至少使用了 4 种不同的状态语法（`✅ Implemented (v0.5.10)` / `> **Status**: Completed (2025-12-14)` / `**Status**: Planning` / `**Status**: Deployed (Phase 2 Complete)` / `> **Status**: Draft`）；日期格式不统一；frontmatter 是行内表格 vs 引用块 vs YAML 混用。

**（3）可读性问题**：`docs/interview/` 10 篇案例研究全部用中文且默认读者懂上下文，外人看不懂。`docs/superpowers/` 名字本身对外人无意义。13 个 SKILL.md 散落在 `backend/src/agent/skills/*/` 下没有总览。缺少架构总图、API 参考、FAQ。

差距：在不动代码的前提下，把仓库的文档提升到"任何中级开发者 30 分钟内能 onboard"的程度。

---

## 2. Goals

**主要目标：**

- **G1**: 全部 51 个 md 在状态标记、frontmatter、日期格式、链接、术语上保持一致
- **G2**: 移除所有引用已删特性（Langfuse、auth、Aliyun OSS 等）的过期内容，或为历史条目加 `[deprecated]` 注释
- **G3**: 修复全部内部死链
- **G4**: `CLAUDE.md` 增加精简 "Documentation Rules" 章节（≤ 20 行），同时新建 `docs/development/documentation.md` 存放完整规则
- **G5**: `docs/interview/` → `docs/case-studies/`，每篇首段补 ≥ 3 句对外读者的 context
- **G6**: 处置 `docs/superpowers/`，迁移有价值内容到 `docs/features/`
- **G7**: 补 4 类缺口：架构总览（含 Mermaid 图）、skills 总览、API 参考、FAQ

**非目标（避免范围爬升）：**

- **N1**: 不改任何代码或测试文件
- **N2**: 不翻译现有英文文档到中文，也不反向翻译——除 case-studies 首段需要双语对外可读外
- **N3**: 不重写历史 CHANGELOG 条目（只加注释）
- **N4**: 不生成自动化文档（Sphinx / TypeDoc / OpenAPI 自动渲染）
- **N5**: 不改 13 个 `SKILL.md` 本体（仅可能改格式注释，不改语义）
- **N6**: 不升级文档站工具链（无 mkdocs / docusaurus 引入）

---

## 3. Acceptance Criteria

可由 Review agent 或 grep / 人工 sampling 验证的 12 条标准：

1. **AC-1 — CLAUDE.md 章节**：`D:\repo\FinancialAgent\CLAUDE.md` 包含 `## Documentation Rules` 一节，行数 ≤ 20，且包含到 `docs/development/documentation.md` 的链接
2. **AC-2 — 详细规则文档**：`docs/development/documentation.md` 存在，定义 frontmatter schema、状态枚举、日期格式、新 feature 流程
3. **AC-3 — 统一 frontmatter**：`docs/features/*.md`（不含 `README.md`）100% 使用 YAML frontmatter，字段固定为 `status / version / last_updated / owner / related_paths`
4. **AC-4 — 状态枚举受限**：feature 文档 status 字段仅能取 {`draft`, `planning`, `in-progress`, `shipped`, `superseded`} 五个值之一
5. **AC-5 — 死链清零**：仓根 markdown link check 报告 0 内部死链，包括 `coding-standards.md:74`、`CONTRIBUTING.md` 的 `VERSION_MATRIX.md`、`docs/features/README.md` 列出但不存在的 langfuse / llm-model-selection
6. **AC-6 — Langfuse / Auth 引用清除**：`grep -ri "langfuse\|@observe\|api/auth" docs/ CLAUDE.md CONTRIBUTING.md README.md` 在非 CHANGELOG / 非 case-studies 文件中返回 0 行；CHANGELOG 中保留的历史条目须紧跟 `> _(removed in v0.x.y)_` 注释
7. **AC-7 — case-studies 重命名 + 上下文**：`docs/interview/` 已不存在；`docs/case-studies/` 存在；目录下每个 `*.md`（含 README）首段 ≥ 3 句完整介绍上下文 + 一句"为什么外部读者会关心这个 case"
8. **AC-8 — superpowers 清空**：`docs/superpowers/` 已不存在；内容已根据 §0 迁移
9. **AC-9 — 四件缺口补齐**：
   - `docs/architecture/overview.md`（≥ 1 个 Mermaid 数据流图 + 1 个 agent graph 图）
   - `docs/architecture/api-reference.md`（覆盖 `backend/src/api/` 全部主路由）
   - `docs/FAQ.md`（≥ 10 条 Q&A）
   - `backend/src/agent/skills/README.md`（13 个 skill 能力矩阵表）
10. **AC-10 — docs/README.md 同步**：根索引反映重命名、移除 superpowers、新增 overview / api-reference / FAQ，无死链
11. **AC-11 — features/README.md 修复**：与目录实际文件 1:1 对应；不再提及 langfuse-observability.md 与 llm-model-selection.md
12. **AC-12 — 代码零改动**：`git diff --stat` 仅包含 `*.md` 和必要的 README；`backend/src/agent/skills/*/SKILL.md` 字节级不变

---

## 4. Implementation Plan

### Group A — 根目录

**A.1 `README.md`**
- 通读，确认 tech stack / quickstart / 端口与当前 `docker-compose.yml` 一致
- 顶部 admonition 明确 "personal local fork, no public deployment"
- 加链接段：→ `docs/architecture/overview.md`、`docs/development/getting-started.md`、`docs/FAQ.md`、`CONTRIBUTING.md`

**A.2 `CLAUDE.md`** — 加 1 节 Documentation Rules（≤ 20 行）：

```
## Documentation Rules
- 所有 docs/features/*.md 必须使用统一 YAML frontmatter（status/version/last_updated/owner/related_paths）
- status 字段枚举：draft | planning | in-progress | shipped | superseded
- 日期一律 ISO 格式 YYYY-MM-DD
- 内部链接全部相对路径；新增 doc 时必须更新 docs/README.md
- 添加 / 修改 feature 时同步 features/<name>.md
- 详见 docs/development/documentation.md
```

**A.3 `CONTRIBUTING.md`**
- 删除/修复 line 194 的 `VERSION_MATRIX.md` 引用 → 改为 `docs/project/versions/README.md`
- "Documentation" 章节加：每次改 feature 必须更新对应 `docs/features/<name>.md` 的 `last_updated` 与 `version`

### Group B — `docs/development/`

**B.1 `coding-standards.md`**
- 修 line 74 死链
- 全文搜其它绝对路径风格的链接，统一为相对路径

**B.2 `error-handling.md`**
- 删除 line 191 `@observe` 装饰器示例及其上下文段落
- 若该段是讲"如何加 trace"，改写为 structlog `bind()` 示例
- 全文 grep `langfuse` 与 `@observe`，全部移除

**B.3 `getting-started.md`**
- 第二节"frontend dev"高亮 `docker compose exec frontend npm <cmd>`
- 加一节"How to verify your install"含 `curl http://localhost:8000/api/health` + 预期 200 输出

**B.4 新增 `documentation.md`** — 完整规则文档：
- frontmatter schema（YAML 块 + 字段说明 + 示例）
- 状态枚举语义
- 何时新建 feature doc / 何时改既有 doc / 何时归档
- case-studies 写作模板（context → investigation → root cause → fix → lesson）
- 链接风格（相对路径）
- 代码块语言标注规范

### Group C — `docs/features/`（9 个 + README）

**C.0 — frontmatter schema：**

```yaml
---
title: Market Insights Trend Visualization
status: shipped              # draft | planning | in-progress | shipped | superseded
version: backend@0.9.0, frontend@0.11.4
last_updated: 2025-12-30
owner: maintainer
related_paths:
  - backend/src/api/market_insights/
  - frontend/src/components/MarketInsights/
---
```

**C.1 — 9 个文件逐个处置：**

| 文件 | 当前状态 | 动作 |
|---|---|---|
| `market-insights-trend-visualization.md` | Deployed | → `status: shipped` |
| `chat-symbol-context.md` | ✅ Implemented v0.8.1+ | → `status: shipped`；删 "(planned)" |
| `symbol-search-and-chart-improvements.md` | Planning | Implement 必须 diff Phase 2 与代码 |
| `fibonacci-trend-detection-improvements.md` | ✅ Implemented v0.5.10 | → `status: shipped` |
| `extended-hours-trading-data.md` | Draft (2025-10-30) | 关键：与 prepost-market-support 合并 |
| `portfolio-agent-architecture-refactor.md` | 无明显 status | Implement 验证架构落地后给 status |
| `langgraph-sdk-react-agent.md` | ✅ DEPLOYED v0.7.0+ | → `status: shipped` |
| `backend-api-module-restructure.md` | Completed 2025-12-14 | → `status: shipped` |
| `README.md` | 含 Langfuse / LLM model selection 失效引用 | 删失效条目；列表与目录 1:1 同步 |

### Group D — `docs/interview/` → `docs/case-studies/`

**D.1** `git mv docs/interview docs/case-studies`

**D.2** 改写 README 给外部读者，例如：
> "Real-world debugging case studies from this project. Each entry follows context → investigation → root cause → fix → lesson, with a focus on *thinking process* rather than just the final fix..."

**D.3** 每个 case study 加首段 ≥ 3 句外部 context：
- 一句话总结这个 bug / 决策是什么
- 它的产品/用户影响
- 外部读者从中能学到的 takeaway

**D.4 — 语言策略（待用户确认 §9 Q2）**：推荐"仅加双语 TL;DR 首段，正文中文不动"

### Group E — `docs/superpowers/`

详见 §0。

### Group F — `docs/archive/`

- 保持现状
- 给两个文件首段加注释：`> Archived — kept for historical context. The architecture described here was superseded by docs/features/portfolio-agent-architecture-refactor.md.`

### Group G — `docs/project/versions/`

- README 顶部加："This directory tracks per-component changelog. Components are versioned independently (Semantic Versioning 2.0)."
- CHANGELOG 历史条目：给 5-10 个引用已删特性的条目末尾加 `_(feature removed in v0.x.y when forking to personal local-only setup)_`

### Group H — 缺口补充

**H.1 `docs/architecture/overview.md`**
- system in one paragraph
- Mermaid 数据流图：User → Frontend → Backend → {MongoDB, Redis, External APIs}
- Mermaid agent graph 图：LangGraph ReAct + 4 个 skill family + Phase 1/2/3 portfolio agent
- 链接到 4 份既有 `docs/architecture/*.md`

**H.2 `docs/architecture/api-reference.md`**
- Implement 阶段先 grep `backend/src/api/` 下所有 `@router.get/post/put/delete`
- 按模块分组：portfolio / chat / analysis / symbol_search / market_insights / health / translate
- 每个 endpoint 1 行表格：method / path / 简述 / request / response 关键字段
- 末尾标注 Source of truth: `curl http://localhost:8000/openapi.json`

**H.3 `docs/FAQ.md`** — ≥ 10 条 Q&A，覆盖：
- docker compose vs venv？
- .env 不生效？
- 端口占用？
- yfinance 429 / 慢？
- 中文翻译有时缺失？
- Phase 1/2/3 portfolio agent？
- 为什么 backend/frontend 版本独立？
- 如何加新 skill？
- 如何加新数据源？
- 测试为什么必须容器里跑？

**H.4 `backend/src/agent/skills/README.md`** — 13 skill 能力矩阵表

### Group I — `backend/tests/REACT_SDK_FINDINGS.md`

移动到 `docs/archive/`，首段加：`> Research notes that led to the LangGraph SDK adoption shipped in v0.7.0. See docs/features/langgraph-sdk-react-agent.md for the production design.`

### Group J — `backend/src/agent/skills/*/SKILL.md`

**不动 SKILL.md 本体**（agent 运行时可能读取，风险大）。仅在抽样发现明显错误时单点修复。

### Group K — `docs/README.md`

索引更新：
- `Interview Case Studies` → `Case Studies` 指向 `case-studies/README.md`
- 加 `Architecture Overview` → `architecture/overview.md`
- 加 `API Reference` → `architecture/api-reference.md`
- 加 `FAQ` → `FAQ.md`
- 加 `Agent Skills` → `../backend/src/agent/skills/README.md`
- 删除所有 `superpowers/` 引用
- features 列表与 `docs/features/README.md` 同步

---

## 5. Files to Modify / Create / Delete

### Create (7 files + 1 rename)

| Path | Purpose |
|---|---|
| `docs/development/documentation.md` | 完整文档规则 |
| `docs/architecture/overview.md` | 架构总览 + Mermaid 图 |
| `docs/architecture/api-reference.md` | API endpoint 参考 |
| `docs/FAQ.md` | 常见问题 |
| `backend/src/agent/skills/README.md` | 13 skill 能力矩阵 |
| `docs/features/write-time-translation.md` | 来自 superpowers 迁移 |
| `docs/case-studies/` | 重命名自 `docs/interview/` |

### Modify

| Path | Change |
|---|---|
| `CLAUDE.md` | 加 Documentation Rules 章节 |
| `README.md` | 加导航链接 |
| `CONTRIBUTING.md` | 修死链 + 加 docs 同步要求 |
| `docs/README.md` | 索引重建 |
| `docs/development/coding-standards.md` | 修 line 74 死链 |
| `docs/development/error-handling.md` | 删 @observe / Langfuse |
| `docs/development/getting-started.md` | 强调 docker compose exec |
| `docs/features/README.md` | 修死链 + 实际文件列表 |
| `docs/features/*.md` (9 个) | 统一 YAML frontmatter |
| `docs/case-studies/*.md` (10 个) | 加首段外部 context |
| `docs/archive/*.md` (2 个) | 首段加 archived note |
| `docs/project/versions/README.md` | 加顶部说明 |
| `docs/project/versions/{backend,frontend}/CHANGELOG.md` | 历史条目加 removed note |

### Delete / Move

| From | To |
|---|---|
| `docs/superpowers/` (3 文件) | 内容迁移到 `docs/features/`，目录删 |
| `docs/interview/` | rename 到 `docs/case-studies/` |
| `backend/tests/REACT_SDK_FINDINGS.md` | move to `docs/archive/` |

---

## 6. Risks

| # | Risk | 严重度 | 缓解 |
|---|---|---|---|
| R1 | 重写 case-studies 开头丢失原作者个人语气 | 中 | 仅加"首段双语 TL;DR"，保留原段落不动 |
| R2 | 改 `SKILL.md` 影响 agent 运行时 | 高 | 本 PRD 明确不动 SKILL.md 本体（Group J），仅新建总览 README |
| R3 | CLAUDE.md 节与现有 agent team orchestrator 冲突 | 中 | 目标是项目 CLAUDE.md（不是 ~/.claude/CLAUDE.md）；插在 "Development Principles" 之后，不删既有内容 |
| R4 | features/ 合并 superpowers 时把没实现的标 shipped → 文档撒谎 | 高 | Implement 必须 grep 验证代码路径再决定 status |
| R5 | Mermaid 图本地 viewer 可能差 | 低 | GitHub renderer 为准 |
| R6 | 重命名 interview/ 后所有外部 backlink 会断 | 中 | rename 后 grep `docs/interview` 全仓修 |
| R7 | API reference 手写易与代码漂移 | 中 | 末尾标注 OpenAPI JSON 为真理来源 |
| R8 | 12,165 行 md 全量 review 工作量大 | 低 | AC 减少主观争议；机器验证为主 |

---

## 7. Validation Plan

1. **死链检查**：grep 验证 `coding-standards.md:74`、`CONTRIBUTING.md` 的 VERSION_MATRIX、`docs/features/README.md` 的失效引用、`docs/README.md` 是否还引用 `docs/interview/` 或 `docs/superpowers/`
2. **Langfuse / Auth 清理验证**：`grep -rEn 'langfuse|@observe|api/auth' docs/ CLAUDE.md CONTRIBUTING.md README.md` 仅 CHANGELOG 可命中，且必须紧跟 "removed in v…"
3. **frontmatter 一致性**：
   ```bash
   for f in docs/features/*.md; do
     [[ "$f" == *README.md ]] && continue
     head -1 "$f" | grep -q '^---$' || echo "MISSING FRONTMATTER: $f"
   done
   ```
4. **status enum 限定**：
   ```bash
   grep -h '^status:' docs/features/*.md \
     | grep -vE 'status: (draft|planning|in-progress|shipped|superseded)' \
     && echo "INVALID STATUS FOUND"
   ```
5. **case-studies 首段长度抽样**：随机 3 篇，确认首段 ≥ 3 句
6. **代码零改动验证**：`git diff --stat | grep -v '\.md$'` 应只剩新建的目录占位
7. **跑测试确保没动到代码**：`make test`（预期与本任务前一致）

---

## 8. Build Sequence

1. **Step 1 — 标准先行**：建 `docs/development/documentation.md`
2. **Step 2 — 项目根更新**：改 `CLAUDE.md`、`CONTRIBUTING.md`、`README.md`
3. **Step 3 — 现有文档修复**：
   - 3a. `docs/development/` 三份修死链 / 删 Langfuse / 强调 docker exec
   - 3b. `docs/features/` 9 份套 YAML frontmatter
   - 3c. `docs/features/README.md` 删失效条目
4. **Step 4 — superpowers 处置**：先验证代码落地状态 → 内容迁移 → 删目录
5. **Step 5 — case-studies 重命名 + 上下文**：`git mv` → 改 README → 10 篇加首段 → grep 修 backlink
6. **Step 6 — 缺口补充**：overview.md → api-reference.md → FAQ.md → skills/README.md
7. **Step 7 — CHANGELOG 注释**
8. **Step 8 — REACT_SDK_FINDINGS 迁移**
9. **Step 9 — `docs/README.md` 索引重建**（必须最后）
10. **Step 10 — Validation pass**：跑 §7 全部脚本

---

## 9. Open Questions（用户在 Implement 启动前必须回答）

**Q1 — superpowers 内容状态**：
`docs/superpowers/specs/2026-05-05-write-time-translation-design.md` 描述的 "write-time translation"（DB 加 `<field>_zh` 字段、`persistence_translator.py`）当前是 **已上线 / 进行中 / 未开始**？同样问 `2026-05-06-prepost-market-support.md` 的 `QuoteData.session` 字段与前端 chip？

**Q2 — case-studies 语言策略**：
- (a) **仅加双语 TL;DR 首段，正文中文不动**（推荐）
- (b) 全文翻译成英文
- (c) 中英对照

**Q3 — CHANGELOG 历史条目处置**：
- (a) **仅加 `> _(removed in v0.x.y when forking to personal local)_` 注释**（推荐）
- (b) 整段删除涉及已删特性的条目
- (c) 顶部加 "Fork Notes" 章节集中说明

---

**预估工作量**：~10-15 小时纯文档工作量
