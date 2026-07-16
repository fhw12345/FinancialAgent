---
title: Structured LLM Content Blocks Reached a String Regex
status: shipped
version: backend@0.32.1
last_updated: 2026-07-16
owner: maintainer
related_paths:
  - backend/src/core/utils/message_content.py
  - backend/src/agent/langgraph_react_agent.py
  - backend/src/core/utils/title_utils.py
  - backend/src/api/chat/streaming/react_agent.py
---

# Structured LLM Content Blocks Reached a String Regex

> **TL;DR (EN)**: The ReAct agent successfully searched SK hynix, fetched its
> quote and history, and generated an answer, but the stream failed afterward
> because the Copilot Bridge returned `AIMessage.content` as a list of content
> blocks. A title regex expected a string. We now normalize structured message
> content at every final-answer boundary and keep non-text blocks out of the
> user response.
>
> **TL;DR (中文)**：ReAct Agent 已成功搜索海力士、获取股价和历史数据并生成回答，
> 但 Copilot Bridge 返回的 `AIMessage.content` 是 content block 列表，后续标题正则
> 只接受字符串，因此在最后一步失败。现在所有最终回答边界都会统一提取文本，并忽略
> thinking 与 tool-use 等非文本 block。

## 1. Context

The user selected the newly listed Nasdaq symbol `SKHY` and asked:

```text
海力士现在股价多少，最近表现怎么样？
```

The automatic router correctly selected v3. The ReAct agent then completed:

1. `search_ticker`;
2. `get_stock_quote`;
3. `get_historical_prices`.

All market-data calls succeeded. The UI nevertheless ended with:

```text
期望字符串或类字节对象，却得到 'list'
```

## 2. Investigation

The backend log showed an unusual combination:

```text
ReAct agent invocation completed
final_answer_length=2
tool_executions=3

Stream error (v3)
expected string or bytes-like object, got 'list'
```

An answer length of two was the key signal. The model had not generated a
two-character answer. It had returned two structured content blocks.

The streaming handler passed `result["final_answer"]` to:

```python
extract_title_from_response(raw_answer)
```

That helper immediately called a compiled regex with the value. Python regex
functions accept strings or bytes, not a list.

## 3. Root Cause

The code assumed this invariant:

```python
AIMessage.content: str
```

LangChain actually permits:

```python
AIMessage.content: str | list[content_block]
```

The Copilot Bridge Responses translation returned multiple text blocks for the
final message. The agent copied `final_message.content` directly into
`final_answer`, so the structured provider representation escaped into code
that expected user-visible text.

The existing flow router had its own local block-extraction helper, but ReAct,
Deep Agent, debate verdict, and title parsing did not share it.

## 4. Fix

Added one shared boundary:

```python
message_content_to_text(content)
```

It:

- preserves ordinary strings;
- joins dictionary or object text blocks;
- ignores thinking and tool-use blocks;
- returns an empty string for absent content;
- stringifies only non-list fallback values.

The helper is now used by:

- automatic routing classifier output;
- ReAct final answers and zero-tool retries;
- Deep Agent report fallback;
- Deep Agent verdict synthesis;
- title extraction as a final defensive boundary.

Regression coverage includes:

- string content;
- mixed thinking/text/tool-use blocks;
- object-based text blocks;
- a title placed in a separate text block.

## 5. Lessons

### Provider response shape is part of the compatibility contract

An Anthropic-compatible endpoint does not guarantee that every model or bridge
returns identical LangChain content representation.

### Normalize at the semantic boundary

Provider-shaped content should become plain user-visible text before it enters
streaming, persistence, title extraction, or translation.

### Successful tool calls do not prove the response path works

The failure occurred after all expensive work had completed. Tests must cover
the final synthesis-to-stream boundary, not only tool execution.

### Small telemetry anomalies are useful

`final_answer_length=2` looked harmless, but it revealed that the value was a
two-element list rather than a short string.
