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

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

import structlog
from langchain_core.tools import StructuredTool

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
        is_async = asyncio.iscoroutinefunction(original_fn)
        cache = self

        @wraps(original_fn)
        async def cached_invoke(**kwargs: Any) -> str:
            key = cache._make_key(tool.name, kwargs)
            if key in cache._cache:
                cache._hits += 1
                logger.debug("Tool cache hit", tool=tool.name)
                return cache._cache[key]
            cache._misses += 1
            result = await original_fn(**kwargs) if is_async else original_fn(**kwargs)
            cache._cache[key] = result
            return result

        return StructuredTool(
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
            coroutine=cached_invoke,
            func=lambda **kwargs: None,  # sync stub; never called
        )

    def log_stats(self) -> None:
        """Log cache stats at end of analysis."""
        logger.info("Analysis tool cache stats", **self.stats)
