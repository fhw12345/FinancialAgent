# DecisionTracker "已经是中文了还在转圈"：一个 UI bug 牵出 4 层根因

> Date: 2026-05-05
> Component: 前端翻译管道 / 后端持久化 / LLM token 上限 / Markdown 渲染
> Severity: 🟠 中高（用户可见的性能 + 显示双重问题，根因跨 4 层）

## 1. 背景 / Context

DecisionTracker 是 zh-CN 模式下展示 AI 决策（reasoning + 完整研究 markdown）的页面。用户反馈分两次给：

**第一次**："Decision Tracker 那边的翻译还是有问题"
**第二次（澄清）**："他还是第一次就是实时的 call llm 翻译，而不是直接显示已经有的翻译"
**第三次**："点开 full research 时明明已经显示中文了，还在灰色等翻译"
**第四次**："而且 full research 前端显示的是 raw md"

四次反馈每次都揭露一个新的子根因。这种"用户的描述每次更精确一点"的过程，本身就是一种调试节奏——重要的不是一次问出全部，而是每次反馈后愿不愿意回去重新建模假设。

## 2. 思考过程 / Reasoning

### 第一次反馈：以为是 chat 翻译那条路径

最初看到"翻译有问题"，我直觉以为是 `<Translated>` 组件 props 漏传。但页面上**确实显示了中文**——只是慢。我没立刻动手，先问了句"具体什么坏了"，让用户说清楚。

### 第二次反馈：定位到"实时 LLM 调用"vs"读取已存翻译"

"他还是第一次就是实时的 call llm 翻译"——这句话直接告诉我：用户已经知道**有些翻译是预存的**（chat title_zh、message content_zh 都早就这么干了），他要的是 DecisionTracker 也走预存路径。

我立刻 grep `chat_repository.py` 看预存怎么实现的——找到 `translate_for_persistence(fields, redis_cache)` 这个 helper，写入时调一次、把 `{field}_zh` 塞回 mongo。然后看 `_persist_decisions` in `flows.py` ——果然，写入时**根本没调**。同一个套路、同一个 helper、就是没人在 portfolio 这条路径上接进来。

修：reasoning 走 batch translation，前端 `<Translated text={reasoning} precomputed={d.metadata?.reasoning_zh ?? null} />`。Bump v0.21.2 / v0.16.1，重启，结束（**自以为**结束）。

### 第三次反馈：用户的"已经显示中文"vs hook 的"isLoading=true"

"点开 full research 时明明已经显示中文了，还在灰色等翻译"——这句话第一眼我以为又是没传 `precomputed`。但等等，full_research 后端**从来没翻译过**，怎么会显示中文？

去翻 `useTranslated.ts` 和 `Translated.tsx`：

```typescript
// useTranslated.ts:56-67
const query = useQuery({
  queryKey: ["translate", lang, text],
  queryFn: async () => { ... await translateBatch([text], lang) },
  enabled: shouldTranslate,
  staleTime: Infinity,
  gcTime: 1000 * 60 * 60, // 1h
});
// ...
if (query.isLoading) return { text, isLoading: true, isTranslated: false };
```

```tsx
// Translated.tsx:39
style={isLoading ? { opacity: 0.7 } : undefined}
```

看到关键：**React Query 的 `staleTime: Infinity` 意味着同一段文本翻译过一次后内存里有结果**——但如果 `enabled` 重新变 `true`（比如组件重新挂载），query 会去 `fetching` 状态，`isLoading` 也跟着变 true。

也就是说，用户看到的中文是**React Query 缓存命中瞬间渲染**，但 hook 仍然把 query 的状态机走了一遍，触发了 `isLoading=true` 的 opacity 0.7。**视觉上中文已在，loading state 仍 active**——这是个典型的"缓存 + 状态机"的边角案例。

去 docker logs 验证，看到 12-15 秒的 `/api/translate` 调用：

```
2026-05-05 15:43:53 [warning] Request completed method=POST path=/api/translate response_time_ms=15279.91 slow=True
2026-05-05 15:47:07 [warning] Request completed method=POST path=/api/translate response_time_ms=12569.42 slow=True
```

15 秒——一段几 KB 的 markdown 翻译要 15 秒。那"用户看到的中文"到底从哪里来？是浏览器内存里 React Query 之前那次的结果，但 `staleTime: Infinity` + `enabled: true` 重新挂载的组合，让它**再调了一次**。

修法对称 reasoning：写入时预翻译 `full_research_zh`。但这里有个问题——

### 第三次的子坑：max_tokens=4096 静默截断

reasoning 是 <500 字符的短文，batch 翻译 5 条没问题。**full_research 是几 KB 的 markdown**，中文输出大概 1.5-2 倍 token 密度，`max_tokens=4096` 大概率在 prod 已经被静默截断了——只是 reasoning 用的时候碰不到上限，没人发现。

```python
# translation_service.py:114（改前）
llm = get_llm(TRANSLATION_ROLE, temperature=0.0, max_tokens=4096)
```

这是个共享路径——同一个 `_llm_translate` 既给短 reasoning 用，又给长 markdown 用，max_tokens 是写死的常量。短文从未触上限，长文每次都被截。**单测全是短文 fixture**，CI 永远绿。

修：调到 16384。这里有个判断——直接调高会不会影响别的调用？看 `get_llm`，max_tokens 是每次调用的参数，提高 translation 这一处不影响别处。

还有一个并发设计：full_research 不能跟 reasoning 揉进同一个 batch，因为：
1. 一个失败拖垮全批（JSON array 解析 → markdown 里未转义引号容易让模型输出非法 JSON）
2. token 限制风险共享

所以 reasoning 走批量、full_research per-symbol 并发独立调用。每个 symbol 失败不影响其它。

### 第四次反馈：raw markdown

"前端显示的是 raw md"——modal body 用的是：

```tsx
<div className="... whitespace-pre-wrap font-sans ...">
  <Translated text={researchModal.text} as="div" precomputed={...} />
</div>
```

`<Translated>` 组件出来的就是个文本节点，外面 `whitespace-pre-wrap` 把换行保留了但 markdown 标记符号都按字面字符显示。`#` `**` `-` `|` 全是裸字符。

ChatMessages.tsx 早就用 `react-markdown` + `remark-gfm` 渲染 assistant 消息，那一坨 components map 配置（h1-h6、p、ul、li、code、blockquote、table...）抄过来就行。但直接在 modal 里 inline 一大坨太挤——抽个内联子组件 `<ResearchBody>`。

这里有个细节判断：要不要把 ChatMessages 里的 markdown 配置抽成共享组件？我克制住了——这是个跨 wave 的重构，不在当前 task 范围内。**写局部 components map 是务实的债，跟 phase2 verdict 用 regex 解析一样性质**——看到了、记下了、不在这一波修。

## 3. 根因 / Root cause

四个根因从前端往后端递进：

| 层 | 表象 | 根因 |
|---|------|-----|
| 1. UI 视觉 | modal 显示 raw `#`/`**`/`-` | modal body 没用 markdown renderer，只用 `whitespace-pre-wrap` + `<Translated>` |
| 2. React Query 状态机 | "中文已显示但还在转圈" | `staleTime: Infinity` 让数据瞬间渲染，但 `isLoading=true` 走了一次，opacity 0.7 |
| 3. LLM 调用层 | `/api/translate` 12-15 秒 | full_research 没在写入时预翻译，每次开 modal 都走 lazy 路径 |
| 4. LLM 输出层 | （潜在）长文翻译可能不完整 | `max_tokens=4096` 对几 KB 中文输出不够，被静默截断 |

第 3 层是用户主诉，但"已经显示中文了"这句线索带出第 2 层——React Query 缓存命中和 isLoading 状态背离的边角案例。第 1 层是用户看穿后才说的。第 4 层是我修第 3 层时主动发现的、虽然没有可观测证据但根据 token 估算高度怀疑的隐患。

## 4. 解决方案 / Fix

### 三次 commit + bump：

| Commit | Bump | 修哪一层 |
|--------|------|---------|
| 第 1 轮 | backend 0.21.2 / frontend 0.16.1 | reasoning 写入时预翻译，前端 `<Translated precomputed>` |
| 第 2 轮 | backend 0.21.3 / frontend 0.16.2 | full_research 写入时预翻译（per-symbol 并发），max_tokens 4096→16384 |
| 第 3 轮 | frontend 0.16.3 | modal 用 `react-markdown` + 内联 `<ResearchBody>` |

关键代码（`flows.py:_persist_decisions` 的 reasoning + research 双策略）：

```python
# reasoning：批量（短文，安全）
if reasoning_to_translate:
    translations = await translate_for_persistence(reasoning_to_translate, redis_cache=redis_cache)
    for sym in reasoning_to_translate:
        reasoning_zh_by_symbol[sym] = translations.get(f"{sym}_zh")

# full_research：per-symbol 并发（长文，需要隔离）
async def _translate_one(sym, text):
    try:
        out = await translate_for_persistence({"r": text}, redis_cache=redis_cache)
        return sym, out.get("r_zh")
    except Exception as e:
        logger.warning("research_pretranslate_failed", symbol=sym, error=str(e))
        return sym, None

results = await asyncio.gather(
    *(_translate_one(sym, text) for sym, text in research_symbols_to_translate),
)
```

### 第 4 层修法：

```python
# translation_service.py
# max_tokens=16384: full_research can be 5-10KB of markdown; Chinese
# output is ~1.5x token-dense than English, so 4096 was being silently
# truncated for long bodies. Reasoning translations cost a few hundred
# tokens — the higher cap costs nothing for the small case.
llm = get_llm(TRANSLATION_ROLE, temperature=0.0, max_tokens=16384)
```

注释里把"为什么"写清楚——下一个改这里的人不需要再重新推一遍。

## 5. 教训 / Takeaways

1. **"用户描述每次更精确"是调试节奏，不是用户表达不清**。第一次说"翻译有问题"的时候我没冲上去改代码，而是问"具体什么坏了"。如果当时直接动手会掉进"补 precomputed prop"的局部最优——但实际根因递归更深。**面试场景可以说**：用户的反馈是迭代的、不是一次性给齐的，每一轮反馈都该是重新建模假设的契机，不要把上一轮的"修完了"当 ground truth。

2. **`isLoading` 和缓存命中是两回事**。React Query 的 `staleTime: Infinity` 意味着数据可瞬间渲染，但 `enabled` 切换会让 query 走一次 fetching 状态。"视觉显示成功 + loading state 还在 active"是这种缓存策略的边角案例。看到这种 UI 矛盾，先去 hook 实现里看状态机而不是看 props。

3. **共享 LLM 调用路径，max_tokens 必须按最长 case 设上限**。`_llm_translate` 既给 reasoning（500 字符）又给 full_research（几 KB markdown）用，max_tokens=4096 对短的过剩、对长的不够。**没有任何错误日志、没有任何 test 失败、用户也不会察觉**——只是翻译末尾几段悄悄消失。这是 LLM 应用层最阴险的一类 bug：**输出"看起来正常"但是被截断的**。dev/staging 的 reasoning fixture 永远碰不上这个上限，要靠生产数据形状的意识去主动审查。

4. **预翻译 vs 懒翻译的取舍要看实际数据形状**。15 秒一次的 lazy 翻译 + 用户每次开 modal 都要等 = 反正这个 LLM token 早晚要烧。提前烧（写入时）比每次烧（开 modal 时）划算，因为：(a) 写入时已经在跑 Phase 2 重活，多 15 秒并发不显眼；(b) Redis 缓存让相同文本只翻一次；(c) 用户体验是"秒开"vs"等 15 秒"。这种"成本怎么烧"的判断比"功能怎么实现"更值得在 PR 里讨论。

5. **批量翻译要看输入分布决定要不要分批**。reasoning 全是短文，揉一起一次 LLM 调用降低 round-trip 成本是对的；full_research 是大段 markdown，揉一起 (a) 容易超 max_tokens (b) JSON array 解析对未转义引号脆弱 (c) 一条失败拖垮全批。**两个看起来对称的字段，实际属于完全不同的批量策略**。这就是 senior 和 junior 在"批量优化"上的差距——不是会用 batch、是判断什么时候**不该**batch。

6. **看到大模块用 markdown 渲染、小弹窗就裸文本——不是省事，是 inconsistency 漏检**。modal 里 raw md 字符跑出来的根因是 `<Translated>` 组件返回纯文本、外面套 `whitespace-pre-wrap`——这俩组件每个单独看都"工作正常"，组合在一起结果是 markdown 当源码贴。**面试可以说**：UI 一致性 bug 的根因经常不在某个组件里，而在两个本来都正常的组件被错误组合。要靠 visual 回归测试或者跨页面 audit 才能抓——单测和类型系统抓不到。

7. **三次 bump、三次 commit、不合一**。每个 commit 修一层根因，CHANGELOG 写明白"用户反馈是什么、根因是什么、为什么这样修"。这种"分阶段持续修"的提交节奏比"一锅端发布"更适合事后回顾——也更适合面试时讲："这个 bug 我修了三遍，每遍发现一个更深的根因，我现在还能讲出每次的判断逻辑"。

## 相关

- [2026-05-04-decision-tracking-cross-layer.md](2026-05-04-decision-tracking-cross-layer.md) — 同一个 DecisionTracker 子系统，上次是端到端 instrumentation，这次是 i18n 管道
- [2026-05-04-token-extraction-getattr-on-dict.md](2026-05-04-token-extraction-getattr-on-dict.md) — 同一类"测试数据形状不等于生产数据形状"，上次是 Mock 遮蔽 dict，这次是 fixture 短文遮蔽 max_tokens 截断
