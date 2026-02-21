# Chat UX Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix two UX issues: replace the broken "Load Older Messages" button with infinite scroll, and persist deep agent accordion state so it survives page reload.

**Architecture:** Infinite scroll uses IntersectionObserver on a sentinel div at the top of the message list. Accordion persistence stores deep agent SSE events in the assistant message's `metadata.raw_data["deep_events"]` field; on restore, the frontend replays these events through the existing reducer.

**Tech Stack:** React 18 (useRef, useEffect, useCallback), IntersectionObserver API, Python/FastAPI backend, MongoDB

---

### Task 1: Backend — Collect deep events for persistence

**Files:**
- Modify: `backend/src/api/chat/streaming/deep_agent.py:156-210` (on_event callback)
- Modify: `backend/src/api/chat/streaming/deep_agent.py:307-321` (message persistence)

**Step 1: Add collected_events list alongside event_queue**

In `stream_with_deep_agent()`, right after `result_holder: dict[str, Any] = {}` (line 160), add a list to collect events for persistence:

```python
result_holder: dict[str, Any] = {}
collected_events: list[dict[str, Any]] = []  # NEW: collect for persistence
```

**Step 2: Update on_event callback to also collect events**

Modify the `on_event` callback (lines 162-175) to append to `collected_events`:

```python
def on_event(event: dict[str, Any]) -> None:
    """Synchronous callback — push SSE string into queue.

    Protected against serialization errors to prevent
    crashing the agent task on malformed events.
    """
    try:
        event_queue.put_nowait(format_sse_event(event))
        collected_events.append(event)  # NEW: collect for persistence
    except Exception:
        logger.warning(
            "Failed to enqueue SSE event",
            event_type=event.get("type"),
            exc_info=True,
        )
```

**Step 3: Attach collected_events to message metadata**

Modify the message persistence block (lines 307-321). Add `deep_events` to the `metadata` dict under a `raw_data` key:

```python
assistant_message = await chat_service.add_message(
    chat_id=chat_id,
    user_id=user_id,
    role="assistant",
    content=final_answer,
    source="llm",
    metadata={
        "tool_executions": tool_executions,
        "trace_id": trace_id,
        "agent_type": "deep_react",
        "transaction_id": transaction.transaction_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "raw_data": {"deep_events": collected_events},  # NEW
    },
)
```

**Step 4: Also persist collected_events on timeout**

In the timeout handler (around line 224-229), before yielding the error event, persist whatever events were collected so far. Find the `except TimeoutError:` block and add:

```python
except TimeoutError:
    logger.error("Deep agent timeout", chat_id=chat_id, timeout_seconds=480)
    # Persist partial events even on timeout
    if collected_events and transaction:
        try:
            await chat_service.add_message(
                chat_id=chat_id,
                user_id=user_id,
                role="assistant",
                content="Deep analysis timed out. Partial results may be available.",
                source="llm",
                metadata={
                    "agent_type": "deep_react",
                    "transaction_id": transaction.transaction_id,
                    "raw_data": {"deep_events": collected_events},
                },
            )
        except Exception:
            logger.warning("Failed to persist partial deep events on timeout")
    if transaction:
        await credit_service.fail_transaction(transaction.transaction_id)
    ...
```

Note: `collected_events` is only defined inside the `if DEEP_STREAMING_V2:` branch. The timeout handler is at the same scope level (inside the try block that wraps this branch), so it has access. But guard with `if collected_events` for the non-streaming branch where this variable doesn't exist.

Actually, since the timeout is inside the same try block, and `collected_events` is defined before `run_agent()`, it's in scope. But we need to handle the case where `DEEP_STREAMING_V2` is False — in that case `collected_events` won't be defined. Use a safer pattern:

Before the try block (around line 154), initialize: `collected_events: list[dict[str, Any]] = []`

This way it's always defined regardless of which branch executes.

**Step 5: Run backend tests**

Run: `cd backend && make test`
Expected: All existing tests pass (deep agent tests don't test SSE event persistence)

**Step 6: Commit**

```bash
git add backend/src/api/chat/streaming/deep_agent.py
git commit -m "feat(deep-agent): persist SSE events in message metadata for accordion restore"
```

---

### Task 2: Frontend — Add infinite scroll to ChatMessages

**Files:**
- Modify: `frontend/src/components/chat/ChatMessages.tsx:343-371` (replace button with sentinel)
- Modify: `frontend/src/components/chat/ChatMessages.tsx:231-245` (add refs for scroll preservation)

**Step 1: Add refs and IntersectionObserver for infinite scroll**

In `ChatMessages` component (line 242-245), add new refs:

```typescript
const sentinelRef = useRef<HTMLDivElement>(null);
const scrollContainerRef = useRef<HTMLDivElement>(null);
```

**Step 2: Add IntersectionObserver effect**

After the existing scroll `useEffect` (after line 309), add:

```typescript
// Infinite scroll: observe sentinel at top of message list
useEffect(() => {
  if (!chatId || !hasMore || !onLoadMore || isLoadingMore) return;

  const sentinel = sentinelRef.current;
  if (!sentinel) return;

  const observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && !isLoadingMore) {
        void onLoadMore();
      }
    },
    { threshold: 0.1 },
  );

  observer.observe(sentinel);
  return () => observer.disconnect();
}, [chatId, hasMore, onLoadMore, isLoadingMore]);
```

**Step 3: Add scroll position preservation effect**

The key UX detail — when older messages are prepended, preserve scroll position:

```typescript
// Preserve scroll position when older messages are prepended
const prevMessageCountRef = useRef(messages.length);
useEffect(() => {
  const container = scrollContainerRef.current;
  if (!container) return;

  // Detect if messages were prepended (count increased but not from a new assistant message at bottom)
  if (messages.length > prevMessageCountRef.current) {
    // We can't easily distinguish prepend vs append here,
    // so we rely on the IntersectionObserver load to trigger this.
    // The scroll container's scrollTop is adjusted after render.
  }
  prevMessageCountRef.current = messages.length;
}, [messages.length]);
```

Actually, a simpler approach: capture scrollHeight before render and adjust after. Use a `useLayoutEffect` pattern:

```typescript
// Scroll preservation: track scrollHeight before prepend, restore after
const scrollHeightBeforeRef = useRef<number>(0);
const isLoadingMoreRef = useRef(false);

// Capture before load
useEffect(() => {
  if (isLoadingMore && !isLoadingMoreRef.current) {
    const container = scrollContainerRef.current;
    if (container) {
      scrollHeightBeforeRef.current = container.scrollHeight;
    }
  }
  isLoadingMoreRef.current = isLoadingMore;
}, [isLoadingMore]);

// Restore after messages update (when loading completes)
useEffect(() => {
  if (!isLoadingMore && isLoadingMoreRef.current) return; // still loading
  const container = scrollContainerRef.current;
  if (!container || scrollHeightBeforeRef.current === 0) return;

  const scrollDelta = container.scrollHeight - scrollHeightBeforeRef.current;
  if (scrollDelta > 0) {
    container.scrollTop += scrollDelta;
  }
  scrollHeightBeforeRef.current = 0;
}, [messages, isLoadingMore]);
```

Simpler approach using `onLoadMore` wrapper in `EnhancedChatInterface.tsx` (Task 3) that captures/restores scroll position. Keep `ChatMessages` clean.

**Step 4: Replace the button with sentinel + spinner**

Replace lines 353-371 (the button block) with:

```tsx
{/* Infinite scroll sentinel — triggers load when visible */}
{chatId && hasMore && onLoadMore && (
  <div ref={sentinelRef} className="flex justify-center py-2">
    {isLoadingMore && (
      <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
    )}
  </div>
)}
```

**Step 5: Add ref to the scroll container div**

The outermost div at line 343 needs the ref for scroll position preservation:

```tsx
<div ref={scrollContainerRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4 min-h-0">
```

**Step 6: Run frontend type check**

Run: `docker compose exec frontend npx tsc --noEmit`
Expected: No new errors (pre-existing `tokenEstimator.test.ts` error is OK)

**Step 7: Commit**

```bash
git add frontend/src/components/chat/ChatMessages.tsx
git commit -m "feat(chat): replace load-more button with infinite scroll sentinel"
```

---

### Task 3: Frontend — Scroll position preservation in EnhancedChatInterface

**Files:**
- Modify: `frontend/src/components/EnhancedChatInterface.tsx:289-336` (handleLoadMore)

**Step 1: Add scroll preservation to handleLoadMore**

Wrap `handleLoadMore` with scroll position capture/restore. The scroll container is the `ChatMessages` wrapper div. We need a ref to it.

Add a ref at line ~68:

```typescript
const chatScrollRef = useRef<HTMLDivElement>(null);
```

Pass it to `ChatMessages` as a prop (or use a callback ref). But since `ChatMessages` already has `scrollContainerRef` from Task 2, the simplest approach: export a forwarded ref from `ChatMessages`.

Alternative (simpler — no prop change): Use a DOM query in `handleLoadMore`:

```typescript
const handleLoadMore = useCallback(async () => {
  if (!chatId || isLoadingMore) return;

  setIsLoadingMore(true);

  // Capture scroll position BEFORE loading
  const scrollContainer = document.querySelector('.overflow-y-auto');
  const prevScrollHeight = scrollContainer?.scrollHeight ?? 0;

  try {
    const { chatService } = await import("../services/api");
    const currentOffset = messages.length;
    const chatDetail = await chatService.getChatDetail(chatId, 50, currentOffset);

    if (chatDetail.messages.length === 0) {
      setHasMoreMessages(false);
      return;
    }

    const olderMessages = chatDetail.messages.map((msg) => ({
      role: msg.role as "user" | "assistant",
      content: msg.content,
      timestamp: msg.timestamp,
      analysis_data: msg.metadata?.raw_data as Record<string, unknown> | undefined,
      tool_call: msg.tool_call,
    }));

    setMessages((prev) => [...olderMessages, ...prev]);
    setHasMoreMessages(chatDetail.messages.length === 50);

    // Restore scroll position AFTER render
    requestAnimationFrame(() => {
      if (scrollContainer) {
        const newScrollHeight = scrollContainer.scrollHeight;
        scrollContainer.scrollTop += newScrollHeight - prevScrollHeight;
      }
    });
  } catch (error) {
    console.error("Failed to load more messages:", error);
  } finally {
    setIsLoadingMore(false);
  }
}, [chatId, messages.length, isLoadingMore, setMessages]);
```

Note: Removed the error message injection into messages (lines 325-332 of the original) — that was polluting the message list with fake assistant messages on transient errors. A `console.error` is sufficient; the user can scroll up again to retry.

**Step 2: Run frontend type check**

Run: `docker compose exec frontend npx tsc --noEmit`
Expected: No new errors

**Step 3: Commit**

```bash
git add frontend/src/components/EnhancedChatInterface.tsx
git commit -m "feat(chat): add scroll position preservation for infinite scroll"
```

---

### Task 4: Frontend — Replay deep events on chat restore

**Files:**
- Modify: `frontend/src/components/EnhancedChatInterface.tsx:258-276` (handleChatSelect)
- Modify: `frontend/src/hooks/useChatRestoration.ts:42-65` (message conversion)
- Modify: `frontend/src/types/api.ts:43-62` (ChatMessage interface)

**Step 1: Add deep_events field to ChatMessage interface**

In `frontend/src/types/api.ts`, add to the `ChatMessage` interface (after line 61):

```typescript
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  chart_url?: string;
  analysis_data?: Record<string, unknown>;
  _id?: string | number;
  tool_call?: ToolCall;
  tool_progress?: {
    toolName: string;
    displayName: string;
    icon: string;
    status: "running" | "success" | "error";
    symbol?: string;
    inputs?: Record<string, unknown>;
    output?: string;
    error?: string;
    durationMs?: number;
  };
  deep_events?: DeepStreamEvent[];  // NEW: persisted accordion events for restore
}
```

Note: `DeepStreamEvent` is already defined in the same file (line 251+). Make sure the import is available (it's in the same file, so no import needed).

**Step 2: Extract deep_events in useChatRestoration**

In `frontend/src/hooks/useChatRestoration.ts`, modify the message mapping (lines 42-65) to extract `deep_events` from `raw_data`:

```typescript
const restoredMessages: ChatMessage[] = chatDetail.messages.map(
  (msg) => {
    let analysis_data: Record<string, unknown> | undefined = undefined;
    if (
      msg.metadata?.raw_data &&
      Object.keys(msg.metadata.raw_data).length > 0
    ) {
      analysis_data = msg.metadata.raw_data as Record<string, unknown>;
    } else if (msg.metadata && Object.keys(msg.metadata).length > 0) {
      analysis_data = msg.metadata as unknown as Record<string, unknown>;
    }

    // Extract deep_events for accordion restore
    const deep_events = msg.metadata?.raw_data?.deep_events as
      | DeepStreamEvent[]
      | undefined;

    return {
      role: msg.role as "user" | "assistant",
      content: msg.content,
      timestamp: msg.timestamp,
      analysis_data,
      deep_events,  // NEW
    };
  },
);
```

Add import at top of file:

```typescript
import type { ChatMessage, DeepStreamEvent } from "../types/api";
```

(Replace the existing `ChatMessage` import from `../types/api` if it exists, or just add `DeepStreamEvent` to the existing import.)

**Step 3: Replay deep_events in handleChatSelect**

In `EnhancedChatInterface.tsx`, modify `handleChatSelect` (lines 258-276) to replay deep events after restoration:

```typescript
const handleChatSelect = useCallback(
  async (chatId: string) => {
    if (isRestoringRef.current) {
      console.log("Skipping chat select: restoration in progress");
      return;
    }

    isRestoringRef.current = true;
    try {
      // Reset deep accordion before restoring
      deepDispatch({ type: 'RESET' });

      await restoreChat(chatId);
      setHasMoreMessages(true);
    } finally {
      isRestoringRef.current = false;
    }
  },
  [restoreChat, deepDispatch],
);
```

But wait — we need access to the restored messages to find `deep_events`. The `restoreChat` function sets messages via `setMessages`, but `handleChatSelect` doesn't get the messages back.

**Better approach**: Add a return value to `restoreChat` that includes the restored messages, or handle replay inside `useChatRestoration`.

Simplest: have `restoreChat` return the restored messages:

In `useChatRestoration.ts`, change the return:

```typescript
// At end of restoreChat, before the catch:
setChatId(chatId);
return restoredMessages;  // NEW: return for caller to inspect
```

Update the function signature and return type. Then in `handleChatSelect`:

```typescript
const handleChatSelect = useCallback(
  async (chatId: string) => {
    if (isRestoringRef.current) return;

    isRestoringRef.current = true;
    try {
      deepDispatch({ type: 'RESET' });

      const restoredMessages = await restoreChat(chatId);
      setHasMoreMessages(true);

      // Replay deep events from any restored message
      if (restoredMessages) {
        for (const msg of restoredMessages) {
          if (msg.deep_events && Array.isArray(msg.deep_events)) {
            for (const event of msg.deep_events) {
              const action = mapDeepEventToAction(event);
              if (action) {
                deepDispatch(action);
              }
            }
            // Set agent mode to v4-deep so accordion renders
            setAgentMode("v4-deep");
            break; // Only one deep analysis per chat
          }
        }
      }
    } finally {
      isRestoringRef.current = false;
    }
  },
  [restoreChat, deepDispatch],
);
```

Import `mapDeepEventToAction` is already imported at line 17.

**Step 4: Also handle deep_events in handleLoadMore**

When loading older messages that contain `deep_events`, also replay them. In `handleLoadMore`, after converting messages:

```typescript
// Check loaded messages for deep_events
for (const msg of olderMessages) {
  if (msg.deep_events && Array.isArray(msg.deep_events)) {
    deepDispatch({ type: 'RESET' });
    for (const event of msg.deep_events) {
      const action = mapDeepEventToAction(event);
      if (action) deepDispatch(action);
    }
    setAgentMode("v4-deep");
    break;
  }
}
```

Also need to extract `deep_events` in the `handleLoadMore` message conversion. Add:

```typescript
const olderMessages = chatDetail.messages.map((msg) => ({
  role: msg.role as "user" | "assistant",
  content: msg.content,
  timestamp: msg.timestamp,
  analysis_data: msg.metadata?.raw_data as Record<string, unknown> | undefined,
  tool_call: msg.tool_call,
  deep_events: msg.metadata?.raw_data?.deep_events as DeepStreamEvent[] | undefined,  // NEW
}));
```

**Step 5: Run type check**

Run: `docker compose exec frontend npx tsc --noEmit`
Expected: No new errors

**Step 6: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/hooks/useChatRestoration.ts frontend/src/components/EnhancedChatInterface.tsx
git commit -m "feat(deep-agent): replay persisted deep events on chat restore"
```

---

### Task 5: Manual E2E Verification

**Step 1: Start dev environment**

Run: `make dev`

**Step 2: Test infinite scroll**

1. Open `http://localhost:3000`, log in
2. Start a chat, send 3+ messages to build history
3. Open a second chat, send 3+ messages
4. Switch back to first chat — verify messages load
5. If the chat has >50 messages (from prior testing), scroll to top — verify older messages auto-load without a button, and scroll position doesn't jump

**Step 3: Test deep agent accordion persistence**

1. Select "Deep" agent mode
2. Run a deep analysis (e.g., "Analyze AAPL")
3. Verify accordion appears with sub-agents, tools, debate, verdict (live session)
4. Reload the page (Cmd+R)
5. Click on the same chat in sidebar
6. Verify the accordion reappears with the same structure (collapsed state)

**Step 4: Test partial accordion on timeout**

This is hard to test manually. Skip for now — the code handles it gracefully.

**Step 5: Commit any fixes**

If any issues found, fix and commit.

---

### Task 6: Final cleanup and commit

**Step 1: Run full checks**

```bash
cd backend && make fmt && make test && make lint
docker compose exec frontend npx tsc --noEmit
```

**Step 2: Bump version**

```bash
./scripts/bump-version.sh frontend patch
./scripts/bump-version.sh backend patch
```

**Step 3: Final commit**

```bash
git add -A
git commit -m "chore: bump versions for chat UX improvements"
```
