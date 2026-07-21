"""Versioned event envelope for unified agent SSE streams."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from ...core.utils.date_utils import utcnow


class AgentEventEnvelope(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str = Field(min_length=1)
    stream_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    type: str = Field(min_length=1)
    timestamp: datetime
    payload: dict[str, Any]


class AgentEventSequencer:
    """Assign one contiguous sequence across a complete agent stream."""

    def __init__(self, run_id: str, *, stream_id: str | None = None) -> None:
        if not run_id:
            raise ValueError("run_id is required")
        self.run_id = run_id
        self.stream_id = stream_id or run_id
        self._sequence = 0

    def wrap(self, legacy_event: dict[str, Any]) -> AgentEventEnvelope:
        self._sequence += 1
        return AgentEventEnvelope(
            run_id=self.run_id,
            stream_id=self.stream_id,
            sequence=self._sequence,
            type=canonical_event_type(legacy_event),
            timestamp=utcnow(),
            payload=legacy_event,
        )

    def format_sse(self, legacy_event: dict[str, Any]) -> str:
        envelope = self.wrap(legacy_event)
        return f"data: {json.dumps(envelope.model_dump(mode='json'))}\n\n"


def canonical_event_type(event: dict[str, Any]) -> str:
    legacy_type = str(event.get("type") or "")
    if legacy_type == "run_state":
        return {
            "running": "run_started",
            "completed": "run_completed",
            "failed": "run_failed",
            "cancelled": "run_cancelled",
            "waiting_for_input": "run_waiting_for_input",
            "pending": "run_started",
        }.get(str(event.get("status")), "run_state")
    if legacy_type == "route_selected":
        return "policy_selected"
    if legacy_type == "thinking":
        return "model_started"
    if legacy_type == "chunk":
        return "response_chunk"
    if legacy_type in {"tool_start", "deep_tool_start"}:
        return "tool_started"
    if legacy_type in {"tool_end", "tool_error", "deep_tool_end"}:
        return "tool_completed"
    if legacy_type in {
        "deep_start",
        "deep_subagent_start",
        "deep_debate_start",
        "deep_rebuttal_start",
        "deep_synthesis_start",
    }:
        return "research_stage_started"
    if legacy_type in {
        "deep_subagent_result",
        "deep_debate_round",
        "deep_rebuttal_result",
        "deep_verdict",
    }:
        return "research_stage_completed"
    if legacy_type == "done":
        return "stream_completed"
    return legacy_type


def parse_sse_data(chunk: Any) -> list[dict[str, Any]]:
    """Parse one or more complete internal SSE data blocks."""
    if isinstance(chunk, bytes):
        text = chunk.decode("utf-8")
    elif isinstance(chunk, str):
        text = chunk
    else:
        raise TypeError(f"Unsupported SSE chunk type: {type(chunk).__name__}")

    events: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        if not block.startswith("data: "):
            raise ValueError("Internal SSE block must start with 'data: '")
        decoded = json.loads(block[6:])
        if not isinstance(decoded, dict):
            raise ValueError("Internal SSE data must be a JSON object")
        events.append(decoded)
    return events
