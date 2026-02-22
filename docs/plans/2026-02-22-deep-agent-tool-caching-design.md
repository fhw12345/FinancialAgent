# Deep Agent Per-Analysis Tool Result Cache

**Date:** 2026-02-22
**Status:** Approved
**Branch:** `users/allen/chat-ux-improvements`

## Problem

A case study of a META deep analysis (2026-02-20, 4.9 min, 114 events, 46 tool calls) revealed massive redundant API calls. Multiple sub-agents (research, debate, rebuttal) call the same tools with identical inputs:

| Tool | Calls | Unique | Redundant |
|------|-------|--------|-----------|
| `get_financial_statements` | 12 | ~4 | ~8 |
| `get_company_overview` | 8 | ~2 | ~6 |
| `get_news_sentiment` | 5 | ~2 | ~3 |
| `get_company_earnings` | 4 | ~1 | ~3 |
| `get_insider_activity` | 3 | ~1 | ~2 |
| **Total** | **46** | **~16** | **~30** |

Estimated wasted time: ~60s of unnecessary API latency per analysis.

### Root Cause

The existing `ToolCacheWrapper` (Redis, 24h TTL for fundamentals) is only used by the ReAct agent flow. The deep agent's sub-agents use raw LangChain `@tool` functions that call APIs directly, bypassing the cache layer.

## Solution: Per-Analysis In-Memory Cache

A simple `AnalysisToolCache` class wraps tool functions with an in-memory dict cache. All sub-agents within one `analyze()` call share the same cache instance.

### Cache Behavior

- **Key:** `tool_name + canonical JSON of inputs` (sorted keys, `default=str`)
- **Value:** The tool's return string (all tools return `str`)
- **Lifetime:** Created at `analyze()` start, garbage collected when `analyze()` returns
- **Thread safety:** Not needed (sub-agents execute sequentially)
- **Eviction:** None (~46 entries max, negligible memory)
- **Errors:** Not cached (exceptions propagate to retry logic)

### Integration Flow

```
analyze()
  -> cache = AnalysisToolCache()
  -> technical_tools = cache.wrap_tools(get_tools_for_subagent(tools, "technical"))
  -> news_tools = cache.wrap_tools(get_tools_for_subagent(tools, "news"))
  -> financial_tools = cache.wrap_tools(get_tools_for_subagent(tools, "financial"))
  -> debater_tools = cache.wrap_tools(get_tools_for_subagent(tools, "debater"))

  Technical: get_historical_prices("META") -> MISS -> fetch + cache
  Debater:   get_company_overview("META")  -> HIT  -> return cached (0ms)
```

### Files Changed

| File | Change | Lines |
|------|--------|-------|
| `agent/tools/analysis_cache.py` | New: `AnalysisToolCache` class | ~40 |
| `agent/deep_react_agent.py` | Create cache, pass to factories | ~10 |
| `agent/subagents/technical.py` | Accept cache param, wrap tools | ~3 |
| `agent/subagents/news.py` | Accept cache param, wrap tools | ~3 |
| `agent/subagents/financial.py` | Accept cache param, wrap tools | ~3 |
| `agent/subagents/debater.py` | Accept cache param, wrap tools | ~3 |

### What Doesn't Change

- Tool implementations (`@tool` functions) remain unchanged
- deepagents library receives normal LangChain tools (wrapped transparently)
- `ToolCacheWrapper` (Redis) stays as-is for ReAct agent
- Event streaming: `deep_tool_end` still fires, cache hits show ~0-1ms duration
- Frontend: no changes needed

### Observability

- Cache logs `hits`, `misses`, `hit_rate` at analysis end (structlog INFO)
- Fast tool completions (~0ms) visible in frontend accordion as near-instant checkmarks

### Testing

- Unit: wrap mock tool, call twice with same inputs, verify function called once
- Unit: cache key normalization (same inputs -> same key, different inputs -> different key)
- Unit: exceptions not cached, propagate to caller
- Integration: verify cache stats logged after mock analysis

### Impact Estimate

- ~30 fewer API calls per analysis
- ~60s faster total duration (from 4.9min to ~3.9min)
- Zero additional infrastructure

## Alternatives Considered

**B: Wire through ToolCacheWrapper (Redis)** - Heavy refactoring to thread `analysis_id/chat_id/user_id` context through deepagents. Marginal benefit over in-memory cache for within-analysis dedup.

**C: Pass research data to debate phase** - Architecturally clean but increases LLM context significantly and removes debater's ability to independently verify data.

## Case Study Reference

Full analysis script: `backend/scripts/analyze_deep_run.py`
Data source: MongoDB `messages` collection, `metadata.raw_data.deep_events`
