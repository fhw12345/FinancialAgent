# 写入时翻译（Write-Time Translation）设计文档

- **Date**: 2026-05-05
- **Status**: Approved (pending implementation plan)
- **Owner**: main agent
- **Related commits**: `14ea280` (i18n force-translate disclaimers), `146e518` (POST /api/translate + lazy hook)

## 1. Problem Statement

LLM 生成的英文用户可见文本（chat content、trading reasoning、portfolio
assessment、chat title 等）目前**只以英文存进 MongoDB**。前端在 zh-CN 语言下打开
内容时才通过 `useTranslated` hook 调 `POST /api/translate`，结果只缓存在 Redis
里 1 天 TTL。

这导致：

- 首次打开有 ~3s LLM 延迟，后续刷新仍有 ~87ms 网络往返
- Redis TTL 过期 → 同样的文本要再翻一次
- DB 里没有中文版本 — 无法直接查询/导出/备份带翻译的数据
- system prompt 改动需要手动清 Redis 缓存
- 渲染时 component 各自调 `useTranslated`，产生多个 loading 闪烁

## 2. Goals

- 所有用户可见的 LLM 生成文本在**写入 MongoDB 之前**就完成 zh-CN 翻译，并存
  在同一文档的 `<field>_zh` 字段里
- 前端读到 `_zh` 直接渲染，正常路径下不再调 `/api/translate`（`_zh` 缺失时
  仍回退到 lazy 路径，详见 §5.6）
- 历史 MongoDB 数据全量回填 zh-CN 译文
- 翻译失败不阻塞英文写入；前端在 `_zh` 缺失时退回到现有 lazy 路径
- 复用现有 `translation_service.translate_batch()`、Redis 缓存、Anthropic
  system prompt — 不动翻译核心逻辑

## 3. Non-Goals

- 不引入 worker / 消息队列（同步内联即可）
- 不改 schema 成 dict-style 多语言 map（加 `_zh` 后缀字段更轻）
- 不删现有 `/api/translate` 端点和 `useTranslated` lazy 逻辑 —
  作为 safety net 保留
- 不改 system prompt 和 Redis 缓存策略
- 不支持 zh-CN 之外的其他目标语言（schema 加字段即可扩展，但本期只做 zh-CN）

## 4. Acceptance Criteria

- 新建一个 chat 消息后，**直接从 MongoDB 读** `messages` collection 能看到
  `content_zh` 非空且为合理中文译文
- 同样验证 `trading_decisions.reasoning_summary_zh`、
  `portfolio_decisions.portfolio_assessment_zh`、`chats.title_zh`
- 前端在 zh-CN 语言下打开历史 chat（已回填）和新 chat 都**不再触发**
  `/api/translate` 网络请求（DevTools 验证）
- 翻译失败的单元测试：模拟 LLM 抛错 → 英文字段照常存入，`_zh` 字段为
  `null`，前端 fallback 到 lazy 路径正常工作
- `make backfill-translations` 跑完后，`_zh` 缺失的旧文档数为 0
- 现有的 `/api/translate` 端点、Redis 缓存、`useTranslated` lazy 行为
  在 `_zh` 缺失时仍然正常工作（回归不破坏）
- `make test` 全绿；新增至少 5 个 backend 测试 + 1 个 frontend 测试

## 5. Architecture

### 5.1 层次

```
LLM/Agent 流程
      │
      ▼ (generates English)
Repository.create/save()
      │
      ├─► persistence_translator.translate_for_persistence({fields...})
      │           │
      │           ├─► translation_service.translate_batch([texts], "zh-CN")
      │           │           ├─► Redis cache lookup
      │           │           ├─► Anthropic batch call (cache miss)
      │           │           └─► Redis cache write
      │           │
      │           └─► returns {field_zh: zh_text or None}
      │
      ▼ (English + Chinese)
MongoDB insert_one / update_one
```

### 5.2 翻译边界 — `persistence_translator.py`

**新文件**: `backend/src/services/persistence_translator.py`

```python
async def translate_for_persistence(
    fields: dict[str, str],
    target_lang: str = "zh-CN",
) -> dict[str, str | None]:
    """
    输入: {"content": "...", "title": "..."}
    输出: {"content_zh": "...", "title_zh": "..."}  或失败时 _zh 值为 None

    - 空白/空字符串字段短路返回 None，不调 LLM
    - 一次性 batch 所有非空字段，复用 translation_service
    - LLM 失败/超时 → 全部返回 None，记 WARN 日志，不抛
    """
```

每个 repository 写入路径调**一次**（不是每个字段一次），保证只有一次 LLM
往返。

### 5.3 数据模型变更

> **修订（2026-05-05，写计划阶段发现）：** 实现探索表明 `TradingDecision.reasoning_summary` 和 `PortfolioDecisionList.portfolio_assessment` **没有独立持久化** —— `phase2_decisions.py:223-260` 把它们拼成 markdown 后写成一条 `messages` 文档。因此本期收敛到 **2 张 collection、3 个字段**：

| Collection | 新增字段 | 类型 | 说明 |
|---|---|---|---|
| `messages` | `content_zh` | `Optional[str]` | `Message.content` 译文（覆盖 chat + Phase 1 研究 + Phase 2 portfolio 决策报告 + disclaimers） |
| `chats` | `title_zh` | `Optional[str]` | `Chat.title` 译文（侧边栏会话名） |
| `chats` | `last_message_preview_zh` | `Optional[str]` | `Chat.last_message_preview` 译文（侧边栏预览片段） |

Pydantic 模型加 `Optional[str] = None`，向后兼容。`None` / 缺失 / `""` 都被
前端识别为"翻译未就绪 → 走 lazy"。

### 5.4 写入路径改造点

> 修订后只剩 2 处实际写入边界（Phase 2 已被吸收进 `MessageRepository.create()`）：

| 位置 | 当前行为 | 改造 |
|---|---|---|
| `backend/src/database/repositories/message_repository.py:create()` (line 45) | `insert_one` 英文 doc | 调 `translate_for_persistence({"content": ...})`，把 `content_zh` 加进 doc 后再 insert。覆盖 chat + Phase 1 研究 + Phase 2 portfolio 报告 |
| `backend/src/database/repositories/chat_repository.py:create()` (line 40) 及 `update()` (line 89) | 写 `title` / `last_message_preview` | 同上，字段 `title` 和 `last_message_preview`（仅当 update 字典里出现这俩 key 时翻译） |

每处改造**只加 ~3 行**：调 translator → merge `_zh` 进 doc dict → insert。

### 5.5 前端改造

**`frontend/src/hooks/useTranslated.ts`** — 扩展签名：

```typescript
useTranslated(text: string, opts?: { precomputed?: string | null })
```

行为：
- `precomputed` 非空 → 立即返回 `{ text: precomputed, isLoading: false, isTranslated: true }`，**不调 API**
- `precomputed` 空 / null / undefined → 走现有 lazy 路径不变

**`<Translated>` 组件**：增加 `precomputed` prop 透传给 hook。

调用点更新（zh-CN 才传 precomputed，en 直接用原文）：
- `ChatMessages.tsx`: `<Translated text={message.content} precomputed={message.content_zh} />`
- `DecisionTracker.tsx`: 同样模式给 reasoning_summary、portfolio_assessment
- 侧边栏 chat title：同样模式

### 5.6 失败处理

- LLM 抛错/超时：`translate_for_persistence` 内 `try/except` 兜住，所有
  `_zh` 字段返回 `None`，写一条 `WARN logger.warning("translation failed for ...")`
  日志
- 英文字段**照常**写入，业务流程不被翻译失败阻塞
- 前端读到 `_zh = null` → `useTranslated` 走 lazy 路径，命中 Redis 缓存或
  调 `/api/translate`
- 这意味着 lazy 路径**降级为 fallback** 而非删除

## 6. 历史数据回填

**新文件**: `backend/scripts/backfill_translations.py`

```bash
python -m scripts.backfill_translations \
    [--collection messages|trading_decisions|portfolio_decisions|chats|all] \
    [--batch-size 50] \
    [--limit N] \
    [--dry-run]
```

行为：
- 遍历指定 collection 中 `_zh` 字段缺失或为 `null` 的文档
  （MongoDB query：`{<field>_zh: {$in: [null]}}` 或 `{<field>_zh: {$exists: false}}`，
  实际用 `$or` 合并两种情况）
- 每批 N 个文档收集所有英文字段，**一次** batch 调 `translation_service`
- `update_one({_id}, {$set: {field_zh: ...}})` 写回
- 幂等：已有 `_zh` 的跳过；可中断重跑
- 进度打印：`[messages] 1234/5678 done, 12 failed (will retry on next run)`
- 失败的不阻塞批次剩余

`Makefile` 加 target：

```makefile
backfill-translations:
	docker compose exec backend python -m scripts.backfill_translations --collection all
```

## 7. 测试

### Backend 新增

`backend/tests/services/test_persistence_translator.py`：
- 成功路径：3 字段 → 3 个 `_zh` 字段都填上
- LLM 抛 `Exception` → 所有 `_zh` 返回 `None`，不抛
- LLM 超时（mock asyncio.TimeoutError）→ 同上
- 空字符串/纯空白字段短路：不出现在 batch 调用里，返回 `None`
- batch 顺序对应：mock 返回乱序也能正确映射回原字段

`backend/tests/database/test_message_repository.py`（增量）：
- `create()` 后从 DB 读出来 `content_zh` 非空
- LLM mock 失败时 `content_zh = None`，`content` 仍正常

`backend/tests/scripts/test_backfill_translations.py`：
- `--dry-run` 不写 DB
- 已有 `_zh` 跳过
- 批次中部分失败不阻塞其他

### Frontend 新增

`frontend/src/hooks/__tests__/useTranslated.test.ts`（增量）：
- `precomputed` 非空 → 不发请求，立即返回
- `precomputed` 为空 → 走现有 lazy 行为

### 端到端

一个集成测试：HTTP 创建 chat 消息 → 从 MongoDB 直接读 → 断言
`content_zh` 非空且不等于 `content`。

## 8. Risks

| 风险 | 缓解 |
|---|---|
| 写入路径多 1-3s 延迟，影响 chat 流式回复后落库的体感 | 流式 token 已经先到前端；落库延迟不影响用户看到的回答；用户已确认接受 |
| 历史回填 LLM 成本一次性较高 | 复用 Redis 缓存（重复文本 0 成本）；提供 `--limit` 分批；可中断 |
| `_zh` 字段全 collection 加上去之后，旧客户端读到不认识的字段 | Pydantic 用 `Optional[str] = None`；前端 `useTranslated` precomputed 缺失时无缝退到 lazy |
| 翻译失败率高时，前端大量退化到 lazy，等于改造没起作用 | 加日志统计 `_zh = None` 比例；如果 > 5% 触发告警；监控 Anthropic 限流 |
| 后续要支持其他语言（如 ja、ko） | 当前 `_zh` 后缀风格扩展即加 `_ja`；本期不实现，但 schema 不挡路 |

## 9. Validation Plan

1. **本地 dev**：`make dev`，新建一个 chat 用 zh-CN UI 提问 → 看
   `docker compose exec mongo mongosh` 直接查 `messages` collection 是否
   有 `content_zh`
2. **Network tab**：zh-CN 下浏览历史已回填的 chat，DevTools 看
   `/api/translate` 调用次数应为 **0**
3. **Backfill 验证**：跑 `make backfill-translations` 之后，
   `db.messages.countDocuments({content_zh: null})` 应为 0
4. **失败 fallback**：临时把 Anthropic key 设错 → 创建消息 → 检查英文
   仍落库 + 前端打开 zh-CN 仍能看到译文（走 lazy fallback）
5. **测试**：`make test` 全绿
6. **Lint/format**：`make fmt && make lint`
7. **版本号**：按 `CLAUDE.md` 规则 bump backend 和 frontend 的 minor
   版本，更新 `CHANGELOG.md`

## 10. Out of Scope (Future)

- 多目标语言扩展（ja、ko 等）
- 翻译质量反馈环（用户可以纠正翻译并喂回 prompt）
- 翻译缓存预热（写入前根据相似度预查 Redis）
- 删除 lazy 路径（等监控显示 `_zh = None` 比例稳定 < 1% 之后再考虑）
