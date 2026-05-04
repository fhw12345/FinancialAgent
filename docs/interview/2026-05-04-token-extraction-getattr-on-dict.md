# Token 统计永远是 0：getattr 用在 dict 上的隐性失败

> Date: 2026-05-04
> Component: backend/src/core/utils/token_utils.py
> Severity: 🟡 中等（不影响功能，但所有的 LLM 成本/用量监控数据都是 0）

## 1. 背景 / Context

跨厂商 LLM 改造后跑端到端 Deep ReAct，最后一行日志显示：

```
[info] Analysis complete   duration_ms=499427  input_tokens=0  output_tokens=0  total_tokens=0
```

500 秒、5 个 sub-agent、100 多次工具调用，**token 计数全是 0**。第一感觉是新接的 GPT/Gemini 响应格式跟 Claude 不一样，所以提取器读不到字段。

## 2. 思考过程 / Reasoning

**假设 1：跨 vendor 引入的 bug。** GPT-5.5 和 Gemini 经 Maestro 转换后的 usage metadata 可能放在不同字段里，提取器只懂 Anthropic 原生格式。

**验证：** 写一个 probe 脚本，对三家模型各发一次请求，dump 完整的 `usage_metadata` + `response_metadata`：

```python
async def probe(role):
    llm = get_llm(role, max_tokens=50)
    r = await llm.ainvoke([HumanMessage(content="say hi")])
    print(f"type(usage_metadata) = {type(r.usage_metadata).__name__}")
    print(f"usage_metadata = {r.usage_metadata}")
```

**输出（三家完全一致）：**
```
=== deep_planner (claude-opus-4.7) ===
  type(usage_metadata) = dict
  usage_metadata = {'input_tokens': 45, 'output_tokens': 14, 'total_tokens': 59, ...}

=== sub_financial (gpt-5.5) ===
  type(usage_metadata) = dict
  usage_metadata = {'input_tokens': 45, 'output_tokens': 10, 'total_tokens': 55, ...}

=== sub_news (gemini-3-flash-preview) ===
  type(usage_metadata) = dict
  usage_metadata = {'input_tokens': 45, 'output_tokens': 18, 'total_tokens': 63, ...}
```

**假设 1 被证伪。** Maestro 把所有 vendor 的 usage 都翻译成了统一的 dict 格式，字段就在那里、就叫 `input_tokens` / `output_tokens`。

**假设 2：那提取器哪里读不到？** 看代码：

```python
# token_utils.py，原版
if hasattr(msg, "usage_metadata") and msg.usage_metadata:
    total_input_tokens += getattr(msg.usage_metadata, "input_tokens", 0)
    total_output_tokens += getattr(msg.usage_metadata, "output_tokens", 0)
```

`usage_metadata` 是 dict，但代码用 `getattr(dict, "input_tokens", 0)`。**dict 没有 `input_tokens` 属性**，只有 `dict["input_tokens"]` 这种访问方式。所以 `getattr` 走默认值 `0`，永远返回 0。

**这是个跟 vendor 完全无关的预存 bug，从一开始就在那里。** 跨厂商改造没引入它，只是因为我顺手验证才发现。

**关键追问：为什么这种基础 bug 没被单元测试抓到？** 看 `tests/test_token_utils.py`：

```python
mock_ai_message.usage_metadata = Mock(input_tokens=100, output_tokens=50)
#                                ^^^^^ 这里造的是带属性的对象，不是 dict
```

测试用 `Mock(input_tokens=100)` 模拟 `usage_metadata`——`Mock` 对象**有** `input_tokens` 属性，所以 `getattr` 在测试里能读到。**测试和 prod 行为完全相反**，于是 bug 长期潜伏。

## 3. 根因 / Root cause

两层叠加：

1. **生产代码错误地用 `getattr` 访问 dict**——LangChain 0.3+ 的 `usage_metadata` 是 `TypedDict` 而不是对象，但代码按对象访问。
2. **单元测试用 `Mock(field=value)` 模拟数据结构**——`Mock` 自动给任何属性返回值，遮蔽了"对象 vs dict"的访问方式差异，导致测试 100% 通过但 prod 100% 失败。

## 4. 解决方案 / Fix

**生产代码** —— `getattr` → `dict.get`：

```python
# Before
total_input_tokens += getattr(msg.usage_metadata, "input_tokens", 0)
total_output_tokens += getattr(msg.usage_metadata, "output_tokens", 0)

# After
um = msg.usage_metadata
total_input_tokens += um.get("input_tokens", 0)
total_output_tokens += um.get("output_tokens", 0)
```

**测试代码** —— `Mock(...)` → 真 dict（6 处）：

```python
# Before
ai_msg.usage_metadata = Mock(input_tokens=100, output_tokens=50)

# After
ai_msg.usage_metadata = {"input_tokens": 100, "output_tokens": 50}
```

**端到端验证：**
```
Claude: input=49 output=6 total=55
GPT:    input=49 output=8 total=57
Gemini: input=49 output=8 total=57
```

三家全部正确报数。22/22 单元测试通过。

## 5. 教训 / Takeaways

1. **`Mock` 是测试中"看起来工作"的最大来源。** 当被测代码用 `getattr` / `obj.field` 访问时，`Mock` 默认会满足你的任何属性访问；当被测代码用 `dict.get` / `obj["field"]` 访问时，必须显式造 dict。**测试 mock 的形状必须和真实数据结构精确一致**，否则测试只是验证"代码不崩"，不是"代码做对"。
2. **统计/监控字段长期为 0 应该当成红灯**。`input_tokens=0 output_tokens=0` 在 deep agent 跑了 500 秒之后是物理不可能的，但日志里看着不显眼。早点加一条 "if usage_metadata exists but extraction returned 0, log warning" 就能更早发现。
3. **修一个 vendor-specific 怀疑前，先用 probe 脚本看真实数据形状**。我一开始假设 GPT/Gemini 格式不一样，写了 30 秒的 probe 一看——三家一模一样。这种 5 分钟的"先看数据再写代码"经常省掉几小时的弯路。
4. **跨厂商验证意外发现的预存 bug 是常见的副产物**——重大重构常常因为接触老代码而暴露老问题。这种"附带发现"是免费的，应当顺手修了或至少记录。
5. **`getattr(x, "field", 0)` 的静默兜底是双刃剑**。它防止崩溃，但同时让"字段名拼错"或"x 类型不对"的 bug 永远静默。在能用更严格的 `x["field"]` + `KeyError` 的地方，宁可让它崩、早暴露。
