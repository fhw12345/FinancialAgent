"""
Shared helper functions for streaming responses.

This module contains utility functions for SSE event formatting
and error handling used by both simple and react agent streams.

Story 1.4: Added streaming latency optimization events:
- create_thinking_event: Immediate feedback for eager streaming (TTFT optimization)
- create_latency_event: Streaming latency metrics for Langfuse observability
"""

import json
from datetime import datetime
from typing import Any


def format_sse_event(event_data: dict[str, Any]) -> str:
    """
    Format a dictionary as an SSE (Server-Sent Events) event.

    Args:
        event_data: Dictionary containing event data

    Returns:
        SSE-formatted string with 'data: ' prefix and double newline
    """
    return f"data: {json.dumps(event_data)}\n\n"


def create_error_event(error_message: str, error_code: str) -> str:
    """
    Create a formatted SSE error event.

    Args:
        error_message: Human-readable error message
        error_code: Error code identifier (e.g., 'INSUFFICIENT_CREDITS')

    Returns:
        SSE-formatted error event string
    """
    error_data = {
        "error": error_message,
        "error_code": error_code,
        "type": "error",
    }
    return format_sse_event(error_data)


def create_done_event(chat_id: str, **extra_data: Any) -> str:
    """
    Create a formatted SSE completion event.

    Args:
        chat_id: Chat identifier
        **extra_data: Additional data to include in the event

    Returns:
        SSE-formatted completion event string
    """
    event_data = {"type": "done", "chat_id": chat_id, **extra_data}
    return format_sse_event(event_data)


def create_chunk_event(content: str) -> str:
    """
    Create a formatted SSE chunk event for streaming text.

    Args:
        content: Text chunk to stream

    Returns:
        SSE-formatted chunk event string
    """
    chunk_data = {"type": "chunk", "content": content}
    return format_sse_event(chunk_data)


def create_thinking_event(stage: str, chat_id: str | None = None) -> str:
    """
    Create a formatted SSE thinking event for eager streaming (Story 1.4).

    This event is sent immediately after request validation to reduce
    perceived latency (time-to-first-visible-feedback).

    Args:
        stage: Current processing stage (e.g., "initializing", "analyzing", "reasoning")
        chat_id: Optional chat identifier

    Returns:
        SSE-formatted thinking event string
    """
    event_data: dict[str, Any] = {
        "type": "thinking",
        "stage": stage,
        "timestamp": datetime.utcnow().isoformat(),
    }
    if chat_id:
        event_data["chat_id"] = chat_id
    return format_sse_event(event_data)


def create_latency_event(
    stage: str,
    duration_ms: int,
    trace_id: str | None = None,
    **extra_metrics: Any,
) -> str:
    """
    Create a formatted SSE latency metrics event for observability (Story 1.4).

    Tracks timing at different stages of the streaming pipeline:
    - request_received: When endpoint receives request
    - credit_checked: After credit validation
    - context_prepared: After history/compaction
    - agent_started: When agent invocation begins
    - first_tool: When first tool event is emitted
    - first_chunk: Time-to-first-token (TTFT)
    - stream_complete: Total duration

    Args:
        stage: Processing stage identifier
        duration_ms: Duration since request start in milliseconds
        trace_id: Optional Langfuse trace ID for correlation
        **extra_metrics: Additional metrics to include

    Returns:
        SSE-formatted latency event string
    """
    event_data: dict[str, Any] = {
        "type": "latency",
        "stage": stage,
        "duration_ms": duration_ms,
        "timestamp": datetime.utcnow().isoformat(),
    }
    if trace_id:
        event_data["trace_id"] = trace_id
    if extra_metrics:
        event_data["metrics"] = extra_metrics
    return format_sse_event(event_data)
