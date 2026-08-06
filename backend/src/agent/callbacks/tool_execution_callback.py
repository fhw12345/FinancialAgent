"""
Tool Execution Callback Handler for Real-Time SSE Streaming.

Intercepts LangGraph agent tool calls and pushes events to asyncio.Queue
for Server-Sent Events (SSE) streaming to frontend.

Key Features:
- Real-time visibility: Stream tool_start, tool_end, tool_error events
- Progress tracking: Frontend displays tool execution status with progress bars
- Strategic integration: Works with ToolCacheWrapper for cost/cache tracking
- Non-blocking: Uses asyncio.Queue for efficient event propagation
"""

import asyncio
import typing
from typing import Any
from uuid import UUID

import structlog
from langchain_core.callbacks.base import AsyncCallbackHandler

from src.core.utils.date_utils import utcnow

from ...core.localization import (
    DEFAULT_LANGUAGE,
    SupportedLanguage,
    get_tool_display_name,
)

logger = structlog.get_logger()


class ToolExecutionCallback(AsyncCallbackHandler):
    """
    Async callback handler for streaming tool execution events to SSE queue.

    Lifecycle:
    1. on_tool_start: Tool begins → push tool_start event to queue
    2. on_tool_end: Tool succeeds → push tool_end event with truncated output
    3. on_tool_error: Tool fails → push tool_error event with error message

    Events are consumed by chat.py streaming endpoint and sent to frontend
    as Server-Sent Events for real-time UI updates.
    """

    def __init__(
        self,
        event_queue: asyncio.Queue[typing.Any],
        language: SupportedLanguage = DEFAULT_LANGUAGE,
    ):
        """
        Initialize callback handler with event queue.

        Args:
            event_queue: asyncio.Queue to push tool events for SSE streaming
            language: Language for tool display names
        """
        super().__init__()
        self.event_queue = event_queue
        self.language = language
        self.active_tools: dict[UUID, dict[str, Any]] = (
            {}
        )  # run_id -> {name, start_time, inputs}

        logger.info("ToolExecutionCallback initialized", language=language)

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
        """
        Called when tool execution begins.

        Pushes tool_start event to queue with tool name, inputs, and metadata.

        Args:
            serialized: Tool metadata (contains name, description)
            input_str: String representation of tool input
            run_id: Unique ID for this tool execution
            inputs: Structured tool input parameters
            **kwargs: Additional metadata
        """
        tool_name = serialized.get("name", "unknown_tool")
        start_time = utcnow()

        # Store active tool metadata
        self.active_tools[run_id] = {
            "name": tool_name,
            "start_time": start_time,
            "inputs": inputs or {},
        }

        # Map tool names to display metadata (icon, title)
        tool_metadata = self._get_tool_metadata(tool_name, inputs or {})

        # Push event to SSE queue
        event = {
            "type": "tool_start",
            "tool_name": tool_name,
            "display_name": tool_metadata["display_name"],
            "icon": tool_metadata["icon"],
            "inputs": inputs or {},
            "symbol": tool_metadata.get("symbol"),
            "run_id": str(run_id),
            "timestamp": start_time.isoformat(),
        }

        await self.event_queue.put(event)

        logger.info(
            "Tool execution started",
            tool_name=tool_name,
            run_id=str(run_id),
            inputs=inputs,
        )

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Called when tool execution completes successfully.

        Pushes tool_end event to queue with truncated output and duration.

        Args:
            output: Tool output (can be str, dict, or any serializable type)
            run_id: Unique ID for this tool execution
            **kwargs: Additional metadata
        """
        tool_info = self.active_tools.get(run_id, {})
        tool_name = tool_info.get("name", "unknown_tool")
        start_time = tool_info.get("start_time", utcnow())

        # Calculate duration
        end_time = utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Truncate output for SSE (prevent huge payloads)
        output_str = str(output)
        truncated_output = (
            output_str[:500] + "..." if len(output_str) > 500 else output_str
        )

        # Push event to SSE queue
        event = {
            "type": "tool_end",
            "tool_name": tool_name,
            "output": truncated_output,
            "duration_ms": duration_ms,
            "run_id": str(run_id),
            "status": "success",
            "timestamp": end_time.isoformat(),
        }

        await self.event_queue.put(event)

        # Clean up active tool tracking
        self.active_tools.pop(run_id, None)

        logger.info(
            "Tool execution completed",
            tool_name=tool_name,
            run_id=str(run_id),
            duration_ms=duration_ms,
            output_length=len(output_str),
        )

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Called when tool execution fails with error.

        Pushes tool_error event to queue with error message.

        Args:
            error: Exception raised during tool execution
            run_id: Unique ID for this tool execution
            **kwargs: Additional metadata
        """
        tool_info = self.active_tools.get(run_id, {})
        tool_name = tool_info.get("name", "unknown_tool")
        start_time = tool_info.get("start_time", utcnow())

        # Calculate duration
        end_time = utcnow()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Push event to SSE queue
        event = {
            "type": "tool_error",
            "tool_name": tool_name,
            "error": str(error),
            "duration_ms": duration_ms,
            "run_id": str(run_id),
            "status": "error",
            "timestamp": end_time.isoformat(),
        }

        await self.event_queue.put(event)

        # Clean up active tool tracking
        self.active_tools.pop(run_id, None)

        logger.error(
            "Tool execution failed",
            tool_name=tool_name,
            run_id=str(run_id),
            error=str(error),
            duration_ms=duration_ms,
        )

    def _get_tool_metadata(
        self, tool_name: str, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Map tool name to display metadata (icon, title, symbol).

        Args:
            tool_name: Internal tool name (e.g., "get_company_overview")
            inputs: Tool input parameters (may contain symbol)

        Returns:
            Dict with display_name, icon, and optional symbol
        """
        # Extract symbol from inputs if available
        symbol = inputs.get("symbol") or inputs.get("ticker")

        # Tool icon mapping (icons are universal, no translation needed)
        icon_map = {
            "search_ticker": "🔍",
            "get_company_overview": "🏢",
            "get_news_sentiment": "📰",
            "get_financial_statements": "📊",
            "get_market_movers": "📈",
            "fibonacci_analysis_tool": "📐",
            "stochastic_analysis_tool": "📉",
            "get_historical_prices": "📅",
            "get_stock_price": "💹",
            "get_earnings": "💰",
            "get_cash_flow": "💵",
            "get_balance_sheet": "📋",
        }

        # Get localized display name
        display_name = get_tool_display_name(tool_name, self.language)
        icon = icon_map.get(tool_name, "🔧")

        metadata = {
            "display_name": display_name,
            "icon": icon,
        }

        # Add symbol if available
        if symbol:
            metadata["symbol"] = str(symbol).upper()

        return metadata
