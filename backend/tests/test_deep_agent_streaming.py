"""Streaming regression tests for Deep Agent symbol clarification."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.api.chat.streaming.deep_agent import stream_with_deep_agent
from src.api.chat.streaming.durable_tasks import await_task_through_cancellation
from src.api.schemas.chat_models import ChatRequest
from src.core.utils.date_utils import utcnow
from src.models.message import Message
from src.models.run_identity import message_id_for_run
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
async def test_shielded_persistence_finishes_after_cancellation():
    started = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()

    async def persist() -> None:
        started.set()
        await release.wait()
        completed.set()

    persistence_task = asyncio.create_task(persist())
    waiter = asyncio.create_task(await_task_through_cancellation(persistence_task))
    await started.wait()
    waiter.cancel()
    release.set()

    _, cancelled = await waiter
    assert cancelled is True
    assert completed.is_set()


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

    persistence_order: list[str] = []

    async def upsert_run_message(**kwargs):
        persistence_order.append("message")
        return None

    chat_service.upsert_run_message.side_effect = upsert_run_message

    async def analyze(on_event, **kwargs):
        on_event(
            {
                "type": "prompt_used",
                "prompt_id": "deep-debater",
                "version": "deep-debater@3",
            }
        )
        return {
            "final_answer": "TSLA analysis",
            "tool_executions": 0,
            "trace_id": "deep_test",
            "input_tokens": 10,
            "output_tokens": 5,
            "research_context": {
                "confirmed_symbol": "TSLA",
                "investment_horizon": "6 months",
            },
            "prompt_versions": {"deep-verdict": "deep-verdict@2"},
            "verdict": {
                "report_markdown": "**Action**: BUY\n\nTSLA analysis",
                "action": "BUY",
                "conviction": "HIGH",
                "risk_level": "MODERATE",
                "key_insight": "Structured verdict.",
                "concern_assessments": [],
            },
        }

    async def persist_verdict_decision(**kwargs):
        persistence_order.append("signal")

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
        ainvoke=AsyncMock(side_effect=analyze),
        persist_verdict_decision=AsyncMock(side_effect=persist_verdict_decision),
    )
    run_service = AsyncMock()

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
        run_id="run_3",
        run_service=run_service,
    )

    output = ""
    async for chunk in response.body_iterator:
        output += chunk.decode() if isinstance(chunk, bytes) else chunk

    events = parse_events(output)
    assert any(
        event["type"] == "chunk" and event["content"] == "TSLA analysis"
        for event in events
    )
    assert any(
        event["type"] == "response_stream_mode" and event["mode"] == "buffered"
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
    recorded_versions = {
        key: value
        for call in run_service.record_prompt_versions.await_args_list
        for key, value in call.args[1].items()
    }
    assert recorded_versions == {
        "deep-debater": "deep-debater@3",
        "deep-verdict": "deep-verdict@2",
    }
    agent.persist_verdict_decision.assert_awaited_once_with(
        symbol="TSLA",
        verdict={
            "report_markdown": "**Action**: BUY\n\nTSLA analysis",
            "action": "BUY",
            "conviction": "HIGH",
            "risk_level": "MODERATE",
            "key_insight": "Structured verdict.",
            "concern_assessments": [],
        },
        chat_id="chat_3",
        run_id="run_3",
        message_id=message_id_for_run("run_3"),
    )
    assert persistence_order == ["message", "signal"]


@pytest.mark.asyncio
async def test_failure_persists_request_local_prompt_versions():
    chat_service = AsyncMock()
    chat_service.get_chat.return_value = SimpleNamespace(chat_id="chat_failure")
    chat_service.add_message.return_value = current_user_message(
        "chat_failure",
        "Deeply analyze AAPL",
    )
    chat_service.get_chat_messages.return_value = []

    async def fail(on_event, **kwargs):
        on_event(
            {
                "type": "prompt_used",
                "prompt_id": "deep-rebuttal",
                "version": "deep-rebuttal@2",
            }
        )
        raise ValueError("invalid rebuttal output")

    agent = SimpleNamespace(
        resolve_symbol=AsyncMock(
            return_value=SymbolResolution(
                status="resolved",
                source="explicit_ticker",
                reason_code="resolved_explicit_ticker",
                symbol="AAPL",
                confidence=1.0,
            )
        ),
        ainvoke=AsyncMock(side_effect=fail),
    )
    run_service = AsyncMock()
    response = await stream_with_deep_agent(
        request=ChatRequest(
            message="Deeply analyze AAPL",
            chat_id="chat_failure",
            agent_version="v4-deep",
            language="en",
        ),
        user_id="local",
        chat_service=chat_service,
        agent=agent,
        context_manager=context_manager(),
        message_repo=AsyncMock(),
        run_id="run_failure",
        run_service=run_service,
    )

    async for _ in response.body_iterator:
        pass

    run_service.record_prompt_versions.assert_any_await(
        "run_failure",
        {"deep-rebuttal": "deep-rebuttal@2"},
    )


@pytest.mark.asyncio
async def test_cancellation_persists_request_local_prompt_versions():
    chat_service = AsyncMock()
    chat_service.get_chat.return_value = SimpleNamespace(chat_id="chat_cancel")
    chat_service.add_message.return_value = current_user_message(
        "chat_cancel",
        "Deeply analyze AAPL",
    )
    chat_service.get_chat_messages.return_value = []

    async def wait_for_cancel(on_event, **kwargs):
        on_event(
            {
                "type": "prompt_used",
                "prompt_id": "deep-debater",
                "version": "deep-debater@3",
            }
        )
        await asyncio.Event().wait()

    agent = SimpleNamespace(
        resolve_symbol=AsyncMock(
            return_value=SymbolResolution(
                status="resolved",
                source="explicit_ticker",
                reason_code="resolved_explicit_ticker",
                symbol="AAPL",
                confidence=1.0,
            )
        ),
        ainvoke=AsyncMock(side_effect=wait_for_cancel),
    )
    run_service = AsyncMock()
    client_request = SimpleNamespace(
        is_disconnected=AsyncMock(side_effect=[False, True])
    )
    response = await stream_with_deep_agent(
        request=ChatRequest(
            message="Deeply analyze AAPL",
            chat_id="chat_cancel",
            agent_version="v4-deep",
            language="en",
        ),
        user_id="local",
        chat_service=chat_service,
        agent=agent,
        context_manager=context_manager(),
        message_repo=AsyncMock(),
        client_request=client_request,
        run_id="run_cancel",
        run_service=run_service,
    )

    async for _ in response.body_iterator:
        pass

    run_service.record_prompt_versions.assert_any_await(
        "run_cancel",
        {"deep-debater": "deep-debater@3"},
    )
