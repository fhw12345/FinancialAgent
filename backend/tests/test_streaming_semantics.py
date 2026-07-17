"""Tests for honest model-token versus buffered response semantics."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.api.chat.streaming.deep_agent import stream_with_deep_agent
from src.api.chat.streaming.react_agent import stream_with_react_agent
from src.api.chat.streaming.simple_agent import stream_with_simple_agent
from src.api.schemas.chat_models import ChatRequest
from src.core.utils.date_utils import utcnow
from src.models.message import Message
from src.models.symbol_resolution import SymbolCandidate, SymbolResolution


def make_chat_service() -> AsyncMock:
    chat_service = AsyncMock()
    chat_service.get_chat.return_value = SimpleNamespace(
        chat_id="chat_stream",
        ui_state=None,
    )
    chat_service.add_message.return_value = Message(
        message_id="msg_current",
        chat_id="chat_stream",
        role="user",
        content="request",
        source="user",
        timestamp=utcnow(),
    )
    chat_service.get_chat_messages.return_value = []
    return chat_service


def make_context_manager() -> Mock:
    context_manager = Mock()
    context_manager.calculate_context_tokens.return_value = 0
    context_manager.estimate_tokens.return_value = 1
    return context_manager


async def collect_events(response) -> list[dict]:
    events: list[dict] = []
    async for raw in response.body_iterator:
        text = raw.decode() if isinstance(raw, bytes) else raw
        for block in text.split("\n\n"):
            if block.startswith("data: "):
                events.append(json.loads(block[6:]))
    return events


@pytest.mark.asyncio
async def test_direct_declares_real_model_token_stream():
    class StreamingAgent:
        async def stream_chat(self, **kwargs):
            yield "FIRST"
            yield "SECOND"

        def get_last_token_usage(self):
            return None

    response = await stream_with_simple_agent(
        request=ChatRequest(
            message="Explain P/E",
            chat_id="chat_stream",
            agent_version="v2",
            language="en",
        ),
        user_id="local",
        chat_service=make_chat_service(),
        agent=StreamingAgent(),  # type: ignore[arg-type]
        context_manager=make_context_manager(),
        message_repo=AsyncMock(),
    )

    events = await collect_events(response)

    assert {"type": "response_stream_mode", "mode": "model_tokens"} in events
    assert [event["content"] for event in events if event["type"] == "chunk"] == [
        "FIRST",
        "SECOND",
    ]
    stages = [event.get("stage") for event in events if event["type"] == "latency"]
    assert "first_model_token" in stages
    assert "first_chunk" not in stages


@pytest.mark.asyncio
async def test_react_declares_one_buffered_response_chunk():
    class BufferedReactAgent:
        async def ainvoke(self, **kwargs):
            return {
                "final_answer": "BUFFERED_REACT_RESPONSE",
                "tool_executions": 0,
                "trace_id": "react_buffered",
            }

    response = await stream_with_react_agent(
        request=ChatRequest(
            message="What is the AAPL price?",
            chat_id="chat_stream",
            agent_version="v3",
            language="en",
        ),
        user_id="local",
        chat_service=make_chat_service(),
        agent=BufferedReactAgent(),  # type: ignore[arg-type]
        context_manager=make_context_manager(),
        message_repo=AsyncMock(),
    )

    events = await collect_events(response)

    assert {"type": "response_stream_mode", "mode": "buffered"} in events
    chunks = [event["content"] for event in events if event["type"] == "chunk"]
    assert chunks == ["BUFFERED_REACT_RESPONSE"]
    stages = [event.get("stage") for event in events if event["type"] == "latency"]
    assert "first_response_chunk" in stages
    assert "first_chunk" not in stages


@pytest.mark.asyncio
async def test_deep_separates_progress_from_buffered_response():
    class BufferedDeepAdapter:
        async def resolve_symbol(self, **kwargs):
            candidate = SymbolCandidate(
                symbol="AAPL",
                name="Apple",
                confidence=1.0,
            )
            return SymbolResolution(
                status="resolved",
                source="explicit_ticker",
                reason_code="resolved_explicit_ticker",
                symbol="AAPL",
                company_name="Apple",
                confidence=1.0,
                candidates=[candidate],
            )

        async def ainvoke(self, **kwargs):
            kwargs["on_event"](
                {
                    "type": "deep_start",
                    "seq": 1,
                    "timestamp": utcnow().isoformat(),
                    "symbol": "AAPL",
                    "subagent_names": ["technical"],
                    "enable_debate": False,
                }
            )
            return {
                "final_answer": "BUFFERED_DEEP_RESPONSE",
                "tool_executions": 0,
                "trace_id": "deep_buffered",
                "research_context": {},
            }

    response = await stream_with_deep_agent(
        request=ChatRequest(
            message="Deeply analyze AAPL",
            chat_id="chat_stream",
            agent_version="v4-deep",
            language="en",
        ),
        user_id="local",
        chat_service=make_chat_service(),
        agent=BufferedDeepAdapter(),
        context_manager=make_context_manager(),
        message_repo=AsyncMock(),
    )

    events = await collect_events(response)

    assert {"type": "response_stream_mode", "mode": "buffered"} in events
    assert any(event["type"] == "deep_start" for event in events)
    chunks = [event["content"] for event in events if event["type"] == "chunk"]
    assert chunks == ["BUFFERED_DEEP_RESPONSE"]
    stages = [event.get("stage") for event in events if event["type"] == "latency"]
    assert "first_progress_event" in stages
    assert "first_response_chunk" in stages
    assert "first_event" not in stages
    assert "first_chunk" not in stages
