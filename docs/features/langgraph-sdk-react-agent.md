---
title: LangGraph SDK ReAct Agent Implementation
status: shipped
version: backend@0.7.0+
last_updated: 2025-12-14
owner: maintainer
related_paths:
  - backend/src/agent/langgraph_react_agent.py
  - backend/src/api/chat/streaming/react_agent.py
---

# LangGraph SDK ReAct Agent Implementation

**Feature**: Flexible Auto-Planning Agent using LangGraph's `create_react_agent` SDK

**Location**: `backend/src/agent/langgraph_react_agent.py`

---

## Summary

Implemented a new **SDK-based ReAct agent** using LangGraph's `create_react_agent` that enables **flexible, autonomous tool chaining** without rigid routing logic. The agent dynamically decides which tools to call based on context, eliminating the need for hardcoded state machine flows.

**Key Achievement**: ✅ **Auto-chaining confirmed** - LLM successfully chained Fibonacci → Stochastic tools autonomously in testing.

---

## Problem Statement

The existing custom state machine agent (`langgraph_agent.py`) has rigid routing:
```
User Query → reasoning_node → conditional_router → ONE tool → synthesis → END
                               └───────────────┘
                               Hardcoded logic
```

**Limitations**:
1. ❌ Cannot chain tools (e.g., "Fibonacci shows support at $150, verify with Stochastic momentum")
2. ❌ Cannot explore multiple timeframes in one conversation
3. ❌ Requires graph modification to add tool sequences
4. ❌ 500+ lines of boilerplate for state management

**User Request**: "Do not specify rigid logic path, it should be dynamically determined by context."

---

## Solution: SDK-Based ReAct Loop

### Architecture

```
User Query
  ↓
┌─→ ReAct Loop (LangGraph SDK Auto-Loop)
│   ├─ LLM reasons about query
│   ├─ Calls tool(s) if needed
│   ├─ Observes tool results
│   └─ Decides: More tools OR Final answer
└─────────────────────┘
     Self-terminating, context-driven
```

**Code Footprint**: ~300 lines (vs 730 lines custom agent)

### Key Features

1. **Auto-Loop**: SDK handles ReAct pattern automatically
   ```python
   agent = create_react_agent(llm, tools, checkpointer=MemorySaver())
   result = await agent.ainvoke({"messages": [HumanMessage(content=query)]})
   ```

2. **Tool Compression**: Results limited to 2-3 lines for context efficiency
   ```python
   return f"""Fibonacci Analysis: {symbol} @ ${price:.2f}
   Key Levels: {', '.join(levels[:3])}
   Trend Strength: {strength}, Confidence: {confidence:.0f}%"""
   ```

3. **Message History**: Built-in with `MemorySaver` checkpointer
   - Thread ID isolates conversations
   - State persists across invocations
   - No manual state passing needed

4. **Observability**: structlog JSON logs scope each agent invocation by `chat_id`
   - Tool calls / results / latencies logged per node
   - No external tracing dependency required for local-only fork

---

## Implementation Details

### File Structure

```
backend/src/agent/
├── langgraph_agent.py         # Existing custom state machine (730 lines)
├── langgraph_react_agent.py   # NEW SDK ReAct agent (300 lines)
└── __init__.py

backend/tests/
├── test_react_sdk.py           # SDK capability validation tests
├── test_react_agent_comparison.py  # SDK vs Custom comparison tests
└── REACT_SDK_FINDINGS.md       # Research findings document
```

### Core Implementation

**Agent Initialization**:
```python
class FinancialAnalysisReActAgent:
    def __init__(self, settings: Settings, ticker_data_service: TickerDataService):
        self.llm = ChatTongyi(...)
        self.tools = [
            self._create_fibonacci_tool(),
            self._create_stochastic_tool(),
        ]
        self.agent = create_react_agent(
            self.llm,
            self.tools,
            checkpointer=MemorySaver()
        )
```

**Tool Compression** (langgraph_react_agent.py:117-173):
```python
@tool
async def fibonacci_analysis_tool(symbol: str, timeframe: str = "1d") -> str:
    """Analyze stock using Fibonacci retracement levels."""
    result = await analyzer.analyze(symbol, timeframe)

    # Compress to 2-3 lines (NOT full dict)
    key_levels = [f"{lv.percentage} (${lv.price:.2f})"
                  for lv in result.fibonacci_levels[:3]
                  if lv.is_key_level]

    return f"""Fibonacci Analysis: {symbol} @ ${result.current_price:.2f}
Key Levels: {', '.join(key_levels)}
Trend Strength: {result.trend_strength}, Confidence: {result.confidence_score * 100:.0f}%"""
```

**Agent Invocation** (langgraph_react_agent.py:246-341):
```python
async def ainvoke(self, user_message: str, conversation_history=None) -> dict:
    thread_id = f"thread_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    messages = [HumanMessage(content=user_message)]

    result = await self.agent.ainvoke(
        {"messages": messages},
        config={"configurable": {"thread_id": thread_id}}
    )

    return {
        "messages": result["messages"],
        "final_answer": result["messages"][-1].content,
        "tool_executions": len([m for m in result["messages"]
                               if m.__class__.__name__ == "ToolMessage"])
    }
```

---

## Test Results

### 1. Single Tool Execution

**Test**: `test_single_tool_fibonacci_sdk`

**Query**: "Analyze AAPL with Fibonacci retracement"

**Result**:
```
✓ Total messages: 6
✓ Tool executions: 2 (LLM called tool twice to retry after initial error)
✓ Final answer: 187 chars
✓ Test: PASSED
```

### 2. Multi-Tool Chaining (**AUTO-PLANNING CONFIRMED**)

**Test**: `test_multi_tool_chaining_sdk`

**Query**: "Analyze AAPL: identify support levels and check if momentum confirms the trend"

**Result**:
```
✓ Total messages: 6
✓ Tool executions: 2

Tool execution sequence:
  [1] fibonacci_analysis_tool: 104 chars
      "Fibonacci Analysis: AAPL @ $262.56..."
  [2] stochastic_analysis_tool: 83 chars
      "Stochastic Analysis: AAPL..."

✅ AUTO-CHAINING CONFIRMED: LLM called multiple tools!
```

**Key Insight**: The LLM autonomously decided to:
1. First call Fibonacci tool (for support levels)
2. Then call Stochastic tool (for momentum confirmation)
3. Synthesize final answer combining both results

**This is exactly what was requested**: "dynamically determined by context"!

### 3. Context Size Validation

**Test**: `test_context_compression_sdk`

**Result**:
```
✓ Tool message 1: 104 chars
✓ Tool message 2: 83 chars
✓ Total tool content: 187 chars
✓ Compression: PASSED (<500 chars per tool)
```

**Comparison**: Without compression, tool results would be ~20KB+ (full analysis dicts)

---

## Comparison: SDK vs Custom State Machine

| Feature | SDK ReAct Agent | Custom State Machine |
|---------|-----------------|---------------------|
| **Code Complexity** | ~300 lines | ~730 lines |
| **Auto-Loop** | ✅ Built-in | ❌ Manual state transitions |
| **Tool Chaining** | ✅ Autonomous (proven in tests) | ⚠️ Requires multiple invocations |
| **Routing Logic** | ⚠️ LLM-driven (less control) | ✅ Explicit `conditional_router` |
| **Message History** | ✅ `MemorySaver` checkpointer | ❌ Manual state passing |
| **Context Compression** | ✅ Compressed tool returns (2-3 lines) | ⚠️ Full dicts in state |
| **Custom State Fields** | ❌ Messages only | ✅ TypedDict with custom fields |
| **Observability** | ✅ structlog JSON traces | ✅ structlog per-node bound context |
| **Flexibility** | ✅ LLM adapts to query | ⚠️ Fixed routing paths |
| **Maintenance** | ✅ Low (SDK updates) | ⚠️ High (manual graph) |

**Performance** (measured in tests):
- SDK: ~10-14 seconds per query with 2 tool calls
- Custom: ~8-10 seconds per query with 1 tool call

**Winner**: SDK for flexibility, Custom for explicit control

---

## Technical Decisions

### 1. Why LangGraph SDK Over Custom Implementation?

**Rationale**:
- ✅ User explicitly requested flexible, context-driven routing
- ✅ 60% less code (300 vs 730 lines)
- ✅ Auto-chaining proven in tests
- ✅ Maintained by LangChain team (future-proof)

**Trade-off**: Less control over routing logic, but that's acceptable for financial analysis use case.

### 2. Why Coexist With Custom Agent?

**Rationale**:
- ✅ Gradual migration strategy
- ✅ Can A/B test both approaches in production
- ✅ Custom agent still useful for complex multi-stage workflows
- ✅ No breaking changes to existing API

**Deployment Strategy**:
- Phase 1: Deploy SDK agent as default
- Phase 2: Monitor performance/cost
- Phase 3: Deprecate custom agent if SDK performs well

### 3. Tool Result Compression Strategy

**Problem**: Full Fibonacci analysis = 20KB+ (arrays, detailed levels)

**Solution**: Return 2-3 line summaries in tool functions
```python
# Before (full dict): ~20KB
{
    "fibonacci_levels": [{"price": 150.0, "percentage": "61.8%", ...}, ...],
    "market_structure": {...},
    "pressure_zone": {...},
    ...
}

# After (compressed string): ~100 chars
"Fibonacci Analysis: AAPL @ $262.56\nKey Levels: 38.2% ($222.19)\nTrend Strength: moderate, Confidence: 52%"
```

**Impact**: 99.5% size reduction, context window preserved

### 4. Observability

structlog JSON logs scope each agent invocation by `chat_id`, with one log
record per tool call / tool result / synthesis step. No external tracing
dependency is required for the local-only fork; logs are tailed via
`docker compose logs -f backend`.

---

## Debugging Features

### X-Debug Header

**Purpose**: Enable verbose debug logging in backend to see full LLM prompts and internal state.

**Usage**:
```bash
# Send X-Debug header to enable debug mode
curl -X POST http://localhost:3000/api/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Debug: true" \
  -H "Content-Type: application/json" \
  -d '{"message": "Analyze AAPL", "agent_version": "v3"}'
```

**Frontend Integration**:
```typescript
// In ModelSettings component
const settings = {
  debug_enabled: true  // Sends X-Debug: true header
};

// API service automatically adds header
chatService.streamChat(message, chatId, {
  debug_enabled: settings.debug_enabled
});
```

**Backend Logging**:
When `X-Debug: true` is sent:
```python
# backend/src/api/chat.py
debug_enabled = x_debug and x_debug.lower() in ("true", "1", "yes")

# Logs full LLM prompt
logger.info(
    "🔍 DEBUG: Full LLM Prompt",
    message_count=len(messages),
    full_messages=[{"type": msg.__class__.__name__, "content": msg.content}]
)
```

**Output**:
```
INFO | 🔍 DEBUG: Full LLM Prompt | message_count=3 | full_messages=[
  {"type": "HumanMessage", "content": "Analyze AAPL"},
  {"type": "AIMessage", "content": "I'll analyze AAPL..."},
  {"type": "ToolMessage", "content": "Fibonacci Analysis: AAPL @ $262.56..."}
]
```

**Use Cases**:
- Debugging agent decision-making
- Understanding tool selection logic
- Troubleshooting unexpected responses
- Development and testing

---

## Known Issues (Historical)

> **Note**: This section documents issues encountered during development. Most have been resolved or are no longer relevant.

### 1. Stochastic Tool Async Error - ✅ RESOLVED

**Issue**: `'async_generator' object has no attribute 'get'` when calling stochastic tool

**Resolution**: Fixed by updating StochasticAnalyzer to properly handle async operations (v0.6.x)

### 2. Parallel Tool Calling - ✅ ACCEPTED

**Finding**: ChatTongyi/DashScope does NOT support parallel tool calls (sequential only)

**Status**: Accepted limitation - sequential chaining is sufficient for financial analysis workflows

### 3. Observability Backend Removed - ✅ RESOLVED

**Issue**: Earlier iterations integrated an external tracing service that required SOCKS proxying in local environments

**Resolution**: External tracing was removed when forking to the personal local-only build. Observability is now handled by structlog JSON logs streamed via `docker compose logs`.

### 4. Test Fixture Warnings - ⚠️ LOW PRIORITY

**Issue**: `pytest-asyncio` warnings about async fixtures

**Status**: Non-blocking (tests pass). Deprioritized as it doesn't affect functionality.

---

## API Integration - ✅ COMPLETED

### Current Endpoint

The ReAct agent is now the **primary chat endpoint**:

```python
# backend/src/api/chat/endpoints.py
@router.post("/message")
async def send_message(...):
    # Uses FinancialAnalysisReActAgent for all chat interactions
    agent = FinancialAnalysisReActAgent(...)
    result = await agent.astream(...)
```

**Status**: ✅ Fully deployed to production (v0.7.0+)

---

## Migration Status - ✅ COMPLETED

### ~~Phase 1: Parallel Deployment~~ → COMPLETED

### ~~Phase 2: A/B Testing~~ → SKIPPED (SDK agent proven superior)

### Phase 3: Full Migration → ✅ COMPLETED (v0.7.0)

```
/api/chat/message
└── Uses SDKAgent (langgraph_react_agent.py)
    └── With streaming tool execution progress
    └── With context compaction (v0.8.8)
```

**Result**: Custom state machine agent (`langgraph_agent.py`) deprecated. SDK ReAct agent is now the sole implementation.

---

## Documentation

- **Research Findings**: `backend/tests/REACT_SDK_FINDINGS.md`
- **SDK Validation Tests**: `backend/tests/test_react_sdk.py`
- **Comparison Tests**: `backend/tests/test_react_agent_comparison.py`
- **This Document**: `backend/docs/features/langgraph-sdk-react-agent.md`

---

## Key Takeaways

1. ✅ **Auto-planning works** - LLM successfully chains tools autonomously
2. ✅ **60% less code** - 300 lines vs 730 lines
3. ✅ **Context compression** - Tool results compressed from 20KB → 100 chars
4. ✅ **Flexible routing** - No hardcoded conditional logic needed
5. ⚠️ **Parallel tools not supported** - ChatTongyi limitation (acceptable)

**Recommendation**: Deploy SDK agent as default for production use.

---

## References

- LangGraph Documentation: https://langchain-ai.github.io/langgraph/
- ReAct Pattern Paper: https://arxiv.org/abs/2210.03629
- Test Results: See [`docs/archive/REACT_SDK_FINDINGS.md`](../archive/REACT_SDK_FINDINGS.md)
