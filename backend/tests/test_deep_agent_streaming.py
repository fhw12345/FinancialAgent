"""Streaming regression tests for Deep Agent symbol clarification."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.api.chat.streaming.deep_agent import stream_with_deep_agent
from src.api.schemas.chat_models import ChatRequest
from src.core.utils.date_utils import utcnow
from src.models.message import Message
from src.models.symbol_resolution import SymbolCandidate, SymbolResolution


def parse_events(output: str) -> list[dict]:
    events = []
    for block in output.split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[6:]))
    return events


def current_user_message(chat_id: str, content: str) -> Message:
    return Message(
        message_id=f"msg_{chat_id}",
        chat_id=chat_id,
        role="user",
        content=content,
        source="user",
        timestamp=utcnow(),
    )


def context_manager() -> Mock:
    manager = Mock()
    manager.calculate_context_tokens.return_value = 0
    manager.estimate_tokens.return_value = 1
    return manager


@pytest.mark.asyncio
async def test_unresolved_symbol_is_persisted_and_stops_before_research():
    chat_service = AsyncMock()
    chat_service.get_chat.return_value = SimpleNamespace(chat_id="chat_1")
    chat_service.add_message.return_value = current_user_message(
        "chat_1",
        "请完整分析我昨天看到的那家公司",
    )
    chat_service.get_chat_messages.return_value = []

    agent = SimpleNamespace(
        resolve_symbol=AsyncMock(
            return_value=SymbolResolution(
                status="unresolved",
                source="llm_assisted",
                reason_code="symbol_missing",
            )
        ),
        ainvoke=AsyncMock(),
    )

    response = await stream_with_deep_agent(
        request=ChatRequest(
            message="请完整分析我昨天看到的那家公司",
            chat_id="chat_1",
            agent_version="v4-deep",
            language="zh-CN",
        ),
        user_id="local",
        chat_service=chat_service,
        agent=agent,
        context_manager=context_manager(),
        message_repo=AsyncMock(),
        route_metadata={
            "type": "route_selected",
            "flow": "v4-deep",
            "source": "rule",
            "reason_code": "deep_financial_request",
        },
    )

    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    output = "".join(chunks)
    events = parse_events(output)

    clarification = next(
        event for event in events if event["type"] == "clarification_required"
    )
    assert clarification["reason_code"] == "symbol_missing"
    assert clarification["candidates"] == []
    assert any(event["type"] == "done" for event in events)
    assert all(not event["type"].startswith("deep_") for event in events)
    agent.ainvoke.assert_not_awaited()

    assistant_call = next(
        call
        for call in chat_service.add_message.await_args_list
        if call.kwargs["role"] == "assistant"
    )
    raw_data = assistant_call.kwargs["metadata"]["raw_data"]
    assert raw_data["clarification_required"]["reason_code"] == "symbol_missing"
    assert raw_data["route_selected"]["flow"] == "v4-deep"


@pytest.mark.asyncio
async def test_ambiguous_symbol_streams_validated_candidates():
    chat_service = AsyncMock()
    chat_service.get_chat.return_value = SimpleNamespace(chat_id="chat_2")
    chat_service.add_message.return_value = current_user_message(
        "chat_2",
        "Deeply analyze Alpha",
    )
    chat_service.get_chat_messages.return_value = []
    agent = SimpleNamespace(
        resolve_symbol=AsyncMock(
            return_value=SymbolResolution(
                status="ambiguous",
                source="llm_assisted",
                reason_code="ambiguous_symbol",
                candidates=[
                    SymbolCandidate(
                        symbol="AAA",
                        name="Alpha A",
                        confidence=0.9,
                    ),
                    SymbolCandidate(
                        symbol="AAB",
                        name="Alpha B",
                        confidence=0.85,
                    ),
                ],
            )
        ),
        ainvoke=AsyncMock(),
    )

    response = await stream_with_deep_agent(
        request=ChatRequest(
            message="Deeply analyze Alpha",
            chat_id="chat_2",
            agent_version="v4-deep",
            language="en",
        ),
        user_id="local",
        chat_service=chat_service,
        agent=agent,
        context_manager=context_manager(),
        message_repo=AsyncMock(),
    )

    output = ""
    async for chunk in response.body_iterator:
        output += chunk.decode() if isinstance(chunk, bytes) else chunk
    events = parse_events(output)
    clarification = next(
        event for event in events if event["type"] == "clarification_required"
    )

    assert [item["symbol"] for item in clarification["candidates"]] == ["AAA", "AAB"]
    agent.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolved_symbol_continues_to_deep_agent():
    chat_service = AsyncMock()
    chat_service.get_chat.return_value = SimpleNamespace(chat_id="chat_3")
    chat_service.add_message.return_value = current_user_message(
        "chat_3",
        "Deeply analyze TSLA",
    )
    chat_service.get_chat_messages.return_value = []
    agent = SimpleNamespace(
        resolve_symbol=AsyncMock(
            return_value=SymbolResolution(
                status="resolved",
                source="explicit_ticker",
                reason_code="resolved_explicit_ticker",
                symbol="TSLA",
                company_name="Tesla",
                confidence=1.0,
                candidates=[
                    SymbolCandidate(
                        symbol="TSLA",
                        name="Tesla",
                        confidence=1.0,
                    )
                ],
            )
        ),
        ainvoke=AsyncMock(
            return_value={
                "final_answer": "TSLA analysis",
                "tool_executions": 0,
                "trace_id": "deep_test",
                "input_tokens": 10,
                "output_tokens": 5,
                "research_context": {
                    "confirmed_symbol": "TSLA",
                    "investment_horizon": "6 months",
                },
            }
        ),
    )

    response = await stream_with_deep_agent(
        request=ChatRequest(
            message="Deeply analyze TSLA",
            chat_id="chat_3",
            agent_version="v4-deep",
            language="en",
        ),
        user_id="local",
        chat_service=chat_service,
        agent=agent,
        context_manager=context_manager(),
        message_repo=AsyncMock(),
    )

    output = ""
    async for chunk in response.body_iterator:
        output += chunk.decode() if isinstance(chunk, bytes) else chunk

    events = parse_events(output)
    assert any(
        event["type"] == "chunk" and event["content"] == "TSLA analy"
        for event in events
    )
    assert all(event["type"] != "clarification_required" for event in events)
    agent.ainvoke.assert_awaited_once()
    assert agent.ainvoke.await_args.kwargs["resolved_symbol"] == "TSLA"
    resolve_kwargs = agent.resolve_symbol.await_args.kwargs
    assert "conversation_history" in resolve_kwargs
    assistant_call = chat_service.upsert_run_message.await_args
    metadata = assistant_call.kwargs["metadata"]
    assert metadata.raw_data["research_context"]["confirmed_symbol"] == "TSLA"
