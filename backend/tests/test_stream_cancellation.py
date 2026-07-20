"""Cancellation propagation tests for direct, ReAct, and Deep streams."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.api.chat.streaming.cancellation import persist_cancelled_run
from src.api.chat.streaming.deep_agent import stream_with_deep_agent
from src.api.chat.streaming.handlers import chat_stream_unified
from src.api.chat.streaming.react_agent import stream_with_react_agent
from src.api.chat.streaming.simple_agent import stream_with_simple_agent
from src.api.schemas.chat_models import ChatRequest
from src.core.utils.date_utils import utcnow
from src.models.agent_run import AgentRun
from src.models.message import Message, MessageMetadata
from src.models.symbol_resolution import SymbolCandidate, SymbolResolution


class DisconnectAfterPoll:
    """Report connected once so the active task can start, then disconnect."""

    def __init__(self) -> None:
        self.calls = 0

    async def is_disconnected(self) -> bool:
        self.calls += 1
        return self.calls >= 2


class DisconnectOnCall:
    def __init__(self, target_call: int) -> None:
        self.target_call = target_call
        self.calls = 0

    async def is_disconnected(self) -> bool:
        self.calls += 1
        return self.calls >= self.target_call


def make_chat_service() -> AsyncMock:
    chat_service = AsyncMock()
    chat_service.get_chat.return_value = SimpleNamespace(
        chat_id="chat_cancel",
        ui_state=None,
    )
    current_message = Message(
        message_id="msg_current",
        chat_id="chat_cancel",
        role="user",
        content="Analyze AAPL",
        source="user",
        timestamp=utcnow(),
    )
    chat_service.add_message.return_value = current_message
    chat_service.get_chat_messages.return_value = []
    return chat_service


def make_context_manager() -> Mock:
    context_manager = Mock()
    context_manager.calculate_context_tokens.return_value = 0
    context_manager.estimate_tokens.return_value = 1
    return context_manager


def cancelled_metadata(chat_service: AsyncMock) -> MessageMetadata:
    call = chat_service.upsert_run_message.await_args
    metadata = call.kwargs["metadata"]
    assert isinstance(metadata, MessageMetadata)
    return metadata


@pytest.mark.asyncio
async def test_cancellation_without_chat_still_transitions_durable_run():
    chat_service = make_chat_service()
    run_service = AsyncMock()
    run_service.cancel.return_value = AgentRun(
        run_id="run_without_chat",
        requested_policy="auto",
        policy_version="auto-router-v1",
        status="cancelled",
        started_at=utcnow(),
        finished_at=utcnow(),
    )

    await persist_cancelled_run(
        chat_service=chat_service,
        chat_id=None,
        user_id="local",
        run_id="run_without_chat",
        language="en",
        agent_type="simple_chat",
        route_metadata=None,
        run_service=run_service,
    )

    run_service.cancel.assert_awaited_once_with(
        "run_without_chat",
        cancel_reason="client_cancelled",
    )
    chat_service.upsert_run_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_simple_stream_cancels_provider_and_persists_status():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class SlowChatAgent:
        async def stream_chat(self, messages, max_tokens=3000, language="zh-CN"):
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                cancelled.set()
                raise
            yield "late"

        def get_last_token_usage(self):
            return None

    chat_service = make_chat_service()
    response = await stream_with_simple_agent(
        request=ChatRequest(
            message="Explain valuation",
            chat_id="chat_cancel",
            agent_version="v2",
            language="en",
        ),
        user_id="local",
        chat_service=chat_service,
        agent=SlowChatAgent(),  # type: ignore[arg-type]
        context_manager=make_context_manager(),
        message_repo=AsyncMock(),
        client_request=DisconnectAfterPoll(),  # type: ignore[arg-type]
    )

    async for _ in response.body_iterator:
        pass

    assert started.is_set()
    assert cancelled.is_set()
    metadata = cancelled_metadata(chat_service)
    assert metadata.run_status == "cancelled"
    assert metadata.cancelled_at is not None
    assert chat_service.upsert_run_message.await_args.kwargs["content"] == (
        "Request cancelled."
    )


@pytest.mark.asyncio
async def test_disconnect_during_routing_cancels_and_persists_request():
    routing_started = asyncio.Event()
    routing_cancelled = asyncio.Event()

    class SlowRouter:
        async def select(self, **kwargs):
            routing_started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                routing_cancelled.set()
                raise

    chat_service = make_chat_service()
    run_service = AsyncMock()
    run_service.create_chat_run.return_value = AgentRun(
        run_id="run_routing",
        requested_policy="auto",
        policy_version="auto-router-v1",
        status="pending",
        started_at=utcnow(),
    )
    response = await chat_stream_unified(
        request=ChatRequest(
            message="Analyze this company",
            chat_id="chat_cancel",
            agent_version="auto",
            language="en",
        ),
        http_request=DisconnectAfterPoll(),  # type: ignore[arg-type]
        chat_service=chat_service,
        simple_agent=Mock(),
        react_agent=Mock(),
        deep_agent=Mock(),
        context_manager=make_context_manager(),
        message_repo=AsyncMock(),
        flow_router=SlowRouter(),  # type: ignore[arg-type]
        run_service=run_service,
        x_debug=None,
    )

    async for _ in response.body_iterator:
        pass

    assert routing_started.is_set()
    assert routing_cancelled.is_set()
    assert chat_service.add_message.await_args.kwargs["role"] == "user"
    assert cancelled_metadata(chat_service).run_status == "cancelled"
    run_service.cancel.assert_awaited_once()


@pytest.mark.asyncio
async def test_closing_unified_stream_after_agent_starts_persists_cancellation():
    class IdleSimpleAgent:
        async def stream_chat(self, messages, max_tokens=3000, language="zh-CN"):
            await asyncio.sleep(30)
            yield "late"

        def get_last_token_usage(self):
            return None

    class SimpleRouter:
        async def select(self, **kwargs):
            return SimpleNamespace(
                flow="v2",
                source="rule",
                reason_code="concept_explanation",
                as_metadata=lambda: {
                    "flow": "v2",
                    "source": "rule",
                    "reason_code": "concept_explanation",
                },
                as_event=lambda: {
                    "type": "route_selected",
                    "flow": "v2",
                    "source": "rule",
                    "reason_code": "concept_explanation",
                },
            )

    chat_service = make_chat_service()
    run_service = AsyncMock()
    created_run = AgentRun(
        run_id="run_stream_close",
        requested_policy="auto",
        policy_version="auto-router-v1",
        status="pending",
        started_at=utcnow(),
    )
    run_service.create_chat_run.return_value = created_run
    run_service.mark_running.return_value = created_run.model_copy(
        update={
            "selected_policy": "v2",
            "execution_mode": "instant",
            "status": "running",
        }
    )
    response = await chat_stream_unified(
        request=ChatRequest(
            message="Explain valuation",
            chat_id="chat_cancel",
            agent_version="auto",
            language="en",
        ),
        http_request=DisconnectOnCall(100),  # type: ignore[arg-type]
        chat_service=chat_service,
        simple_agent=IdleSimpleAgent(),  # type: ignore[arg-type]
        react_agent=Mock(),
        deep_agent=Mock(),
        context_manager=make_context_manager(),
        message_repo=AsyncMock(),
        flow_router=SimpleRouter(),  # type: ignore[arg-type]
        run_service=run_service,
        x_debug=None,
    )

    iterator = response.body_iterator
    await anext(iterator)
    await anext(iterator)
    await anext(iterator)
    await iterator.aclose()

    run_service.cancel.assert_awaited_once_with(
        "run_stream_close",
        cancel_reason="client_cancelled",
    )
    assert cancelled_metadata(chat_service).run_status == "cancelled"


@pytest.mark.asyncio
async def test_react_stream_cancels_agent_and_awaited_child():
    agent_started = asyncio.Event()
    agent_cancelled = asyncio.Event()
    child_cancelled = asyncio.Event()

    async def child_work() -> None:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            child_cancelled.set()
            raise

    class SlowReactAgent:
        async def ainvoke(self, **kwargs):
            agent_started.set()
            child = asyncio.create_task(child_work())
            try:
                await child
            except asyncio.CancelledError:
                agent_cancelled.set()
                if not child.done():
                    child.cancel()
                try:
                    await child
                except asyncio.CancelledError:
                    pass
                raise

    chat_service = make_chat_service()
    response = await stream_with_react_agent(
        request=ChatRequest(
            message="What is the current AAPL price?",
            chat_id="chat_cancel",
            agent_version="v3",
            language="en",
        ),
        user_id="local",
        chat_service=chat_service,
        agent=SlowReactAgent(),  # type: ignore[arg-type]
        context_manager=make_context_manager(),
        message_repo=AsyncMock(),
        client_request=DisconnectAfterPoll(),  # type: ignore[arg-type]
    )

    async for _ in response.body_iterator:
        pass

    assert agent_started.is_set()
    assert agent_cancelled.is_set()
    assert child_cancelled.is_set()
    assert cancelled_metadata(chat_service).run_status == "cancelled"


@pytest.mark.asyncio
async def test_deep_stream_cancels_graph_and_persists_cancelled_event():
    agent_started = asyncio.Event()
    agent_cancelled = asyncio.Event()

    class SlowDeepAdapter:
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
            agent_started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                agent_cancelled.set()
                raise

    chat_service = make_chat_service()
    response = await stream_with_deep_agent(
        request=ChatRequest(
            message="Deeply analyze AAPL",
            chat_id="chat_cancel",
            agent_version="v4-deep",
            language="en",
        ),
        user_id="local",
        chat_service=chat_service,
        agent=SlowDeepAdapter(),
        context_manager=make_context_manager(),
        message_repo=AsyncMock(),
        client_request=DisconnectAfterPoll(),  # type: ignore[arg-type]
    )

    async for _ in response.body_iterator:
        pass

    assert agent_started.is_set()
    assert agent_cancelled.is_set()
    metadata = cancelled_metadata(chat_service)
    assert metadata.run_status == "cancelled"
    assert metadata.raw_data is not None
    assert metadata.raw_data["deep_events"][-1]["type"] == "deep_cancelled"


@pytest.mark.asyncio
async def test_react_final_chunk_disconnect_overwrites_completed_status():
    class ImmediateReactAgent:
        async def ainvoke(self, **kwargs):
            return {
                "final_answer": "OK",
                "tool_executions": 0,
                "trace_id": "trace_final_chunk",
            }

    chat_service = make_chat_service()
    response = await stream_with_react_agent(
        request=ChatRequest(
            message="What is the current AAPL price?",
            chat_id="chat_cancel",
            agent_version="v3",
            language="en",
        ),
        user_id="local",
        chat_service=chat_service,
        agent=ImmediateReactAgent(),  # type: ignore[arg-type]
        context_manager=make_context_manager(),
        message_repo=AsyncMock(),
        client_request=DisconnectOnCall(3),  # type: ignore[arg-type]
    )

    async for _ in response.body_iterator:
        pass

    assert cancelled_metadata(chat_service).run_status == "cancelled"
    statuses = [
        call.kwargs["metadata"].run_status
        for call in chat_service.upsert_run_message.await_args_list
    ]
    assert statuses == ["cancelled"]


@pytest.mark.asyncio
async def test_deep_final_chunk_disconnect_overwrites_completed_status():
    class ImmediateDeepAdapter:
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
            return {
                "final_answer": "OK",
                "tool_executions": 0,
                "trace_id": "trace_deep_final_chunk",
                "research_context": {},
            }

    chat_service = make_chat_service()
    response = await stream_with_deep_agent(
        request=ChatRequest(
            message="Deeply analyze AAPL",
            chat_id="chat_cancel",
            agent_version="v4-deep",
            language="en",
        ),
        user_id="local",
        chat_service=chat_service,
        agent=ImmediateDeepAdapter(),
        context_manager=make_context_manager(),
        message_repo=AsyncMock(),
        client_request=DisconnectOnCall(3),  # type: ignore[arg-type]
    )

    async for _ in response.body_iterator:
        pass

    statuses = [
        call.kwargs["metadata"].run_status
        for call in chat_service.upsert_run_message.await_args_list
    ]
    assert statuses == ["cancelled"]
