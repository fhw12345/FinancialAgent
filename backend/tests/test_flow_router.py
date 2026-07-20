"""Tests for hybrid automatic chat-flow routing."""

from unittest.mock import AsyncMock

import pytest
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage

from src.agent.flow_router import AgentFlowRouter, FlowRoutingDecision
from src.api.chat.streaming.handlers import _prepend_route_event
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
    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(content='{"flow":"v4-deep"}')
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
    llm = AsyncMock()
    llm.ainvoke.return_value = AIMessage(content="not json")
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

    output = "".join(chunks)
    assert output.startswith('data: {"type": "run_state"')
    assert '"run_id": "run_1"' in output
    assert 'data: {"type": "route_selected"' in output
    assert '"flow": "v3"' in output
    assert output.endswith('data: {"type":"done","chat_id":"chat_1"}\n\n')


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
