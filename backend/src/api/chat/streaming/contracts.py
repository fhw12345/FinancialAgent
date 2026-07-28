"""Shared chat streaming lifecycle contracts."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ....models.agent_run import ExecutionMode


@dataclass(frozen=True)
class ChatCompletion:
    content: str
    execution_mode: ExecutionMode
    agent_type: str
    llm_title: str | None = None
    update_final_title: bool = False
    model: str | None = None
    trace_id: str | None = None
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int | None = None
    raw_data: dict[str, Any] | None = None
    latency_metrics: dict[str, Any] = field(default_factory=dict)
    done_data: dict[str, Any] = field(default_factory=dict)
    after_durable: Callable[[], Awaitable[None]] | None = None


@dataclass(frozen=True)
class ChatFailure:
    execution_mode: ExecutionMode
    error_code: str
    error_message: str
    client_message: str
    include_error_code: bool = True


@dataclass(frozen=True)
class ChatClarification:
    execution_mode: ExecutionMode
    agent_type: str
    content: str
    payload: dict[str, Any]
