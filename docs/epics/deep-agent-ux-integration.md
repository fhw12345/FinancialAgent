# Epic 5: Deep Agent UX Integration

> **Epic Type**: Feature / UX Enhancement
> **Created**: 2026-01-30
> **Status**: Active
> **Estimated Stories**: 5

---

## Epic Goal

Transform the deep agent's output from a single wall-of-text markdown dump into a **progressive, real-time, hierarchical UX** with an accordion tree. Users see sub-agents activate live, tools spin as they execute, results appear progressively, and only the **verdict** appears as a chat message bubble. The full analysis is discoverable via expandable sections.

---

## Business Context

The Deep Agent (v4-deep) is wired into the chat API and produces high-quality multi-agent analysis with debate verification. However, the current UX has critical problems:

1. **Wall of text**: The entire 7,000+ character response dumps as one giant message
2. **No progress visibility**: Users stare at a blank screen for 3+ minutes with no feedback
3. **No discoverability**: Sub-agent research, tools used, and debate findings are buried in markdown
4. **No structure**: Technical analyst, news analyst, and financial analyst outputs are not visually separated

### Target Experience

```
User sends "Analyze TSLA stock" in Deep mode
    ↓
[Real-time accordion tree appears]
    ├── 🔬 Deep Analysis: TSLA          ← main agent card (expandable)
    │   ├── 📊 Technical Analyst         ← sub-agent (expandable, shows "running...")
    │   │   ├── 🔧 get_historical_prices ← tool (spinner → ✅ completed)
    │   │   ├── 🔧 stochastic_analysis   ← tool (spinner → ✅ completed)
    │   │   ├── 🔧 fibonacci_analysis    ← tool (spinner → ✅ completed)
    │   │   └── 📝 Result: "TSLA shows bearish..."  ← collapsed summary
    │   ├── 📰 News Analyst              ← sub-agent
    │   │   ├── 🔧 get_company_overview  ← tool
    │   │   ├── 🔧 get_market_movers     ← tool
    │   │   └── 📝 Result: "Mixed sentiment..."
    │   ├── 💰 Financial Analyst         ← sub-agent
    │   │   ├── 🔧 get_company_overview  ← tool
    │   │   └── 📝 Result: "P/E 294x, margin 5.31%..."
    │   └── ⚖️ Debate Verification       ← debate phase
    │       ├── Round 1: "Credit rating contradicted..."
    │       └── Status: ✅ No further concerns
    ↓
[Summary Card]
    Key Findings: 3 risks identified | Risk Level: HIGH
    Tools Used: 8 | Duration: 3m 28s
    ↓
[Verdict Message Bubble]  ← the ONLY chat message
    "The investment thesis rests on unverified premises..."
```

---

## Technical Architecture

### Current State

- `DeepReActAgent.analyze()` runs as a **batch operation** via `workflow.ainvoke()`
- Streaming handler (`deep_agent.py`) waits for full result, then streams chunks
- No structured SSE events for sub-agent lifecycle
- Frontend receives only `chunk` events (raw text)
- All content rendered as one message bubble

### Target State

- `analyze()` refactored to use `workflow.astream()` or callback-based event emission
- New SSE event types: `deep_phase_start`, `deep_subagent_start`, `deep_tool_start`, `deep_tool_end`, `deep_subagent_result`, `deep_debate_update`, `deep_verdict`
- Frontend renders accordion tree component with real-time state updates
- Verdict extracted as separate message; sub-agent work rendered as UI components

### Key Technical Decisions

1. **Event emission**: Use LangGraph `astream_events()` or custom callback handler to emit lifecycle events without blocking the pipeline
2. **Accordion component**: New React component tree, not reusing existing `tool_start`/`tool_end` events (different hierarchy)
3. **Verdict extraction**: Backend separates verdict from research/debate content before streaming
4. **State management**: Frontend uses `useReducer` for accordion tree state (complex nested updates)

---

## Stories

### Story 5.1: Backend - Deep Agent Event Streaming Pipeline
**Status**: Pending
**Estimate**: Large
**Type**: Backend

Refactor the deep agent to emit structured lifecycle events in real-time as the analysis progresses, rather than returning a single batch result.

**Acceptance Criteria**:
1. Deep agent emits structured SSE events for each phase transition (research start, sub-agent start/end, tool start/end, debate start/end, verdict)
2. Events include metadata: sub-agent name, tool name, duration, status, result summary
3. Streaming handler forwards events to frontend as new SSE event types (prefixed `deep_*`)
4. Existing batch `ainvoke()` path preserved as fallback (non-breaking change)
5. Event schema documented with TypeScript types
6. Backend unit tests for event emission

---

### Story 5.2: Frontend - Accordion Tree Component System
**Status**: Pending
**Estimate**: Large
**Type**: Frontend
**Depends On**: 5.1

Build the collapsible accordion UI hierarchy: Main Agent -> Sub-agents -> Tools. Each level expands/collapses independently.

**Acceptance Criteria**:
1. `DeepAgentAccordion` renders a nested tree: main agent card -> sub-agent cards -> tool items
2. Each accordion level expands/collapses independently with smooth animation
3. Sub-agent cards show: icon, name, status (pending/running/completed/failed), result summary
4. Tool items show: name, inputs (symbol), status spinner, duration, output preview
5. Component handles 3-5 sub-agents with 2-6 tools each without performance issues
6. Accessible (keyboard navigation, ARIA attributes for expand/collapse)
7. i18n support for all labels (en + zh-CN)

---

### Story 5.3: Frontend - Real-time Progress Streaming
**Status**: Pending
**Estimate**: Medium
**Type**: Frontend
**Depends On**: 5.1, 5.2

Wire SSE events to the accordion tree for live updates. Users see sub-agents activate, tools spin, and results appear in real-time as the 3+ minute analysis progresses.

**Acceptance Criteria**:
1. New `deep_*` SSE events update accordion state in real-time
2. Sub-agent cards show "running" spinner when active, transition to "completed" with result
3. Tool items show animated spinner during execution, then checkmark with duration
4. Overall progress indicator shows phase (Research → Debate → Synthesis → Verdict)
5. Time elapsed counter visible during analysis
6. Graceful handling of event ordering (out-of-order, duplicate, missing events)
7. Timeout handling: if no events for 60s, show warning; at 5min, show error state

---

### Story 5.4: Verdict Extraction & Summary Card
**Status**: Pending
**Estimate**: Medium
**Type**: Full-Stack
**Depends On**: 5.1, 5.2

Extract the verdict from the deep agent's response and present it as the only chat message bubble. Build a summary card above it showing key findings at a glance.

**Acceptance Criteria**:
1. Backend extracts verdict section separately from research/debate content
2. Verdict appears as a normal chat message bubble (consistent with v3 agent messages)
3. Summary card above verdict shows: key findings count, risk level, tools used count, total duration
4. Sub-agent accordion appears above the summary card (not as a message bubble)
5. Summary card has "expand all" / "collapse all" toggle for the accordion
6. i18n support for summary labels

---

### Story 5.5: Integration Testing, Polish & DRY Cleanup
**Status**: Pending
**Estimate**: Medium
**Type**: Full-Stack
**Depends On**: 5.1, 5.2, 5.3, 5.4

End-to-end testing, visual polish, responsive design, and consolidation of duplicate streaming code.

**Acceptance Criteria**:
1. HarshJudge E2E scenario passing: login -> select deep mode -> send query -> verify accordion renders -> verify verdict message
2. Responsive design: accordion collapses gracefully on mobile (<768px)
3. Streaming handler DRY cleanup: extract shared logic between `react_agent.py` and `deep_agent.py` into common utilities
4. Error state handling: network disconnect, backend timeout, partial response recovery
5. Dark mode compatibility (if applicable)
6. All new components have unit tests (>80% coverage)
7. Existing v3 agent flow unaffected (regression test)

---

## Compatibility Requirements

- [x] Existing v3 agent flow remains unchanged
- [x] Existing v2 copilot flow remains unchanged
- [x] Chat history displays deep agent messages correctly (accordion collapsed by default for old messages)
- [x] Credit system works with new streaming pattern
- [x] Langfuse tracing captures deep agent events

---

## Risk Mitigation

| Risk | Mitigation | Rollback |
|------|------------|----------|
| **LangGraph astream complexity** | Fallback to callback-based event emission; keep batch path | Revert to current batch streaming |
| **Frontend performance with many tools** | Virtual scrolling for large trees; collapse by default | Limit visible depth |
| **SSE event ordering** | Sequence numbers on events; frontend reconciliation | Ignore out-of-order events |
| **Breaking existing deep agent** | Feature flag `deep_streaming_v2`; old path preserved | Disable flag, revert to batch |

---

## Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Time to first visual feedback | ~210s (blank) | <3s (accordion appears) | Playwright timing |
| User understanding of analysis | Low (wall of text) | High (structured tree) | Feedback scores |
| Tool discoverability | 0% (buried in markdown) | 100% (visible in tree) | UI inspection |
| Verdict clarity | Low (scrolling required) | High (prominent message) | Screenshot |

---

## Definition of Done

- [ ] All 5 stories completed with acceptance criteria met
- [ ] Deep agent accordion renders in real-time during analysis
- [ ] Only verdict appears as chat message; sub-agent work in accordion
- [ ] HarshJudge E2E scenario passes
- [ ] Existing v3/v2 agents unaffected
- [ ] i18n complete (en + zh-CN)
- [ ] Code reviewed and merged to main

---

## Technical References

| Reference | Location |
|-----------|----------|
| Deep Agent | `backend/src/agent/deep_react_agent.py` |
| Deep Agent Adapter | `backend/src/agent/deep_agent_adapter.py` |
| Streaming Handler (deep) | `backend/src/api/chat/streaming/deep_agent.py` |
| Streaming Handler (v3) | `backend/src/api/chat/streaming/react_agent.py` |
| Chat Dependencies | `backend/src/api/dependencies/chat_deps.py` |
| Handler Routing | `backend/src/api/chat/streaming/handlers.py` |
| Frontend Chat Interface | `frontend/src/components/EnhancedChatInterface.tsx` |
| SSE Event Types | `frontend/src/types/api.ts` (StreamEvent) |
| Chat API Service | `frontend/src/services/api.ts` |
| useAnalysis Hook | `frontend/src/components/chat/useAnalysis.ts` |
| i18n (en) | `frontend/public/locales/en/chat.json` |
| i18n (zh-CN) | `frontend/public/locales/zh-CN/chat.json` |

---

## Change Log

| Date | Description | Author |
|------|-------------|--------|
| 2026-01-30 | Epic created with 5 stories for deep agent UX integration | Bob (SM) |
