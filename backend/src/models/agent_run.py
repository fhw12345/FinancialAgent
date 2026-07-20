"""Shared durable execution model for chat and portfolio workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AgentRunStatus = Literal[
    "pending",
    "running",
    "waiting_for_input",
    "completed",
    "failed",
    "cancelled",
]
ExecutionMode = Literal["instant", "agentic", "research", "portfolio"]


class AgentRun(BaseModel):
    """One durable execution record across all agent workflows."""

    run_id: str
    chat_id: str | None = None
    request_id: str | None = None
    portfolio_key: str | None = None
    active_portfolio_key: str | None = None
    execution_mode: ExecutionMode | None = None
    requested_policy: str
    selected_policy: str | None = None
    policy_version: str
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    model_routes: dict[str, str] = Field(default_factory=dict)
    status: AgentRunStatus
    started_at: datetime
    finished_at: datetime | None = None
    lease_expires_at: datetime | None = None
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float | None = None
    data_sources: list[str] = Field(default_factory=list)
    data_freshness: dict[str, str] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    cancel_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


TERMINAL_RUN_STATUSES: frozenset[AgentRunStatus] = frozenset(
    {"completed", "failed", "cancelled"}
)

ALLOWED_RUN_TRANSITIONS: dict[AgentRunStatus, frozenset[AgentRunStatus]] = {
    "pending": frozenset({"running", "waiting_for_input", "failed", "cancelled"}),
    "running": frozenset({"waiting_for_input", "completed", "failed", "cancelled"}),
    "waiting_for_input": frozenset({"running", "completed", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}
