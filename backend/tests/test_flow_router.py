"""Tests for hybrid automatic chat-flow routing."""

import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.responses import StreamingResponse

from src.agent.flow_router import (
    AgentFlowRouter,
    FlowRoutingDecision,
    RouteClassification,
)
from src.api.chat.streaming.handlers import (
    _prepend_route_event,
    _wrap_persistence_event_stream,
)
from src.core.utils.date_utils import utcnow
from src.models.agent_run import AgentRun


@pytest.mark.asyncio
async def test_explicit_override_is_preserved():
    router = AgentFlowRouter()

    result = await router.select(
        message="hello",
        current_symbol=None,
        requested_version="v4-deep",
    )

    assert result.flow == "v4-deep"
    assert result.source == "explicit"


@pytest.mark.asyncio
async def test_deep_financial_request_uses_deep_flow():
    router = AgentFlowRouter()

    result = await router.select(
        message="请对 NVDA 做完整投资分析并加入反方质疑",
        current_symbol="NVDA",
        requested_version="auto",
    )

    assert result.flow == "v4-deep"
    assert result.reason_code == "deep_financial_request"


@pytest.mark.asyncio
async def test_live_data_request_uses_react_flow():
    router = AgentFlowRouter()

    result = await router.select(
        message="What is the current price and latest news for AAPL?",
        current_symbol=None,
        requested_version="auto",
    )

    assert result.flow == "v3"
    assert result.reason_code == "live_data_or_tool_request"


@pytest.mark.asyncio
async def test_generic_concept_stays_simple_even_with_selected_symbol():
    router = AgentFlowRouter()

    result = await router.select(
        message="什么是市盈率？",
        current_symbol="AAPL",
        requested_version="auto",
    )

    assert result.flow == "v2"
    assert result.reason_code == "concept_explanation"


@pytest.mark.asyncio
async def test_deictic_selected_symbol_request_uses_react():
    router = AgentFlowRouter()

    result = await router.select(
        message="这只股票接下来的走势和风险怎么看？",
        current_symbol="AAPL",
        requested_version="auto",
    )

    assert result.flow == "v3"
    assert result.reason_code == "selected_symbol_analysis"


@pytest.mark.asyncio
async def test_explicit_ticker_analysis_uses_react():
    router = AgentFlowRouter()

    result = await router.select(
        message="Analyze NVDA outlook and risks",
        current_symbol=None,
        requested_version="auto",
    )

    assert result.flow == "v3"
    assert result.reason_code == "explicit_symbol_analysis"


@pytest.mark.asyncio
async def test_ambiguous_request_uses_classifier():
    classifier = AsyncMock()
    classifier.ainvoke.return_value = RouteClassification(flow="v4-deep")
    llm = Mock()
    llm.with_structured_output.return_value = classifier
    router = AgentFlowRouter(llm=llm)

    result = await router.select(
        message="Give me the strongest possible view on Microsoft",
        current_symbol=None,
        requested_version="auto",
    )

    assert result.flow == "v4-deep"
    assert result.source == "classifier"
    assert result.reason_code == "classifier_v4_deep"


@pytest.mark.asyncio
async def test_classifier_failure_falls_back_to_react():
    classifier = AsyncMock()
    classifier.ainvoke.side_effect = ValueError("invalid structured output")
    llm = Mock()
    llm.with_structured_output.return_value = classifier
    router = AgentFlowRouter(llm=llm)

    result = await router.select(
        message="Thoughts on Microsoft?",
        current_symbol=None,
        requested_version="auto",
    )

    assert result.flow == "v3"
    assert result.source == "fallback"
    assert result.reason_code == "classifier_error_fallback"


@pytest.mark.asyncio
async def test_route_event_is_prepended_as_data_only_sse():
    async def original_stream():
        yield 'data: {"type":"done","chat_id":"chat_1"}\n\n'

    wrapped = _prepend_route_event(
        StreamingResponse(original_stream(), media_type="text/event-stream"),
        FlowRoutingDecision(
            flow="v3",
            source="rule",
            reason_code="live_data_or_tool_request",
        ),
        AgentRun(
            run_id="run_1",
            requested_policy="auto",
            selected_policy="v3",
            policy_version="auto-router-v1",
            execution_mode="agentic",
            status="running",
            started_at=utcnow(),
        ),
    )

    chunks = []
    async for chunk in wrapped.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)

    envelopes = [
        json.loads(block.removeprefix("data: "))
        for block in "".join(chunks).split("\n\n")
        if block
    ]
    assert [event["sequence"] for event in envelopes] == [1, 2, 3]
    assert [event["type"] for event in envelopes] == [
        "run_started",
        "policy_selected",
        "stream_completed",
    ]
    assert envelopes[0]["run_id"] == "run_1"
    assert envelopes[1]["payload"]["flow"] == "v3"
    assert envelopes[2]["payload"]["chat_id"] == "chat_1"


@pytest.mark.asyncio
async def test_closing_route_prelude_cancels_unstarted_run():
    inner_started = False
    cancelled = AsyncMock()

    async def original_stream():
        nonlocal inner_started
        inner_started = True
        yield 'data: {"type":"done"}\n\n'

    wrapped = _prepend_route_event(
        StreamingResponse(original_stream(), media_type="text/event-stream"),
        FlowRoutingDecision(
            flow="v2",
            source="rule",
            reason_code="concept_explanation",
        ),
        AgentRun(
            run_id="run_1",
            requested_policy="auto",
            selected_policy="v2",
            policy_version="auto-router-v1",
            execution_mode="instant",
            status="running",
            started_at=utcnow(),
        ),
        on_prelude_cancel=cancelled,
    )

    iterator = wrapped.body_iterator
    await anext(iterator)
    await iterator.aclose()

    cancelled.assert_awaited_once_with()
    assert inner_started is False


@pytest.mark.asyncio
async def test_persistence_only_stream_is_enveloped():
    async def original_stream():
        yield 'data: {"type":"done","chat_id":"chat_1"}\n\n'

    wrapped = _wrap_persistence_event_stream(
        StreamingResponse(original_stream(), media_type="text/event-stream"),
        run_id="event_1",
    )
    output = ""
    async for chunk in wrapped.body_iterator:
        output += chunk.decode() if isinstance(chunk, bytes) else chunk

    envelope = json.loads(output.removeprefix("data: ").strip())
    assert envelope["run_id"] == "event_1"
    assert envelope["sequence"] == 1
    assert envelope["type"] == "stream_completed"


@pytest.mark.asyncio
async def test_envelope_failure_marks_run_failed_before_inner_close():
    failed = AsyncMock()

    async def malformed_stream():
        yield "not-sse"

    wrapped = _prepend_route_event(
        StreamingResponse(malformed_stream(), media_type="text/event-stream"),
        FlowRoutingDecision(
            flow="v2",
            source="rule",
            reason_code="concept_explanation",
        ),
        AgentRun(
            run_id="run_1",
            requested_policy="auto",
            selected_policy="v2",
            policy_version="auto-router-v1",
            execution_mode="instant",
            status="running",
            started_at=utcnow(),
        ),
        on_stream_failure=failed,
    )

    with pytest.raises(ValueError, match="must start"):
        async for _ in wrapped.body_iterator:
            pass

    failed.assert_awaited_once()


@pytest.mark.asyncio
async def test_envelope_failure_is_shielded_before_cancelled_inner_close():
    failure_started = asyncio.Event()
    release_failure = asyncio.Event()
    failure_completed = asyncio.Event()
    inner_closed = asyncio.Event()

    async def malformed_stream():
        try:
            yield "not-sse"
        finally:
            inner_closed.set()

    async def persist_failure(exc: Exception):
        failure_started.set()
        await release_failure.wait()
        failure_completed.set()

    wrapped = _prepend_route_event(
        StreamingResponse(malformed_stream(), media_type="text/event-stream"),
        FlowRoutingDecision(
            flow="v2",
            source="rule",
            reason_code="concept_explanation",
        ),
        AgentRun(
            run_id="run_1",
            requested_policy="auto",
            selected_policy="v2",
            policy_version="auto-router-v1",
            execution_mode="instant",
            status="running",
            started_at=utcnow(),
        ),
        on_stream_failure=persist_failure,
    )

    async def consume():
        async for _ in wrapped.body_iterator:
            pass

    consumer = asyncio.create_task(consume())
    await failure_started.wait()
    consumer.cancel()
    release_failure.set()
    with pytest.raises(asyncio.CancelledError):
        await consumer

    assert failure_completed.is_set()
    assert inner_closed.is_set()
