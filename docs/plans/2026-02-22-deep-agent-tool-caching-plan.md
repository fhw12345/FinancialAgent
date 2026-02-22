# Deep Agent Per-Analysis Tool Cache — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate ~30 redundant API calls per deep analysis by adding a per-analysis in-memory tool result cache shared across all sub-agents.

**Architecture:** A new `AnalysisToolCache` class wraps LangChain tool functions with a dict-based cache keyed on `(tool_name, canonical_inputs)`. Created in `_create_subagents()`, shared by all 4 sub-agent factories, garbage collected when `analyze()` returns.

**Tech Stack:** Python 3.12, LangChain `@tool` / `StructuredTool`, structlog, pytest

**Design doc:** `docs/plans/2026-02-22-deep-agent-tool-caching-design.md`

---

### Task 1: Write AnalysisToolCache with failing tests

**Files:**
- Create: `backend/tests/test_analysis_cache.py`
- Create: `backend/src/agent/tools/analysis_cache.py` (empty stub)

**Step 1: Write the failing tests**

Create `backend/tests/test_analysis_cache.py`:

```python
"""Unit tests for AnalysisToolCache."""

import pytest

from src.agent.tools.analysis_cache import AnalysisToolCache


# ===== Helpers =====

def make_mock_tool(name: str, return_value: str = "result"):
    """Create a minimal mock LangChain tool for testing."""
    call_count = {"n": 0}

    async def _invoke(**kwargs):
        call_count["n"] += 1
        return return_value

    class _Tool:
        pass

    tool = _Tool()
    tool.name = name
    tool.description = f"Mock {name}"
    tool.args_schema = None
    tool.coroutine = _invoke
    tool.func = None
    tool.call_count = call_count
    return tool


def make_failing_tool(name: str, error: Exception):
    """Create a mock tool that raises on invoke."""
    async def _invoke(**kwargs):
        raise error

    class _Tool:
        pass

    tool = _Tool()
    tool.name = name
    tool.description = f"Failing {name}"
    tool.args_schema = None
    tool.coroutine = _invoke
    tool.func = None
    return tool


# ===== Tests =====


class TestAnalysisToolCache:
    """Tests for the per-analysis tool result cache."""

    def test_cache_hit_same_inputs(self):
        """Calling the same tool with same inputs returns cached result."""
        cache = AnalysisToolCache()
        tool = make_mock_tool("get_overview", "overview data")
        wrapped = cache.wrap_tools([tool])

        import asyncio
        result1 = asyncio.get_event_loop().run_until_complete(
            wrapped[0].coroutine(symbol="META")
        )
        result2 = asyncio.get_event_loop().run_until_complete(
            wrapped[0].coroutine(symbol="META")
        )

        assert result1 == "overview data"
        assert result2 == "overview data"
        assert tool.call_count["n"] == 1  # Only called once

    def test_cache_miss_different_inputs(self):
        """Different inputs produce separate cache entries."""
        cache = AnalysisToolCache()
        tool = make_mock_tool("get_overview", "data")
        wrapped = cache.wrap_tools([tool])

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            wrapped[0].coroutine(symbol="META")
        )
        asyncio.get_event_loop().run_until_complete(
            wrapped[0].coroutine(symbol="AAPL")
        )

        assert tool.call_count["n"] == 2  # Called twice

    def test_cache_miss_different_tools(self):
        """Different tool names with same inputs are separate entries."""
        cache = AnalysisToolCache()
        tool_a = make_mock_tool("tool_a", "a")
        tool_b = make_mock_tool("tool_b", "b")
        wrapped = cache.wrap_tools([tool_a, tool_b])

        import asyncio
        r1 = asyncio.get_event_loop().run_until_complete(
            wrapped[0].coroutine(symbol="META")
        )
        r2 = asyncio.get_event_loop().run_until_complete(
            wrapped[1].coroutine(symbol="META")
        )

        assert r1 == "a"
        assert r2 == "b"
        assert tool_a.call_count["n"] == 1
        assert tool_b.call_count["n"] == 1

    def test_errors_not_cached(self):
        """Exceptions propagate and are not cached."""
        cache = AnalysisToolCache()
        tool = make_failing_tool("bad_tool", ValueError("API down"))
        wrapped = cache.wrap_tools([tool])

        import asyncio
        with pytest.raises(ValueError, match="API down"):
            asyncio.get_event_loop().run_until_complete(
                wrapped[0].coroutine(symbol="META")
            )

        # Stats should show miss but no hit
        assert cache.stats["hits"] == 0
        assert cache.stats["misses"] == 1

    def test_stats_tracking(self):
        """Cache tracks hit/miss counts and hit rate."""
        cache = AnalysisToolCache()
        tool = make_mock_tool("overview", "data")
        wrapped = cache.wrap_tools([tool])

        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(wrapped[0].coroutine(symbol="META"))  # miss
        loop.run_until_complete(wrapped[0].coroutine(symbol="META"))  # hit
        loop.run_until_complete(wrapped[0].coroutine(symbol="AAPL"))  # miss

        assert cache.stats == {"hits": 1, "misses": 2, "hit_rate": "33.3%"}

    def test_wrap_preserves_tool_metadata(self):
        """Wrapped tools retain name and description."""
        cache = AnalysisToolCache()
        tool = make_mock_tool("get_overview", "data")
        wrapped = cache.wrap_tools([tool])

        assert wrapped[0].name == "get_overview"
        assert wrapped[0].description == "Mock get_overview"

    def test_empty_tool_list(self):
        """Wrapping an empty list returns an empty list."""
        cache = AnalysisToolCache()
        assert cache.wrap_tools([]) == []

    def test_key_normalization_dict_order(self):
        """Different dict key ordering produces the same cache key."""
        cache = AnalysisToolCache()
        tool = make_mock_tool("financials", "data")
        wrapped = cache.wrap_tools([tool])

        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            wrapped[0].coroutine(symbol="META", period="quarter")
        )
        loop.run_until_complete(
            wrapped[0].coroutine(period="quarter", symbol="META")
        )

        assert tool.call_count["n"] == 1  # Same key despite arg order
```

**Step 2: Create empty stub so import doesn't crash**

Create `backend/src/agent/tools/analysis_cache.py`:

```python
"""Per-analysis in-memory tool result cache (stub)."""


class AnalysisToolCache:
    pass
```

**Step 3: Run tests to verify they fail**

Run: `docker compose exec backend python -m pytest tests/test_analysis_cache.py -v`
Expected: FAIL (AnalysisToolCache has no `wrap_tools` or `stats`)

**Step 4: Commit**

```bash
git add backend/tests/test_analysis_cache.py backend/src/agent/tools/analysis_cache.py
git commit -m "test(deep-agent): add failing tests for AnalysisToolCache"
```

---

### Task 2: Implement AnalysisToolCache

**Files:**
- Modify: `backend/src/agent/tools/analysis_cache.py`

**Step 1: Implement the full class**

Replace `backend/src/agent/tools/analysis_cache.py` with:

```python
"""
Per-analysis in-memory tool result cache.

Shared across all sub-agents within a single deep analysis run.
Eliminates redundant API calls when multiple sub-agents
(research -> debate -> rebuttal) query the same data.

Usage:
    cache = AnalysisToolCache()
    wrapped_tools = cache.wrap_tools(original_tools)
    # Pass wrapped_tools to sub-agent factory
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class AnalysisToolCache:
    """In-memory cache for tool results, scoped to one analysis run."""

    _cache: dict[str, str] = field(default_factory=dict, repr=False)
    _hits: int = field(default=0, repr=False)
    _misses: int = field(default=0, repr=False)

    @property
    def stats(self) -> dict[str, Any]:
        """Cache statistics for observability."""
        total = self._hits + self._misses
        rate = f"{self._hits / total * 100:.1f}%" if total > 0 else "0.0%"
        return {"hits": self._hits, "misses": self._misses, "hit_rate": rate}

    def _make_key(self, tool_name: str, kwargs: dict[str, Any]) -> str:
        """Generate a canonical cache key from tool name and inputs."""
        return f"{tool_name}:{json.dumps(kwargs, sort_keys=True, default=str)}"

    def wrap_tools(self, tools: list[Any]) -> list[Any]:
        """Wrap a list of LangChain tools with caching.

        Returns new tool objects with the same name/description/schema
        but with cached async invocation.
        """
        return [self._wrap_single(tool) for tool in tools]

    def _wrap_single(self, tool: Any) -> Any:
        """Wrap a single LangChain tool with caching."""
        original_fn: Callable = tool.coroutine or tool.func
        cache = self

        @wraps(original_fn)
        async def cached_invoke(**kwargs: Any) -> str:
            key = cache._make_key(tool.name, kwargs)
            if key in cache._cache:
                cache._hits += 1
                return cache._cache[key]
            cache._misses += 1
            result = await original_fn(**kwargs)
            cache._cache[key] = result
            return result

        # Build a lightweight wrapper preserving tool metadata
        wrapped = _CachedToolWrapper(
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
            coroutine=cached_invoke,
        )
        return wrapped

    def log_stats(self) -> None:
        """Log cache stats at end of analysis."""
        logger.info("Analysis tool cache stats", **self.stats)


class _CachedToolWrapper:
    """Minimal tool wrapper that satisfies deepagents' tool interface."""

    def __init__(
        self,
        name: str,
        description: str,
        args_schema: Any,
        coroutine: Callable,
    ):
        self.name = name
        self.description = description
        self.args_schema = args_schema
        self.coroutine = coroutine
        self.func = None  # deepagents checks this attribute
```

**Step 2: Run tests to verify they pass**

Run: `docker compose exec backend python -m pytest tests/test_analysis_cache.py -v`
Expected: All 8 tests PASS

**Step 3: Commit**

```bash
git add backend/src/agent/tools/analysis_cache.py
git commit -m "feat(deep-agent): implement AnalysisToolCache with stats"
```

---

### Task 3: Wire cache into sub-agent factories

**Files:**
- Modify: `backend/src/agent/subagents/technical.py:21-81` (add cache param)
- Modify: `backend/src/agent/subagents/news.py:21-80` (add cache param)
- Modify: `backend/src/agent/subagents/financial.py:21-80` (add cache param)
- Modify: `backend/src/agent/subagents/debater.py:25-89` (add cache param)

**Step 1: Add `cache` parameter to each factory**

The change is identical for all 4 factories. In each file:

1. Add import at top:
```python
from ..tools.analysis_cache import AnalysisToolCache
```

2. Add `cache: AnalysisToolCache | None = None` parameter to the factory function signature.

3. After extracting tools via `get_tools_for_subagent()`, wrap them if cache is provided:
```python
    domain_tools = list(get_tools_for_subagent(
        list(tools.values()), "<domain>"
    ).values())

    if cache is not None:
        domain_tools = cache.wrap_tools(domain_tools)
```

Example for `technical.py` — the function signature becomes:

```python
def create_technical_subagent(
    tools: dict[str, Callable],
    model: "BaseChatModel",
    context: AgentContext | None = None,
    cache: AnalysisToolCache | None = None,
) -> DeepSubAgent:
```

And lines 72-74 become:

```python
    technical_tools = list(get_tools_for_subagent(
        list(tools.values()), "technical"
    ).values())

    if cache is not None:
        technical_tools = cache.wrap_tools(technical_tools)
```

Repeat for `news.py` (line 71-73), `financial.py` (line 71-73), `debater.py` (line 80-82).

**Step 2: Run existing tests to verify no regressions**

Run: `docker compose exec backend python -m pytest tests/ -x -q --timeout=60`
Expected: All existing tests pass (cache param is optional, defaults to None)

**Step 3: Commit**

```bash
git add backend/src/agent/subagents/technical.py backend/src/agent/subagents/news.py backend/src/agent/subagents/financial.py backend/src/agent/subagents/debater.py
git commit -m "feat(deep-agent): accept optional cache param in sub-agent factories"
```

---

### Task 4: Wire cache into DeepReActAgent._create_subagents

**Files:**
- Modify: `backend/src/agent/deep_react_agent.py:33` (add import)
- Modify: `backend/src/agent/deep_react_agent.py:107-118` (`_create_subagents`)
- Modify: `backend/src/agent/deep_react_agent.py:120-133` (`_build_workflow`)

**Step 1: Add import**

At `deep_react_agent.py:33`, add:

```python
from .tools.analysis_cache import AnalysisToolCache
```

**Step 2: Add cache to `_create_subagents`**

Change the `_create_subagents` method (lines 107-118) to accept and forward a cache:

```python
    def _create_subagents(
        self,
        context: AgentContext,
        cache: AnalysisToolCache | None = None,
    ) -> dict[str, Any]:
        """Create all sub-agents with context and optional tool cache."""
        return {
            "technical": create_technical_subagent(
                self.tools_dict, self.llm, context, cache=cache
            ),
            "news": create_news_subagent(
                self.tools_dict, self.llm, context, cache=cache
            ),
            "financial": create_financial_subagent(
                self.tools_dict, self.llm, context, cache=cache
            ),
            "debater": create_debater_subagent(
                self.tools_dict, self.llm, context, cache=cache
            ),
        }
```

**Step 3: Create cache in `_build_workflow` and log stats**

In `_build_workflow` (line 133), replace `subagents = self._create_subagents(context)` with:

```python
        cache = AnalysisToolCache()
        subagents = self._create_subagents(context, cache=cache)
```

Then find the end of the `analyze()` method where the result dict is returned (search for `return {` in `analyze()`). Before the return, add:

```python
        cache.log_stats()
```

Note: `cache` is created in `_build_workflow` and used by nodes via closure. The `analyze()` method calls `_build_workflow` — the cache variable is accessible where `log_stats()` needs to be called. Since `_build_workflow` returns a `StateGraph` and `analyze()` compiles and invokes it, the cleanest place to log stats is after `graph.ainvoke()` completes in `analyze()`.

Actually, since `_build_workflow` returns the graph and `analyze()` invokes it, we need to expose the cache. Two options:
- (a) Store cache as `self._analysis_cache` (instance attr, reset per analyze())
- (b) Return cache from `_build_workflow` alongside the graph

Option (a) is simpler:

In `_build_workflow`, add `self._analysis_cache = cache` after creating it.

In `analyze()`, after `result = await graph.ainvoke(...)`, add:

```python
        if self._analysis_cache:
            self._analysis_cache.log_stats()
```

**Step 4: Run tests**

Run: `docker compose exec backend python -m pytest tests/ -x -q --timeout=60`
Expected: All tests pass

**Step 5: Commit**

```bash
git add backend/src/agent/deep_react_agent.py
git commit -m "feat(deep-agent): create AnalysisToolCache per analysis run"
```

---

### Task 5: Bump version and final verification

**Files:**
- Modify: version files via bump script

**Step 1: Run full test suite**

Run: `docker compose exec backend python -m pytest tests/ -x -q --timeout=60`
Expected: All tests pass

**Step 2: Run linter**

Run: `cd backend && make fmt && make lint`
Expected: No errors

**Step 3: Bump backend version**

Run: `./scripts/bump-version.sh backend patch`

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: bump backend version for deep agent tool caching"
```

---

### Post-Implementation: Verify with Live Analysis

After deploying (or running locally via `make dev`):

1. Run a deep analysis: open the app, select "Deep" mode, analyze any stock
2. Check backend logs for: `"Analysis tool cache stats", hits=N, misses=M`
3. Verify hits > 0 (confirms caching is working)
4. Run `docker compose exec backend python /app/scripts/analyze_deep_run.py` on the new analysis to compare tool call durations (cache hits should show ~0-1ms)
