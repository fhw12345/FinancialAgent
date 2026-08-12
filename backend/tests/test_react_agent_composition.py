"""Composition coverage for the ReAct invocation boundary.

The real FinancialAnalysisReActAgent response lifecycle is exercised while only
the outer model graph is faked. This protects retries, tool accounting,
conversation conversion, malformed structured output, and terminal errors.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel

from src.agent.langgraph_react_agent import FinancialAnalysisReActAgent


class _Graph:
    def __init__(self, outcomes: Sequence[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def ainvoke(self, payload: dict[str, Any], config: object) -> object:
        self.calls.append(payload)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _result(answer: str, *, with_tool: bool) -> dict[str, list[Any]]:
    messages: list[Any] = []
    if with_tool:
        messages.append(ToolMessage(content="quote=200", tool_call_id="quote_call"))
    messages.append(AIMessage(content=answer))
    return {"messages": messages}


def _agent(outcomes: Sequence[object]) -> tuple[FinancialAnalysisReActAgent, _Graph]:
    agent = object.__new__(FinancialAnalysisReActAgent)
    graph = _Graph(outcomes)
    agent.agent = graph
    agent.langfuse_enabled = False
    agent.langfuse_client = None
    return agent, graph


@pytest.mark.asyncio
async def test_react_success_preserves_history_and_counts_tools() -> None:
    agent, graph = _agent([_result("grounded answer", with_tool=True)])

    response = await agent.ainvoke(
        "Explain the result",
        conversation_history=[
            {"role": "user", "content": "Prior question"},
            {"role": "assistant", "content": "Prior answer"},
        ],
        language="en",
        chat_id="chat_composition",
    )

    assert response["final_answer"] == "grounded answer"
    assert response["tool_executions"] == 1
    sent = graph.calls[0]["messages"]
    assert [message.__class__.__name__ for message in sent] == [
        "HumanMessage",
        "AIMessage",
        "HumanMessage",
    ]


@pytest.mark.asyncio
async def test_zero_tool_guard_retries_financial_request() -> None:
    agent, graph = _agent(
        [
            _result("unsupported first answer", with_tool=False),
            _result("tool-backed retry", with_tool=True),
        ]
    )

    response = await agent.ainvoke(
        "What is the current AAPL stock price?", language="en"
    )

    assert response["final_answer"] == "tool-backed retry"
    assert response["tool_executions"] == 1
    assert len(graph.calls) == 2
    retry_messages = graph.calls[1]["messages"]
    assert "not used any tools" in retry_messages[-1].content


@pytest.mark.asyncio
async def test_transient_failure_then_success_does_not_rethrow_stale_error() -> None:
    agent, graph = _agent(
        [TimeoutError("gateway timeout"), _result("recovered", with_tool=True)]
    )

    with patch("src.agent.langgraph_react_agent.asyncio.sleep") as sleep:
        response = await agent.ainvoke("Current AAPL quote", language="en")

    assert response["final_answer"] == "recovered"
    assert "error" not in response
    assert len(graph.calls) == 2
    sleep.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_retryable_failure_returns_typed_terminal_error() -> None:
    agent, graph = _agent([ValueError("invalid graph state")])

    response = await agent.ainvoke("Explain duration", language="en")

    assert response["error"] == "invalid graph state"
    assert response["final_answer"].startswith("Agent execution failed")
    assert response["tool_executions"] == 0
    assert len(graph.calls) == 1


class _StructuredResult(BaseModel):
    value: int


class _StructuredInvoker:
    def __init__(self, outcomes: Sequence[object]) -> None:
        self.outcomes = list(outcomes)
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str) -> object:
        self.prompts.append(prompt)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _StructuredLlm:
    def __init__(self, invoker: _StructuredInvoker) -> None:
        self.invoker = invoker

    def with_structured_output(self, schema: type[BaseModel]) -> _StructuredInvoker:
        return self.invoker


@pytest.mark.asyncio
async def test_structured_invocation_validates_and_retries() -> None:
    agent, _ = _agent([])
    invoker = _StructuredInvoker([ConnectionError("connection reset"), {"value": 7}])
    agent.llm = _StructuredLlm(invoker)

    with patch("src.agent.langgraph_react_agent.asyncio.sleep") as sleep:
        result = await agent.ainvoke_structured(
            "Return value", _StructuredResult, context="Research context"
        )

    assert result == _StructuredResult(value=7)
    assert invoker.prompts[-1].startswith("Research context\n\n---")
    sleep.assert_awaited_once()


@pytest.mark.asyncio
async def test_structured_invocation_rejects_invalid_payload() -> None:
    agent, _ = _agent([])
    agent.llm = _StructuredLlm(_StructuredInvoker([{"wrong": 1}]))

    with pytest.raises(ValueError):
        await agent.ainvoke_structured("Return value", _StructuredResult)


class _Trace:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


class _LangfuseClient:
    def __init__(self) -> None:
        self.trace_obj = _Trace()
        self.flush_count = 0

    def trace(self, **kwargs: Any) -> _Trace:
        return self.trace_obj

    def flush(self) -> None:
        self.flush_count += 1


@pytest.mark.asyncio
async def test_langfuse_trace_records_success_and_terminal_failure() -> None:
    success_agent, _ = _agent([_result("observed", with_tool=True)])
    success_client = _LangfuseClient()
    success_agent.langfuse_enabled = True
    success_agent.langfuse_client = success_client

    success = await success_agent.ainvoke("Explain result", language="en")
    assert success["final_answer"] == "observed"
    assert success_client.trace_obj.updates[-1]["metadata"]["status"] == "success"
    assert success_client.flush_count == 1

    failed_agent, _ = _agent([ValueError("broken state")])
    failed_client = _LangfuseClient()
    failed_agent.langfuse_enabled = True
    failed_agent.langfuse_client = failed_client
    failed = await failed_agent.ainvoke("Explain duration", language="en")
    assert failed["error"] == "broken state"
    assert failed_client.trace_obj.updates[-1]["metadata"]["status"] == "error"
    assert failed_client.flush_count == 1


@pytest.mark.asyncio
async def test_zero_tool_retry_failure_keeps_original_answer() -> None:
    agent, graph = _agent(
        [_result("original answer", with_tool=False), RuntimeError("nudge failed")]
    )
    response = await agent.ainvoke("Current AAPL price", language="en")
    assert response["final_answer"] == "original answer"
    assert response["tool_executions"] == 0
    assert len(graph.calls) == 2


@pytest.mark.asyncio
async def test_structured_non_retryable_error_is_not_retried() -> None:
    agent, _ = _agent([])
    invoker = _StructuredInvoker([ValueError("invalid structured request")])
    agent.llm = _StructuredLlm(invoker)
    with pytest.raises(ValueError, match="invalid structured request"):
        await agent.ainvoke_structured("Return value", _StructuredResult)
    assert len(invoker.prompts) == 1


@pytest.mark.asyncio
async def test_callbacks_debug_and_trace_creation_failure_do_not_block_run() -> None:
    agent, graph = _agent([_result("callback answer", with_tool=True)])
    agent.langfuse_enabled = True
    agent.langfuse_client = type(
        "BrokenClient",
        (),
        {
            "trace": lambda self, **kwargs: (_ for _ in ()).throw(
                RuntimeError("trace down")
            )
        },
    )()
    callback = object()

    response = await agent.ainvoke(
        "Explain result", additional_callbacks=[callback], debug=True, language="en"
    )

    assert response["final_answer"] == "callback answer"
    assert graph.calls[0]["messages"]


@pytest.mark.asyncio
async def test_retry_exhaustion_returns_terminal_error_after_three_attempts() -> None:
    agent, graph = _agent([TimeoutError("gateway timeout") for _ in range(3)])
    with patch("src.agent.langgraph_react_agent.asyncio.sleep") as sleep:
        response = await agent.ainvoke("Current AAPL price", language="en")
    assert response["error"] == "gateway timeout"
    assert len(graph.calls) == 3
    assert sleep.await_count == 2


class _BrokenTrace(_Trace):
    def update(self, **kwargs: Any) -> None:
        raise RuntimeError("trace update failed")


@pytest.mark.asyncio
async def test_trace_update_failure_is_non_fatal() -> None:
    agent, _ = _agent([_result("still succeeds", with_tool=True)])
    client = _LangfuseClient()
    client.trace_obj = _BrokenTrace()
    agent.langfuse_enabled = True
    agent.langfuse_client = client
    response = await agent.ainvoke("Explain result", language="en")
    assert response["final_answer"] == "still succeeds"
