---
title: ReAct Agent — Components, Patterns & Debugging
status: shipped
version: backend@0.7.0+
last_updated: 2026-05-16
owner: maintainer
related_paths:
  - backend/src/api/chat/streaming/react_agent.py
  - backend/src/agent/
---

# ReAct Agent - Components, Patterns & Debugging

Detailed technical reference for the LangGraph ReAct Agent implementation.

> **See also**: [Architecture & Flow](react-agent-integration.md) for the core integration flow.

---

## 🔧 Key Components Explained

### 1. Dependency Injection

```python
# chat.py gets agent via Depends()
async def chat_stream_unified(
    # ...
    react_agent: FinancialAnalysisReActAgent = Depends(get_react_agent),
):
    return await _stream_with_react_agent(request, user_id, chat_service, react_agent)
```

```python
# backend/src/api/dependencies/chat_deps.py
_react_agent_singleton: FinancialAnalysisReActAgent | None = None

def get_react_agent(
    settings: Settings = Depends(get_settings),
    ticker_service: TickerDataService = Depends(get_ticker_data_service),
) -> FinancialAnalysisReActAgent:
    """Singleton per worker process (avoid re-compilation)."""
    global _react_agent_singleton

    if _react_agent_singleton is None:
        _react_agent_singleton = FinancialAnalysisReActAgent(
            settings=settings,
            ticker_data_service=ticker_service,
        )

    return _react_agent_singleton
```

**Why Singleton?**
- LangGraph agent compilation takes 300-500ms
- Singleton caches compiled agent per worker
- Reused across all requests in same worker process

---

### 2. Tool Compression

**Problem**: Financial analysis tools return huge JSON objects (5-20KB)

```python
# Raw Fibonacci result (5KB):
{
    "levels": {
        "0.236": {"price": 220.50, "distance": "2.5%", ...},
        "0.382": {"price": 222.19, "distance": "1.2%", ...},
        # ... 10 more levels
    },
    "swing_high": {"price": 230.00, "date": "2024-01-15", ...},
    "confidence": 0.87,
    # ... tons more metadata
}
```

**Solution**: Compress to 2-3 lines before passing to LLM

```python
# Compressed (100 chars):
"Fibonacci: AAPL @ $180.50
Key Levels: 38.2% ($175.20), 61.8% ($172.10)
Trend Strength: Strong Uptrend, Confidence: 87%"
```

**Benefits**:
- ✅ 99.5% token reduction
- ✅ Faster LLM processing
- ✅ Lower API costs (~¥0.020 saved per request)
- ✅ Focus on actionable insights

---

### 3. Conversation History Management

```python
# Get last 10 messages from MongoDB
messages = await chat_service.get_messages(chat_id, limit=10)
conversation_history = [
    {"role": msg.role, "content": msg.content}
    for msg in reversed(messages)
]

# Pass to agent
result = await agent.ainvoke(
    user_message=request.message,
    conversation_history=conversation_history,  # ◄── Context
)
```

**Why This Matters**:
- LLM sees previous conversation
- Can reference earlier analysis
- Maintains context across turns

**Example**:
```
User: "Analyze AAPL"
Agent: "AAPL shows support at $175..."

User: "What about resistance?"
Agent: "Based on our earlier Fibonacci analysis, resistance is at..."
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
       (Remembers previous discussion)
```

---

### 4. Message Flow

```python
# Inside LangGraph agent
result = await self.agent.ainvoke({"messages": messages}, config=config)

# Returns:
{
    "messages": [
        HumanMessage("Analyze AAPL"),           # User input
        AIMessage("I'll analyze AAPL..."),      # LLM reasoning
        ToolMessage("Fibonacci: ..."),          # Tool result 1
        ToolMessage("Stochastic: ..."),         # Tool result 2
        AIMessage("Based on analysis...")       # Final answer
    ]
}

# We extract the last message:
final_answer = result["messages"][-1].content
```

---

## 💡 Complete Example

### Request Flow

1. **Frontend**:
   ```typescript
   chatService.sendMessageStreamPersistent(
     "Analyze AAPL with Fibonacci and check momentum",
     "chat_abc123",
     { agent_version: "v3" }
   );
   ```

2. **chat.py**:
   - Saves user message to MongoDB
   - Gets conversation history (last 10 messages)
   - Calls `agent.ainvoke(message, history)`

3. **langgraph_react_agent.py**:
   - Wraps message in HumanMessage
   - Calls LangGraph SDK: `self.agent.ainvoke({messages: [...]})`

4. **LangGraph SDK**:
   - **Iteration 1**: Fibonacci analysis → returns compressed result
   - **Iteration 2**: Stochastic analysis → returns compressed result
   - **Iteration 3**: Synthesizes comprehensive response

5. **langgraph_react_agent.py**:
   - Extracts final_answer from messages
   - Returns `{final_answer, tool_executions: 2, trace_id}`

6. **chat.py**:
   - Streams final_answer character-by-character
   - Saves assistant message to MongoDB
   - Sends completion event

7. **Frontend**:
   - Displays chunks as they arrive
   - Shows "Tool executions: 2"

---

## 🎯 Key Design Patterns

### 1. Separation of Concerns

| Component | Responsibility |
|-----------|----------------|
| **chat.py** | HTTP handling, MongoDB persistence, streaming |
| **langgraph_react_agent.py** | Agent logic, tool management, SDK wrapper |
| **LangGraph SDK** | ReAct loop, tool calling, message management |
| **Tools** | Analysis logic, result compression |

### 2. Async All The Way

```python
# API layer
async def chat_stream_unified() -> StreamingResponse:
    return await _stream_with_react_agent(...)

# Orchestrator layer
async def _stream_with_react_agent():
    result = await agent.ainvoke(...)

# Agent layer
async def ainvoke():
    result = await self.agent.ainvoke(...)

# Tool layer
async def fibonacci_analysis_tool():
    result = await analyzer.analyze(...)
```

**Benefits**:
- ✅ Non-blocking I/O
- ✅ Handle multiple concurrent requests
- ✅ Efficient resource usage

### 3. Error Handling at Each Layer

```python
# chat.py
try:
    result = await agent.ainvoke(...)
except Exception as e:
    yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

# langgraph_react_agent.py
try:
    result = await self.agent.ainvoke(...)
except Exception as e:
    return {"final_answer": f"Error: {str(e)}", "tool_executions": 0}

# Tools
try:
    result = await analyzer.analyze(...)
except Exception as e:
    return f"Analysis error: {str(e)}"
```

---

## 📊 Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| **Agent Compilation** | 300-500ms | Cached via singleton |
| **Simple Query** | 2-4s | No tools called |
| **Single Tool** | 4-6s | 1 tool execution |
| **Multi-tool Chain** | 8-12s | 2-3 tools in sequence |
| **Token Usage** | 800-1200 | Multi-tool with compression |
| **Cost per Request** | ~¥0.008 | Multi-tool (with 99.5% compression) |

---

## 🚀 Why This Architecture?

### ✅ Advantages

1. **Clean Separation**:
   - API layer handles HTTP/persistence
   - Agent layer handles AI logic
   - Easy to test each layer independently

2. **Reusable Agent**:
   - Same agent can be used by different endpoints
   - Could add batch processing endpoint
   - Could add WebSocket endpoint

3. **Flexible**:
   - Easy to swap LLM models
   - Easy to add new tools
   - Easy to change streaming strategy

4. **Observable**:
   - trace_id for every request
   - tool_executions counted
   - Logs at each layer

5. **Scalable**:
   - Async for concurrency
   - Singleton for efficiency
   - Stateless (MongoDB for persistence)

---

## 🔍 Debugging Tips

### Check Agent Is Being Called

```python
# Add log in chat.py:
logger.info("Calling agent", message=request.message)
result = await agent.ainvoke(user_message=request.message, ...)
logger.info("Agent returned", tool_executions=result["tool_executions"])
```

### Check Tool Executions

```python
# In langgraph_react_agent.py:
tool_messages = [msg for msg in result["messages"] if msg.__class__.__name__ == "ToolMessage"]
logger.info("Tool executions", count=len(tool_messages), tools=[msg.name for msg in tool_messages])
```

### Check Final Answer

```bash
# Watch backend logs
docker compose logs -f backend | grep "ReAct agent"
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Agent not responding | Dependency injection failed | Check `get_react_agent()` singleton |
| No tools called | LLM didn't understand query | Check prompt and tool descriptions |
| Slow response | Tool compilation on every request | Verify singleton is working |
| Missing context | History not passed | Check `conversation_history` parameter |

---

## Related Documentation

- [Architecture & Flow](react-agent-integration.md) - Core integration flow from request to response
- [SDK ReAct Agent Feature Spec](../features/langgraph-sdk-react-agent.md) - Feature specification
- [Agent Architecture](agent-architecture.md) - 12-Factor agent implementation
