"""
Tool cache wrapper with execution tracking.

Wraps agent tools to provide:
1. Redis caching with TTL strategies
2. Execution metrics tracking (duration, cost, cache hit rate)
3. Database persistence (tool_executions collection)
4. Tool execution timeout with graceful fallback (Story 1.4)
5. Circuit breaker pattern for failing tools (Story 1.4)
"""

import asyncio
import typing
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import structlog

from src.core.utils.date_utils import utcnow

from ..core.utils import generate_tool_cache_key, get_api_cost, get_tool_ttl
from ..core.utils.circuit_breaker import (
    tool_circuit_breaker,
)
from ..database.redis import RedisCache
from ..database.repositories.tool_execution_repository import ToolExecutionRepository
from ..models.tool_execution import ToolExecution

logger = structlog.get_logger()


class ToolCacheWrapper:
    """
    Wrapper for tools with caching and execution tracking.

    Provides a transparent caching layer for registered tools.
    """

    # Default timeout in seconds (Story 1.4: Tool Execution Optimization)
    DEFAULT_TIMEOUT_SECONDS = 30

    # Tool-specific timeouts (seconds) - longer for slow external APIs
    TOOL_TIMEOUTS: dict[str, int] = {
        # News and sentiment tools can be slow
        "NEWS_SENTIMENT": 45,
        "news_sentiment_tool": 45,
        # Fundamentals require multiple API calls
        "INCOME_STATEMENT": 40,
        "BALANCE_SHEET": 40,
        "CASH_FLOW": 40,
        "EARNINGS": 40,
        # Technical indicators with many data points
        "TIME_SERIES_INTRADAY": 35,
        "TIME_SERIES_DAILY": 35,
        # Quick quote tools
        "GLOBAL_QUOTE": 20,
        "REALTIME_BULK_QUOTES": 25,
        # Local analysis tools are fast
        "fibonacci_analysis_tool": 15,
        "stochastic_analysis_tool": 15,
        "macro_analysis_tool": 20,
    }

    def __init__(
        self,
        redis_cache: RedisCache,
        tool_execution_repo: ToolExecutionRepository,
    ):
        """
        Initialize tool cache wrapper.

        Args:
            redis_cache: Redis cache instance
            tool_execution_repo: Repository for tool_executions collection
        """
        self.redis_cache = redis_cache
        self.tool_execution_repo = tool_execution_repo

    def get_timeout_for_tool(self, tool_name: str) -> int:
        """
        Get timeout in seconds for a specific tool.

        Returns tool-specific timeout or default.
        """
        return self.TOOL_TIMEOUTS.get(tool_name, self.DEFAULT_TIMEOUT_SECONDS)

    async def wrap_tool(
        self,
        tool_name: str,
        tool_source: str,
        tool_func: Callable[..., Any] | Callable[..., Awaitable[Any]],
        params: dict[str, Any],
        analysis_id: str,
        chat_id: str,
        user_id: str,
        message_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute tool with caching and tracking.

        Flow:
        1. Generate cache key from params
        2. Check Redis cache
        3. If cache hit → return cached result (skip tool execution)
        4. If cache miss → execute tool, cache result, track execution
        5. Store execution record in database

        Args:
            tool_name: Tool name (e.g., "GLOBAL_QUOTE", "fibonacci_analysis_tool")
            tool_source: Tool source ("1st_party", "mcp_alphavantage")
            tool_func: Tool function to execute (async callable)
            params: Tool input parameters
            analysis_id: Analysis workflow ID
            chat_id: Chat ID
            user_id: User ID
            message_id: Optional message ID that triggered tool

        Returns:
            Tool execution result with metadata:
            {
                "result": <tool output>,
                "execution_id": "exec_abc123",
                "cache_hit": true/false,
                "duration_ms": 1234,
                "api_cost": 0.00004
            }

        Example:
            >>> wrapper = ToolCacheWrapper(redis_cache, tool_repo)
            >>> result = await wrapper.wrap_tool(
            ...     tool_name="GLOBAL_QUOTE",
            ...     tool_source="mcp_alphavantage",
            ...     tool_func=mcp_tool.invoke,
            ...     params={"symbol": "AAPL"},
            ...     analysis_id="analysis-20251101-AAPL",
            ...     chat_id="chat_xyz",
            ...     user_id="user_123"
            ... )
            >>> print(result["result"]["price"])
            271.50
            >>> print(result["cache_hit"])
            False
        """
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        start_time = utcnow()

        # ===== CIRCUIT BREAKER CHECK (Story 1.4) =====
        # Check if tool is blocked by circuit breaker before proceeding
        if not tool_circuit_breaker.can_execute(tool_name):
            circuit_status = tool_circuit_breaker.get_status(tool_name)

            logger.warning(
                "Tool blocked by circuit breaker",
                tool_name=tool_name,
                tool_source=tool_source,
                execution_id=execution_id,
                circuit_state=circuit_status.get("state"),
                consecutive_failures=circuit_status.get("consecutive_failures"),
            )

            # Store circuit breaker rejection record
            await self._store_execution(
                execution_id=execution_id,
                chat_id=chat_id,
                user_id=user_id,
                analysis_id=analysis_id,
                message_id=message_id,
                tool_name=tool_name,
                tool_source=tool_source,
                input_params=params,
                output_result={"error": "Circuit breaker OPEN"},
                status="circuit_breaker_open",
                started_at=start_time,
                duration_ms=0,
                is_paid_api=tool_source.startswith("mcp_"),
                api_cost=0.0,
                cache_hit=False,
                cache_key="",
                error_message=f"Tool '{tool_name}' blocked by circuit breaker",
            )

            # Return graceful fallback
            return {
                "result": {
                    "error": f"Tool '{tool_name}' is temporarily unavailable due to repeated failures",
                    "fallback": True,
                    "message": "The service will be retried automatically. Please try again later.",
                },
                "execution_id": execution_id,
                "cache_hit": False,
                "duration_ms": 0,
                "api_cost": 0.0,
                "circuit_breaker_open": True,
            }

        # Generate cache key
        cache_key = generate_tool_cache_key(tool_source, tool_name, params)

        logger.info(
            "Tool execution request",
            tool_name=tool_name,
            tool_source=tool_source,
            execution_id=execution_id,
            cache_key=cache_key,
            params=params,
        )

        # Check cache
        cached_result = await self.redis_cache.get(cache_key)

        if cached_result is not None:
            # Cache hit - return immediately
            duration_ms = int((utcnow() - start_time).total_seconds() * 1000)

            logger.info(
                "Tool cache hit",
                tool_name=tool_name,
                cache_key=cache_key,
                duration_ms=duration_ms,
            )

            # Store execution record (cache hit)
            await self._store_execution(
                execution_id=execution_id,
                chat_id=chat_id,
                user_id=user_id,
                analysis_id=analysis_id,
                message_id=message_id,
                tool_name=tool_name,
                tool_source=tool_source,
                input_params=params,
                output_result=cached_result,
                status="success",
                started_at=start_time,
                duration_ms=duration_ms,
                is_paid_api=tool_source.startswith("mcp_"),
                api_cost=0.0,  # No cost for cache hit
                cache_hit=True,
                cache_key=cache_key,
            )

            return {
                "result": cached_result,
                "execution_id": execution_id,
                "cache_hit": True,
                "duration_ms": duration_ms,
                "api_cost": 0.0,
            }

        # Cache miss - execute tool with timeout (Story 1.4)
        timeout_seconds = self.get_timeout_for_tool(tool_name)
        logger.info(
            "Tool cache miss - executing",
            tool_name=tool_name,
            timeout_seconds=timeout_seconds,
        )

        try:
            # Execute tool with timeout protection
            import inspect

            if inspect.iscoroutinefunction(tool_func):
                # Async tool - use asyncio.wait_for with timeout
                try:
                    result = await asyncio.wait_for(
                        tool_func(**params),
                        timeout=timeout_seconds,
                    )
                except TimeoutError:
                    # Timeout - return graceful fallback
                    end_time = utcnow()
                    duration_ms = int((end_time - start_time).total_seconds() * 1000)

                    # Record timeout as failure with circuit breaker (Story 1.4)
                    timeout_error = TimeoutError(
                        f"Tool execution timed out after {timeout_seconds}s"
                    )
                    tool_circuit_breaker.record_failure(tool_name, timeout_error)

                    logger.warning(
                        "Tool execution timeout",
                        tool_name=tool_name,
                        timeout_seconds=timeout_seconds,
                        duration_ms=duration_ms,
                        circuit_breaker_status=tool_circuit_breaker.get_status(
                            tool_name
                        ),
                    )

                    # Store timeout execution record
                    await self._store_execution(
                        execution_id=execution_id,
                        chat_id=chat_id,
                        user_id=user_id,
                        analysis_id=analysis_id,
                        message_id=message_id,
                        tool_name=tool_name,
                        tool_source=tool_source,
                        input_params=params,
                        output_result={"error": f"Timeout after {timeout_seconds}s"},
                        status="timeout",
                        started_at=start_time,
                        duration_ms=duration_ms,
                        is_paid_api=tool_source.startswith("mcp_"),
                        api_cost=0.0,
                        cache_hit=False,
                        cache_key=cache_key,
                        error_message=f"Tool execution timed out after {timeout_seconds}s",
                    )

                    # Return graceful fallback result
                    return {
                        "result": {
                            "error": f"Tool '{tool_name}' timed out after {timeout_seconds}s",
                            "fallback": True,
                            "message": "Please try again or use a simpler query.",
                        },
                        "execution_id": execution_id,
                        "cache_hit": False,
                        "duration_ms": duration_ms,
                        "api_cost": 0.0,
                        "timeout": True,
                    }
            else:
                result = tool_func(**params)

            # Calculate duration
            end_time = utcnow()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Get API cost
            api_cost = get_api_cost(tool_source, tool_name)

            # Record success with circuit breaker (Story 1.4)
            tool_circuit_breaker.record_success(tool_name)

            logger.info(
                "Tool executed successfully",
                tool_name=tool_name,
                execution_id=execution_id,
                duration_ms=duration_ms,
                api_cost=api_cost,
            )

            # Cache the result
            ttl = get_tool_ttl(tool_name, params.get("interval"))
            await self.redis_cache.set(cache_key, result, ttl_seconds=ttl)

            logger.info(
                "Tool result cached",
                cache_key=cache_key,
                ttl=ttl,
            )

            # Store execution record (successful)
            await self._store_execution(
                execution_id=execution_id,
                chat_id=chat_id,
                user_id=user_id,
                analysis_id=analysis_id,
                message_id=message_id,
                tool_name=tool_name,
                tool_source=tool_source,
                input_params=params,
                output_result=result,
                status="success",
                started_at=start_time,
                duration_ms=duration_ms,
                is_paid_api=tool_source.startswith("mcp_"),
                api_cost=api_cost,
                cache_hit=False,
                cache_key=cache_key,
            )

            return {
                "result": result,
                "execution_id": execution_id,
                "cache_hit": False,
                "duration_ms": duration_ms,
                "api_cost": api_cost,
            }

        except Exception as e:
            # Tool execution failed
            end_time = utcnow()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Record failure with circuit breaker (Story 1.4)
            tool_circuit_breaker.record_failure(tool_name, e)

            logger.error(
                "Tool execution failed",
                tool_name=tool_name,
                execution_id=execution_id,
                error=str(e),
                exc_info=True,
                circuit_breaker_status=tool_circuit_breaker.get_status(tool_name),
            )

            # Store execution record (failed)
            await self._store_execution(
                execution_id=execution_id,
                chat_id=chat_id,
                user_id=user_id,
                analysis_id=analysis_id,
                message_id=message_id,
                tool_name=tool_name,
                tool_source=tool_source,
                input_params=params,
                output_result={"error": str(e)},
                status="error",
                started_at=start_time,
                duration_ms=duration_ms,
                is_paid_api=tool_source.startswith("mcp_"),
                api_cost=0.0,  # No cost for failed call
                cache_hit=False,
                cache_key=cache_key,
                error_message=str(e),
            )

            # Re-raise exception
            raise

    async def _store_execution(
        self,
        execution_id: str,
        chat_id: str,
        user_id: str,
        analysis_id: str,
        message_id: str | None,
        tool_name: str,
        tool_source: str,
        input_params: dict[str, typing.Any],
        output_result: Any,
        status: str,
        started_at: datetime,
        duration_ms: int,
        is_paid_api: bool,
        api_cost: float,
        cache_hit: bool,
        cache_key: str,
        error_message: str | None = None,
    ) -> None:
        """
        Store tool execution record in database.

        Args:
            All fields from ToolExecution model
        """
        try:
            execution = ToolExecution(
                execution_id=execution_id,
                chat_id=chat_id,
                user_id=user_id,
                analysis_id=analysis_id,
                message_id=message_id,
                tool_name=tool_name,
                tool_source=tool_source,
                input_params=input_params,
                output_result=output_result,
                status=status,
                error_message=error_message,
                started_at=started_at,
                completed_at=utcnow(),
                duration_ms=duration_ms,
                is_paid_api=is_paid_api,
                api_cost=api_cost,
                cache_hit=cache_hit,
                cache_key=cache_key,
            )

            await self.tool_execution_repo.create(execution)

            logger.info(
                "Tool execution stored",
                execution_id=execution_id,
                tool_name=tool_name,
                status=status,
                cache_hit=cache_hit,
            )

        except Exception as e:
            logger.error(
                "Failed to store tool execution",
                execution_id=execution_id,
                error=str(e),
                exc_info=True,
            )
            # Don't raise - storage failure shouldn't break tool execution
