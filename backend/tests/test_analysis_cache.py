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

    @pytest.mark.asyncio
    async def test_cache_hit_same_inputs(self):
        """Calling the same tool with same inputs returns cached result."""
        cache = AnalysisToolCache()
        tool = make_mock_tool("get_overview", "overview data")
        wrapped = cache.wrap_tools([tool])

        result1 = await wrapped[0].coroutine(symbol="META")
        result2 = await wrapped[0].coroutine(symbol="META")

        assert result1 == "overview data"
        assert result2 == "overview data"
        assert tool.call_count["n"] == 1  # Only called once

    @pytest.mark.asyncio
    async def test_cache_miss_different_inputs(self):
        """Different inputs produce separate cache entries."""
        cache = AnalysisToolCache()
        tool = make_mock_tool("get_overview", "data")
        wrapped = cache.wrap_tools([tool])

        await wrapped[0].coroutine(symbol="META")
        await wrapped[0].coroutine(symbol="AAPL")

        assert tool.call_count["n"] == 2  # Called twice

    @pytest.mark.asyncio
    async def test_cache_miss_different_tools(self):
        """Different tool names with same inputs are separate entries."""
        cache = AnalysisToolCache()
        tool_a = make_mock_tool("tool_a", "a")
        tool_b = make_mock_tool("tool_b", "b")
        wrapped = cache.wrap_tools([tool_a, tool_b])

        r1 = await wrapped[0].coroutine(symbol="META")
        r2 = await wrapped[1].coroutine(symbol="META")

        assert r1 == "a"
        assert r2 == "b"
        assert tool_a.call_count["n"] == 1
        assert tool_b.call_count["n"] == 1

    @pytest.mark.asyncio
    async def test_errors_not_cached(self):
        """Exceptions propagate and are not cached on retry."""
        cache = AnalysisToolCache()
        tool = make_failing_tool("bad_tool", ValueError("API down"))
        wrapped = cache.wrap_tools([tool])

        # First call should raise and not be cached
        with pytest.raises(ValueError, match="API down"):
            await wrapped[0].coroutine(symbol="META")

        # Second identical call should also raise (error not cached)
        with pytest.raises(ValueError, match="API down"):
            await wrapped[0].coroutine(symbol="META")

        # Two misses, zero hits — confirms errors are never cached
        assert cache.stats["hits"] == 0
        assert cache.stats["misses"] == 2

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        """Cache tracks hit/miss counts and hit rate."""
        cache = AnalysisToolCache()
        tool = make_mock_tool("overview", "data")
        wrapped = cache.wrap_tools([tool])

        await wrapped[0].coroutine(symbol="META")  # miss
        await wrapped[0].coroutine(symbol="META")  # hit
        await wrapped[0].coroutine(symbol="AAPL")  # miss

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

    @pytest.mark.asyncio
    async def test_key_normalization_dict_order(self):
        """Different dict key ordering produces the same cache key."""
        cache = AnalysisToolCache()
        tool = make_mock_tool("financials", "data")
        wrapped = cache.wrap_tools([tool])

        await wrapped[0].coroutine(symbol="META", period="quarter")
        await wrapped[0].coroutine(period="quarter", symbol="META")

        assert tool.call_count["n"] == 1  # Same key despite arg order
