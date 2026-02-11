"""
Sub-agent invocation with deepagents graphs and retry logic.

Handles invoking DeepSubAgent instances (backed by deepagents library)
with exponential backoff retry for DashScope transient errors.

Includes DeepToolStreamingCallback for real-time tool event emission
during sub-agent execution.
"""

import asyncio
import random
import time
import uuid
from collections.abc import Callable
from typing import Any
from uuid import UUID

import structlog
from langchain_core.callbacks.base import AsyncCallbackHandler
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from ..api.schemas.deep_agent_events import DeepEventEmitter
from .subagents import DeepSubAgent

logger = structlog.get_logger()

# Retry configuration for DashScope API
MAX_RETRIES = 3
_BASE_DELAY = 2.0
_MAX_DELAY = 30.0
_JITTER_FACTOR = 0.25
_RETRYABLE_KEYWORDS = [
    "ssl",
    "certificate",
    "connection",
    "timeout",
    "max retries",
    "eof occurred",
    "rate limit",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
]


class DeepToolStreamingCallback(AsyncCallbackHandler):
    """Real-time tool event callback for deep agent sub-agents.

    Emits deep_tool_start/deep_tool_end events as tools execute,
    providing real-time streaming instead of post-hoc extraction.

    All event emissions are wrapped in try/except to prevent
    callback failures from crashing the sub-agent.
    """

    def __init__(
        self,
        subagent_name: str,
        emitter: DeepEventEmitter,
        on_event: Callable[[dict[str, Any]], None],
    ) -> None:
        super().__init__()
        self.subagent_name = subagent_name
        self.emitter = emitter
        self.on_event = on_event
        self._tool_starts: dict[UUID, float] = {}  # run_id -> start time
        self._tool_names: dict[UUID, str] = {}  # run_id -> tool name

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Emit deep_tool_start event when a tool begins."""
        tool_name = serialized.get("name", "unknown")
        self._tool_starts[run_id] = time.perf_counter()
        self._tool_names[run_id] = tool_name
        try:
            self.on_event(
                self.emitter.tool_start(
                    subagent_name=self.subagent_name,
                    tool_name=tool_name,
                    inputs=inputs or {},
                )
            )
        except Exception:
            logger.debug(
                "Failed to emit tool_start",
                subagent_name=self.subagent_name,
                tool_name=tool_name,
                exc_info=True,
            )

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Emit deep_tool_end event when a tool completes."""
        start_time = self._tool_starts.pop(run_id, None)
        duration_ms = (
            int((time.perf_counter() - start_time) * 1000)
            if start_time is not None
            else 0
        )
        tool_name = self._tool_names.pop(run_id, "unknown")
        output_preview = str(output)[:200] if output else ""
        try:
            self.on_event(
                self.emitter.tool_end(
                    subagent_name=self.subagent_name,
                    tool_name=tool_name,
                    status="success",
                    duration_ms=duration_ms,
                    output_preview=output_preview,
                )
            )
        except Exception:
            logger.debug(
                "Failed to emit tool_end",
                subagent_name=self.subagent_name,
                tool_name=tool_name,
                exc_info=True,
            )

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Emit deep_tool_end with error status when a tool fails."""
        start_time = self._tool_starts.pop(run_id, None)
        duration_ms = (
            int((time.perf_counter() - start_time) * 1000)
            if start_time is not None
            else 0
        )
        tool_name = self._tool_names.pop(run_id, "unknown")
        try:
            self.on_event(
                self.emitter.tool_end(
                    subagent_name=self.subagent_name,
                    tool_name=tool_name,
                    status="error",
                    duration_ms=duration_ms,
                    output_preview=str(error)[:200],
                )
            )
        except Exception:
            logger.debug(
                "Failed to emit tool_error",
                subagent_name=self.subagent_name,
                tool_name=tool_name,
                exc_info=True,
            )


async def invoke_subagent(
    subagent: DeepSubAgent,
    prompt: str,
    config: RunnableConfig | None = None,
    emitter: DeepEventEmitter | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[str, int]:
    """Invoke a deep sub-agent with retry logic.

    Uses the pre-compiled deepagents graph directly instead of
    creating a new create_react_agent. The graph already has
    built-in tools (filesystem, planning) + custom financial tools
    + skills middleware.

    Args:
        subagent: DeepSubAgent instance with .graph compiled state graph
        prompt: The task/query for the sub-agent to execute
        config: RunnableConfig with runtime parameters
        emitter: Event emitter for sequenced event creation
        on_event: Callback to emit events to the streaming layer

    Returns:
        Tuple of (response_content, tool_count) where tool_count is the
        number of tools actually invoked by the sub-agent.
    """
    subagent_name = subagent.config.name

    logger.debug(
        "Invoking deep subagent",
        subagent_name=subagent_name,
        custom_tools=subagent.tool_names,
    )

    # Inject real-time tool streaming callback into config
    merged_config: RunnableConfig = RunnableConfig(**config) if config else RunnableConfig()
    if emitter and on_event:
        cb = DeepToolStreamingCallback(subagent_name, emitter, on_event)
        raw_callbacks = merged_config.get("callbacks") or []
        existing_callbacks: list[Any] = (
            list(raw_callbacks) if isinstance(raw_callbacks, list) else []
        )
        existing_callbacks.append(cb)
        merged_config["callbacks"] = existing_callbacks

    # Ensure thread_id is set for deepagents state management
    configurable = merged_config.get("configurable", {})
    if "thread_id" not in configurable:
        configurable["thread_id"] = f"{subagent_name}_{uuid.uuid4().hex[:8]}"
        merged_config["configurable"] = configurable

    # Retry loop with exponential backoff
    last_exception: Exception | None = None
    result: dict[str, Any] | None = None
    for attempt in range(MAX_RETRIES):
        try:
            result = await subagent.graph.ainvoke(
                {"messages": [HumanMessage(content=prompt)]},
                config=merged_config,
            )
            if attempt > 0:
                logger.info(
                    "Subagent retry succeeded",
                    subagent_name=subagent_name,
                    attempt=attempt + 1,
                )
            break
        except Exception as e:
            last_exception = e
            error_str = str(e).lower()
            is_retryable = any(kw in error_str for kw in _RETRYABLE_KEYWORDS)

            if not is_retryable or attempt == MAX_RETRIES - 1:
                logger.error(
                    "Subagent invocation failed",
                    subagent_name=subagent_name,
                    attempt=attempt + 1,
                    error=str(e),
                    retryable=is_retryable,
                )
                raise

            delay = min(_BASE_DELAY * (2**attempt), _MAX_DELAY)
            jitter = delay * _JITTER_FACTOR * random.random()
            wait_time = delay + jitter
            logger.warning(
                "Subagent retrying after transient error",
                subagent_name=subagent_name,
                attempt=attempt + 1,
                error=str(e),
                wait_seconds=round(wait_time, 2),
            )
            await asyncio.sleep(wait_time)
    else:
        if last_exception:
            raise last_exception

    if result is None:
        msg = f"Subagent {subagent_name} returned no result"
        raise RuntimeError(msg)

    # Extract final response and actual tool count
    all_messages = result.get("messages", [])
    final_message = all_messages[-1]
    response_content = (
        final_message.content
        if hasattr(final_message, "content")
        else str(final_message)
    )
    tool_count = sum(
        1 for m in all_messages if m.__class__.__name__ == "ToolMessage"
    )

    logger.debug(
        "Subagent completed",
        subagent_name=subagent_name,
        response_length=len(response_content),
        total_messages=len(all_messages),
        tool_count=tool_count,
    )

    return response_content, tool_count
