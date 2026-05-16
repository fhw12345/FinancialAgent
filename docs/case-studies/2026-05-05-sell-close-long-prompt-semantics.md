---
title: SELL = "Close Long" Prompt Semantics
status: shipped
version: backend@0.18.x
last_updated: 2026-05-05
owner: maintainer
related_paths:
  - backend/src/services/watchlist/phase2_decisions.py
---

# SELL 平多仓的"砍仓回平"：LLM 输出歧义不要用文档兜，回 prompt 找根因

> **TL;DR (EN)**: A SELL recommendation came out with `entry_price`,
> `stop_loss`, and `take_profit` written as if it were opening a short
> position ("if it breaks above $655, cut losses and flip"). The reflex
> is to "explain the fields better in the UI." The right fix was to
> rewrite the *prompt* so the LLM uses long-position-closing semantics
> when the action is SELL. Documentation cannot rescue a prompt that
> emits ambiguous text.
> **TL;DR (中文)**: SELL 决策的 `entry_price` / `stop_loss` / `take_profit`
> 字段输出像在"开空头"（"涨破 $655 就砍仓回平"）。直觉是"在 UI 上把
> 字段解释清楚"。正确做法是回 prompt 改根因——让 LLM 在 SELL 时使用
> "平多仓"语义。文档兜不住 prompt 本身生成的歧义文本。

> Date: 2026-05-05
> Component: Phase 2 LLM prompt（portfolio decision price levels）
> Severity: 🟡 中等（用户能看出来但不会把钱亏掉，根因在 prompt 不在代码）

## 1. 背景 / Context

刚给 Phase 2 加了"entry_price / stop_loss / take_profit"三个价位字段后，跑了一次 holdings 分析。MU 那条 SELL 决策长这样：

```
SELL MU @ entry $645 / stop $655 / take_profit $576
Reasoning: 看到 RSI 84 超买、stochastic K 95、price 顶到 fib 1.618，
建议 $645 挂卖单。如果反向涨破 $655 就别等了，砍仓回平。
$576 是 fib 0.618 附近，跌到这里如果还没卖就补救。
```

用户：**"MU 到底挂多少的价格卖出，感觉说得还是不清晰"**

我立刻看价位本身——$645 是 entry、$655 是 stop、$576 是 take_profit。我想用 chat 解释一下三个价位的含义。

但用户继续追问：**"入场也指的是卖出价？"**——这暴露了第一层歧义：`entry_price` 这个字段名是中性的（"入场"），但 LLM 在 SELL 上下文下输出的"entry"实际是"卖出限价"。

我刚开始解释，用户又问：**"涨破这里就别等了，砍仓回平什么意思"**——这是第二层。SELL 是平掉已有多头持仓，不是开空头。"砍仓回平"在没有空头的语境下完全不通。但 LLM 真的这么写了。

## 2. 思考过程 / Reasoning

### 假设 1：UI/文档兜底（被否决）

第一反应：在 DecisionTracker 加 tooltip 解释 entry/stop/take_profit 三个字段在 BUY/SELL 不同语义下分别什么意思。

否决。原因：
- LLM 的 reasoning 本身在用错误的术语（"砍仓回平"），UI tooltip 解释三个字段含义解决不了 reasoning 文本里的问题
- 用户每次看到"砍仓回平"都会困惑一次，加多少 tooltip 都救不了
- 这是 prompt 没说清楚的问题，应该在生成端修

### 假设 2：在 prompt 里加 SELL 语义专属说明（采纳）

去翻 `phase2_decisions.py` 的 Price Levels 章节：原文只说"BUY 时 entry 是买入价、stop 是止损、take_profit 是止盈"——**完全没说 SELL 在平掉已有持仓时这三个字段意味着什么**。LLM 在 BUY/SELL 上下文下沿用了 BUY 语义的术语（"砍仓"），导致 reasoning 文本不自洽。

正确的 SELL 平多仓语义应该是：
- `entry_price` = **挂卖单的限价**（不是入场，是离场）
- `stop_loss` = 价格反向涨破到这就**撤销卖单**，别在高点手贱卖（不是真止损）
- `take_profit` = 卖单不成交、价格继续跌的话，跌到这是**补救性最后离场**（不是止盈）

这三个字段在 SELL 平多仓上下文里跟字面意思**全部相反**——但你不能改字段名（schema 是 BUY/SELL 共用的），只能改 prompt 解释。

### 假设 3：reasoning 必须 cite 全部三个 anchor

同时发现一个更细的问题：MU 那条 reasoning 里**只点了 stop ($655 = fib 1.618)** 和 **take_profit ($576 = fib 0.618)** 的锚点，entry $645 是凭空冒出来的——但 prompt 写的是"reasoning 必须 cite tool-derived levels"。LLM 解读成"cite levels"是部分 cite 就行，没意识到三个价位都要点。

修：把"必须 cite 全部三个价位的 anchor"明文写死。

## 3. 根因 / Root cause

不是代码 bug，是 **prompt schema 设计漏洞**：

1. **字段命名 BUY-centric**（`entry_price` 在 BUY=入场、在 SELL 平多仓=离场限价）。schema 共用是对的（避免数据库分两套），但**不同决策方向下字段语义是反向的**这件事 prompt 没明确教 LLM
2. **reasoning 要求模糊**："cite tool-derived levels" 没说"对所有 levels"、还是"对 levels 中的一些"。LLM 选了后者
3. **没有 SELL=close-long vs SELL=open-short 的区分**。本系统当前只支持平多仓的 SELL，但 LLM 训练数据里 SELL 大概率是开空，写出"砍仓回平"是自然的——它在按训练分布生成

### 为什么发现得晚

Phase 2 之前没有 entry/stop/take_profit 字段，SELL 只输出"卖出"动作，不写价位也就没有"哪个价位什么含义"的歧义。**新加字段后才暴露 prompt 的语义留白**。这是个新功能引入旧 prompt 没覆盖的 case 的典型例子。

## 4. 解决方案 / Fix

`phase2_decisions.py` 的 Price Levels 章节加一段（commit `0422513`）：

```
**Important — SELL semantics when closing an existing long position**:

When the action is SELL on a holding you currently own (closing a long),
the three price fields read DIFFERENTLY than for BUY:

- `entry_price` = the LIMIT SELL price you want to fill at. This is your
  exit, not your entry. Pick a level near resistance (Fibonacci extension,
  recent swing high, RSI overbought reversal point).
- `stop_loss` = if price moves AGAINST your sell intent (i.e., rallies
  through this level), CANCEL the limit order — don't keep trying to sell
  near a top that's still going up. This is a "cancel-and-reassess" trigger,
  NOT a real stop-loss in the long-position sense.
- `take_profit` = if the limit sell at `entry_price` doesn't fill and price
  drops, this is the LAST-RESORT exit price (e.g., Fibonacci 0.618 retrace).
  Below this, momentum is gone — better to close at this level than hold and
  hope.

Do NOT use the phrase "stop out" or "cut losses" or "砍仓" in SELL
reasoning — there's no long position bleeding here, you're just deciding
whether to take the gain at the limit price or cancel the order.

**Required**: `reasoning_summary` must explicitly cite the tool-derived
anchor for ALL THREE prices. Not just stop and take_profit — entry_price
must also point to a specific level (e.g., "entry $645 = Fibonacci 1.618
extension from recent low").
```

Bump v0.21.1，重启，下一轮 holdings 分析时新生成的 SELL reasoning 不再出现"砍仓回平"。

## 5. 教训 / Takeaways

1. **LLM 输出歧义优先回 prompt 找根因，不要在 UI/文档兜**。Tooltip 解释三个字段含义是个低成本的"假修"——它每次提醒用户"对，LLM 在用错误的术语，但你看 tooltip 就能理解"。这是把 LLM 输出质量问题转嫁给用户。**正确做法是把 LLM 输出修对**，让用户读到的 reasoning 本身就自洽。

2. **共用 schema 必须显式教 LLM 不同上下文下字段的反向语义**。BUY 和 SELL 共用 entry/stop/take_profit 三字段是对的——但"BUY 的 entry 是买入价、SELL 平多仓的 entry 是离场限价"这种**反向语义**不能让 LLM 自己悟，要 prompt 明文说。否则 LLM 会按字面意思 + 训练分布默认生成（SELL → 默认开空 → "砍仓"），跟你的产品语义错位。

3. **新增字段 = 必须重审 prompt 是否覆盖所有决策路径**。Entry/stop/take 三字段加进 schema 是用户提的需求，我加的时候只想着"BUY 路径怎么写"，没想到"SELL 在我们系统下专指平多仓而 LLM 默认理解 SELL 是开空"这个语义错位。**任何 schema 扩展都要走一遍每个 enum 取值（BUY/SELL/HOLD × open/close × long/short）的笛卡尔积**，看 prompt 在每个组合下是否都能生成自洽 reasoning。

4. **"必须 cite anchor"要明确 cite 范围**。"cite tool-derived levels" 这种指令对 LLM 是模糊的——它会做"cite 一些"满足要求。要写 **"cite ALL THREE prices' anchors"** 才精确。这是 prompt 工程里很基础的"具体量词比定性描述强"。

5. **用户的"说不清晰"通常比"说错"难诊断**。"MU 到底挂多少的价格卖出"——这不是一个具体的 bug 报告，是用户读完 reasoning 之后心里没建立清晰模型。这种主诉的根因常在 LLM 输出的语义结构层（术语错配、缺关键 anchor），不在 UI 显示层。**面试可以说**：用户给"看不懂/不清晰"反馈的时候，第一反应不应该是"加更多说明"——而是问"输出本身是不是逻辑自洽的、用对术语的"。

6. **prompt 改完不验证 = 等同没改**。改完 prompt 后我自己没立刻跑一轮 SELL 决策验证措辞——只 commit 了。下一次有 SELL 决策时再看 reasoning 是不是真不出现"砍仓回平"。**prompt 改动的验证比代码改动验证更重要**——LLM 不会因为你改了 prompt 就 100% 不再生成旧措辞，prompt 是个软约束。理想流程是改完 prompt 跑 N 个 SELL fixture 各 3 次看输出分布。

## 相关

- [2026-05-05-translation-pipeline-multilayer.md](2026-05-05-translation-pipeline-multilayer.md) — 同一轮 session 的 user-feedback 驱动调试，那篇是 4 层根因，本篇是 prompt 单点修复
