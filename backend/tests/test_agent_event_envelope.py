"""Tests for the unified sequenced agent event envelope."""

import json

import pytest
from pydantic import ValidationError

from src.api.schemas.agent_events import (
    AgentEventEnvelope,
    AgentEventSequencer,
    canonical_event_type,
    parse_sse_data,
)
from src.core.utils.date_utils import utcnow


def test_envelope_requires_run_id_and_positive_sequence():
    with pytest.raises(ValidationError):
        AgentEventEnvelope(
            run_id="",
            sequence=0,
            type="run_started",
            timestamp=utcnow(),
            payload={},
        )


def test_sequencer_wraps_events_with_contiguous_sequence():
    sequencer = AgentEventSequencer("run_1")

    first = sequencer.wrap({"type": "run_state", "status": "running"})
    second = sequencer.wrap({"type": "chunk", "content": "hello"})

    assert first.sequence == 1
    assert first.type == "run_started"
    assert second.sequence == 2
    assert second.type == "response_chunk"
    assert second.payload == {"type": "chunk", "content": "hello"}


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ({"type": "route_selected"}, "policy_selected"),
        ({"type": "tool_start"}, "tool_started"),
        ({"type": "tool_error"}, "tool_completed"),
        ({"type": "deep_subagent_start"}, "research_stage_started"),
        ({"type": "deep_verdict"}, "research_stage_completed"),
        ({"type": "run_state", "status": "completed"}, "run_completed"),
        ({"type": "done"}, "stream_completed"),
    ],
)
def test_canonical_event_mapping(event, expected):
    assert canonical_event_type(event) == expected


def test_parse_multiple_sse_blocks_and_format_envelope():
    events = parse_sse_data(
        'data: {"type":"chunk","content":"a"}\n\n'
        'data: {"type":"done","chat_id":"chat_1"}\n\n'
    )
    output = AgentEventSequencer("run_1").format_sse(events[0])
    envelope = json.loads(output.removeprefix("data: ").strip())

    assert [event["type"] for event in events] == ["chunk", "done"]
    assert envelope["schema_version"] == "1.0"
    assert envelope["run_id"] == "run_1"
    assert envelope["payload"]["content"] == "a"


def test_parse_rejects_unsequenced_internal_data():
    with pytest.raises(ValueError, match="must start"):
        parse_sse_data('event: chunk\ndata: {"type":"chunk"}\n\n')
