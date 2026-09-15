import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, ValidationError

from src.agent.copilot_chat_model import CopilotChatModel
from src.services.copilot.protocol import CopilotError
from src.services.copilot.responses import response_input
from tests.copilot_fixtures import ready_service, sse, text_output


@pytest.mark.asyncio
async def test_stream_unicode_usage_and_native_request(tmp_path, monkeypatch):
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        assert request.url.path == "/responses"
        assert request.headers["X-Initiator"] == "user"
        return sse(
            text_output("Hello\u2028世界"),
            deltas=[{"type": "response.output_text.delta", "delta": "Hello\u2028世界"}],
        )

    ready_service(tmp_path, handler, monkeypatch)
    result = await CopilotChatModel().ainvoke(
        [SystemMessage("Be precise"), HumanMessage("Hi")]
    )
    assert result.content == "Hello\u2028世界"
    assert result.usage_metadata == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "input_token_details": {"cache_read": 3},
    }
    assert captured[0]["store"] is False
    assert captured[0]["instructions"] == "Be precise"
    assert "temperature" not in captured[0]


@pytest.mark.asyncio
async def test_real_langgraph_tool_result_and_reasoning_replay(tmp_path, monkeypatch):
    calls = []
    executions = []

    @tool
    def add_one(value: int) -> int:
        """Return the next integer."""
        executions.append(value)
        return value + 1

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == 1:
            item = {
                "type": "function_call",
                "id": "fc_1",
                "call_id": "call_1",
                "name": "add_one",
                "arguments": '{"value":2}',
                "status": "completed",
            }
            reasoning = {
                "type": "reasoning",
                "id": "rs_1",
                "summary": [],
                "encrypted_content": "opaque-recorded-reasoning",
            }
            return sse(
                [reasoning, item],
                deltas=[
                    {
                        "type": "response.output_item.added",
                        "output_index": 1,
                        "item": {**item, "arguments": ""},
                    },
                    {
                        "type": "response.function_call_arguments.delta",
                        "output_index": 1,
                        "delta": '{"value":',
                    },
                    {
                        "type": "response.function_call_arguments.delta",
                        "output_index": 1,
                        "delta": "2}",
                    },
                    {
                        "type": "response.output_item.done",
                        "output_index": 1,
                        "item": item,
                    },
                ],
            )
        assert request.headers["X-Initiator"] == "agent"
        assert any(
            i.get("type") == "function_call_output"
            and i["call_id"] == "call_1"
            and i["output"] == "3"
            for i in payload["input"]
        )
        assert any(
            i.get("encrypted_content") == "opaque-recorded-reasoning"
            for i in payload["input"]
        )
        return sse(text_output("NATIVE_TOOL_RESULT_3"))

    ready_service(tmp_path, handler, monkeypatch)
    graph = create_react_agent(CopilotChatModel(), [add_one])
    result = await graph.ainvoke({"messages": [HumanMessage("Add one to 2")]})
    assert executions == [2]
    assert result["messages"][-1].content == "NATIVE_TOOL_RESULT_3"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_structured_output_validates_schema(tmp_path, monkeypatch):
    class Verdict(BaseModel):
        count: int

    valid = True

    def handler(request):
        data = json.loads(request.content)
        assert data["tool_choice"] == "required"
        assert data["tools"][0]["name"] == "Verdict"
        return sse(
            [
                {
                    "type": "function_call",
                    "call_id": "call_structured",
                    "name": "Verdict",
                    "arguments": json.dumps({"count": 2 if valid else "invalid"}),
                }
            ]
        )

    ready_service(tmp_path, handler, monkeypatch)
    model = CopilotChatModel().with_structured_output(Verdict)
    assert (await model.ainvoke("Return a count")).count == 2
    valid = False
    with pytest.raises(ValidationError):
        await model.ainvoke("Return a count")


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["failed", "incomplete"])
async def test_failed_terminal_never_success(tmp_path, monkeypatch, terminal):
    ready_service(tmp_path, lambda r: sse([], status=terminal), monkeypatch)
    with pytest.raises(CopilotError):
        await CopilotChatModel().ainvoke("Hello")


def test_foreign_model_does_not_replay_opaque_reasoning():
    message = AIMessage(
        content="Prior answer",
        additional_kwargs={
            "copilot_output": [{"type": "reasoning", "encrypted_content": "opaque"}]
        },
        response_metadata={"model_name": "other"},
    )
    _, items = response_input(
        [message, ToolMessage(content="ok", tool_call_id="call_1")], "gpt-6-astra"
    )
    assert not any(i.get("type") == "reasoning" for i in items)


@pytest.mark.asyncio
async def test_logout_invalidates_inflight_profile(tmp_path, monkeypatch):
    service = ready_service(tmp_path, lambda r: sse(text_output("ok")), monkeypatch)
    from src.services.copilot.context import current_profile

    current_profile()  # Simulate the binding captured by AgentRun/HTTP request.
    assert (await CopilotChatModel().ainvoke("hello")).content == "ok"
    service.logout()
    with pytest.raises(CopilotError, match="session_changed"):
        await CopilotChatModel().ainvoke("again")
