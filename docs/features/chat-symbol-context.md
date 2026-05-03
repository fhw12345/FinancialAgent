# Chat Symbol Context Injection

**Feature ID**: `chat-symbol-context-injection`
**Status**: ✅ Implemented
**Version**: Backend v0.8.1+ (planned)
**Date**: 2025-11-27

---

## Overview

Automatically inject the active/selected symbol from the UI into the chat conversation context, allowing the LLM agent to use it when the user doesn't explicitly mention a stock symbol in their message.

## Problem Statement

Previously, when users selected a symbol (e.g., "GOOG") in the UI but sent chat messages without explicitly mentioning it, the system had no mechanism to pass this context to the LLM. This led to:

- Agent asking for symbol even though user had selected one
- Agent defaulting to examples from system prompt (e.g., "AAPL")
- Poor user experience requiring redundant symbol mentions

### Example Scenario (Before Fix)

1. User selects "GOOG" in symbol search
2. User asks: "What's the trend?"
3. ❌ Agent responds: "Which stock would you like me to analyze?"

### Expected Behavior (After Fix)

1. User selects "GOOG" in symbol search
2. User asks: "What's the trend?"
3. ✅ Agent responds: "Let me analyze GOOG's trend..." (uses active symbol)

---

## Solution Design

### Approach: System Message Injection

Inject the active symbol as a **system message** in the conversation history before invoking the LLM agent.

**Why System Message?**
- ✅ Clean separation of concerns (symbol context ≠ user message)
- ✅ LLM-friendly format (system messages are standard)
- ✅ Easy to override (user's explicit mention takes precedence)
- ✅ No agent code changes required

### Architecture

```
Frontend (User selects "GOOG")
    ↓
UI State Sync (debounced 2s)
    ↓
MongoDB (chat.ui_state.current_symbol = "GOOG")
    ↓
User sends message: "What's the trend?"
    ↓
Backend /api/chat/stream endpoint
    ↓
Extract current_symbol from chat.ui_state
    ↓
Build system message: "[Active Symbol Context] Current selected symbol: GOOG..."
    ↓
Prepend to conversation_history
    ↓
Agent invocation (v2 or v3) with enriched context
    ↓
LLM uses GOOG without asking
```

---

## Implementation Details

### 1. Helper Function

**File**: `backend/src/api/chat.py:73-107`

```python
def _build_symbol_context_message(current_symbol: str | None) -> dict[str, str] | None:
    """Build system context message for active symbol injection."""
    if not current_symbol:
        return None

    return {
        "role": "system",
        "content": (
            f"[Active Symbol Context]\n"
            f"Current selected symbol: {current_symbol}\n\n"
            f"Instructions:\n"
            f"- Use this symbol if the user's question doesn't explicitly mention a stock symbol\n"
            f"- If the user mentions a different symbol, use their mentioned symbol instead\n"
            f"- If no symbol is selected and user doesn't mention one, ask the user which symbol to analyze"
        ),
    }
```

### 2. Symbol Extraction & Injection (v3 - ReAct Agent)

**File**: `backend/src/api/chat.py:795-812`

```python
# Extract active symbol from chat ui_state
chat = await chat_service.get_chat(chat_id, user_id)
current_symbol = None
if chat and chat.ui_state:
    current_symbol = chat.ui_state.current_symbol

if current_symbol:
    symbol_context = _build_symbol_context_message(current_symbol)
    if symbol_context:
        # Prepend system message to conversation history
        conversation_history.insert(0, symbol_context)
        logger.info(
            "Symbol context injected into conversation (v3)",
            chat_id=chat_id,
            symbol=current_symbol,
            history_length=len(conversation_history),
        )
```

### 3. Symbol Extraction & Injection (v2 - Simple Agent)

**File**: `backend/src/api/chat.py:548-565`

Similar logic applied to the v2 (Simple Agent) path.

---

## Behavior Specification

### Scenario A: Active Symbol + No Mention

**Setup**: Active symbol = "GOOG"
**Message**: "What's the trend?"

**Expected**:
- System message injected: `[Active Symbol Context] Current selected symbol: GOOG`
- Agent uses GOOG without asking
- Response: "Based on GOOG's recent price action..."

### Scenario B: Active Symbol + User Override

**Setup**: Active symbol = "GOOG"
**Message**: "Compare AAPL's performance"

**Expected**:
- System message injected with GOOG
- Agent recognizes explicit "AAPL" mention
- Agent uses AAPL (user override takes precedence)
- Response: "Let me analyze AAPL..."

### Scenario C: No Active Symbol + No Mention

**Setup**: No symbol selected (`current_symbol = None`)
**Message**: "What's the market doing?"

**Expected**:
- No system message injected
- Agent cannot infer symbol
- Agent asks: "Which stock symbol would you like me to analyze?"

### Scenario D: No Active Symbol + Explicit Mention

**Setup**: No symbol selected
**Message**: "Analyze TSLA"

**Expected**:
- No system message injected
- Agent extracts "TSLA" from user message
- Response: "Let me analyze TSLA..."

---

## Testing

### Unit Tests

**File**: `backend/tests/test_chat_symbol_context.py`

**Coverage**:
- ✅ Helper function with valid symbol
- ✅ Helper function with None/empty
- ✅ Message structure validation
- ✅ Multiple symbols sequential injection
- ✅ Integration with conversation history

**Run Tests**:
```bash
cd backend
pytest tests/test_chat_symbol_context.py -v
```

**Results**: 11/11 tests passing ✅

### Manual Testing

**Prerequisites**:
```bash
# Start services
docker compose up -d

# Watch backend logs
docker compose logs -f backend
```

**Test Scenarios**:

1. **Scenario A**:
   - Login: http://localhost:3000 (admin/<password>)
   - Select symbol "GOOG"
   - Send: "What's the trend?"
   - Verify: Agent uses GOOG in response

2. **Scenario B**:
   - Active symbol: "GOOG"
   - Send: "How is AAPL performing?"
   - Verify: Agent analyzes AAPL (override)

3. **Scenario C**:
   - No symbol selected
   - Send: "What should I invest in?"
   - Verify: Agent asks which symbol

4. **Scenario D**:
   - No symbol selected
   - Send: "Analyze MSFT"
   - Verify: Agent uses MSFT

**Log Verification**:
```bash
# Check for symbol context injection logs
docker compose logs backend | grep "Symbol context injected"

# Expected output:
# Symbol context injected into conversation (v3) chat_id=chat_xxx symbol=GOOG history_length=3
```

---

## Impact & Benefits

### User Experience
- ✅ **Reduced friction**: No need to repeat symbol in every message
- ✅ **Context awareness**: Agent remembers selected symbol
- ✅ **Flexibility**: User can override by mentioning different symbol

### Technical
- ✅ **Simple implementation**: ~60 lines added to existing endpoint
- ✅ **No frontend changes**: Leverages existing ui_state sync
- ✅ **Backward compatible**: No breaking changes to API
- ✅ **Testable**: Full unit test coverage

### Token Usage
- ⚠️ **Trade-off**: Adds ~20-30 tokens per agent invocation
- ✅ **Benefit**: Reduces back-and-forth clarification (saves overall tokens)

---

## Related Files

| Component | File | Purpose |
|-----------|------|---------|
| **Backend API** | `backend/src/api/chat.py:73-107` | Helper function |
| | `backend/src/api/chat.py:795-812` | v3 injection point |
| | `backend/src/api/chat.py:548-565` | v2 injection point |
| **Models** | `backend/src/models/chat.py:11-47` | UIState model with current_symbol |
| **Tests** | `backend/tests/test_chat_symbol_context.py` | Unit tests (11 tests) |
| **Frontend** | `frontend/src/components/EnhancedChatInterface.tsx` | Symbol selection UI |
| | `frontend/src/hooks/useUIStateSync.ts` | Symbol persistence to MongoDB |
| **Docs** | `docs/features/chat-symbol-context.md` | This document |
| **Plan** | `.claude/plan/chat-symbol-context-injection.md` | Implementation plan |

---

## Deployment Notes

### Version Bump
- Backend: Patch version increment required (e.g., v0.8.0 → v0.8.1)

### Rollout Steps
1. **Local Testing**: Verify all scenarios A-D pass
2. **Unit Tests**: Ensure `pytest tests/test_chat_symbol_context.py` passes
3. **Version Bump**: `./scripts/bump-version.sh backend patch`
4. **Build & Deploy**: Follow [deployment workflow](../deployment/workflow.md)
5. **Monitor**: Watch production logs for symbol injection

### Rollback Plan
If issues arise, remove the symbol context injection code:
1. Comment out lines 795-812 (v3) and 548-565 (v2)
2. Redeploy backend
3. Symbol selection still works, just not auto-injected into context

---

## Future Enhancements

1. **Symbol Override Detection**: Log when user overrides active symbol
2. **Symbol Confidence**: Track how often LLM uses vs. ignores active symbol
3. **Multi-symbol Context**: Support comparing multiple symbols from watchlist
4. **Symbol Validation**: Warn if ui_state symbol is invalid/delisted
5. **Context Compression**: Optimize token usage for long conversations

---

## FAQ

**Q: Does this change the chat API?**
A: No, API contracts remain unchanged. Feature is internal to backend.

**Q: What if I don't select a symbol?**
A: Agent behavior unchanged - will ask for symbol or use explicitly mentioned one.

**Q: Can I override the active symbol?**
A: Yes, mentioning a different symbol in your message takes precedence.

**Q: Does this work with both v2 and v3 agents?**
A: Yes, symbol context is injected for both Simple Agent (v2) and ReAct Agent (v3).

**Q: How do I verify it's working?**
A: Check backend logs for "Symbol context injected" messages with your chat_id.

---

## References

- [CLAUDE.md - Development Guide](../../CLAUDE.md)
- [System Design](../architecture/system-design.md)
- [Chat API Documentation](../../backend/src/api/chat.py)
- [UI State Sync Hook](../../frontend/src/hooks/useUIStateSync.ts)
- [Implementation Plan](./../.claude/plan/chat-symbol-context-injection.md)
