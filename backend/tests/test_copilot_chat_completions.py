import json
import asyncio

import httpx
import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

from src.agent.copilot_chat_model import CopilotChatModel
from src.services.copilot.catalog import CopilotModel
from src.services.copilot.completions import chat_input
from src.services.copilot.protocol import CopilotError
from tests.copilot_fixtures import ready_service
from tests.copilot_chat_fixtures import chat_sse, chat_tool


def gemini(tmp_path, handler, monkeypatch):
    service = ready_service(tmp_path, handler, monkeypatch)
    state = service.store.read()
    state.selected_model = "gemini-3.8-flash"
    state.models = [
        CopilotModel(
            id=state.selected_model,
            name="Recorded Gemini",
            api="openai-completions",
            vendor="Google",
        )
    ]
    service.store.save(state)
    return service


@pytest.mark.asyncio
async def test_gemini_parallel_tools_reasoning_and_real_graph(tmp_path, monkeypatch):
    requests = []
    values = []

    @tool
    def next_number(value: int) -> int:
        """Return the next integer."""
        values.append(value)
        return value + 1

    def handler(request):
        data = json.loads(request.content)
        requests.append(data)
        assert request.url.path == "/chat/completions"
        assert data["stream_options"] == {"include_usage": True}
        assert "max_completion_tokens" in data and "include" not in data
        if len(requests) == 1:
            return chat_sse(
                [
                    {
                        "reasoning_details": [
                            {"type": "reasoning.encrypted", "data": "opaque", "id": "r"}
                        ]
                    },
                    {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_a",
                                "type": "function",
                                "function": {
                                    "name": "next_number",
                                    "arguments": '{"value":',
                                },
                            },
                            {
                                "index": 1,
                                "id": "call_b",
                                "type": "function",
                                "function": {
                                    "name": "next_number",
                                    "arguments": '{"value":4}',
                                },
                            },
                        ]
                    },
                    {"tool_calls": [{"index": 0, "function": {"arguments": "2}"}}]},
                ],
                finish="tool_calls",
            )
        assistant = next(m for m in data["messages"] if m["role"] == "assistant")
        assert assistant["reasoning_details"][0]["data"] == "opaque"
        assert {m["tool_call_id"] for m in data["messages"] if m["role"] == "tool"} == {
            "call_a",
            "call_b",
        }
        return chat_sse([{"content": "结果\u2028"}, {"content": "3,5"}])

    gemini(tmp_path, handler, monkeypatch)
    result = await create_react_agent(CopilotChatModel(), [next_number]).ainvoke(
        {"messages": [HumanMessage("Use the tool for 2 and 4")]}
    )
    message = result["messages"][-1]
    assert message.content == "结果\u20283,5" and sorted(values) == [2, 4]
    assert message.usage_metadata["total_tokens"] == 28
    assert message.response_metadata["copilot_api"] == "openai-completions"
    assert message.response_metadata["copilot_role"] == "simple_chat"
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_structured_output_and_no_cross_role_reasoning(tmp_path, monkeypatch):
    class Answer(BaseModel):
        count: int

    def handler(request):
        data = json.loads(request.content)
        assert data["tool_choice"] == "required"
        return chat_tool(data["tools"][0]["function"]["name"], {"count": 2})

    gemini(tmp_path, handler, monkeypatch)
    result = await CopilotChatModel().with_structured_output(Answer).ainvoke("Return 2")
    assert result.count == 2
    message = (
        await CopilotChatModel()
        .bind_tools([Answer], tool_choice="required")
        .ainvoke("Return 2")
    )
    same = chat_input([message], "gemini-3.8-flash", "simple_chat")
    other = chat_input([message], "gemini-3.8-flash", "sub_news")
    assert "reasoning_details" in same[0] and "reasoning_details" not in other[0]
    assert other[0]["tool_calls"][0]["id"] == message.tool_calls[0]["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["length", "content_filter"])
async def test_bad_terminal_is_not_success(tmp_path, monkeypatch, reason):
    gemini(
        tmp_path,
        lambda _: chat_sse([{"content": "partial"}], finish=reason),
        monkeypatch,
    )
    with pytest.raises(CopilotError, match="incomplete"):
        await CopilotChatModel().ainvoke("Hello")


@pytest.mark.asyncio
async def test_usage_missing_and_stream_cancel(tmp_path, monkeypatch):
    gemini(tmp_path, lambda _: chat_sse([{"content": "ok"}], usage=False), monkeypatch)
    with pytest.raises(CopilotError, match="completion_or_usage"):
        await CopilotChatModel().ainvoke("Hello")
    started = asyncio.Event()
    closed = asyncio.Event()

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            started.set()
            await asyncio.sleep(60)
            yield b""

        async def aclose(self):
            closed.set()

    gemini(tmp_path, lambda _: httpx.Response(200, stream=Stream()), monkeypatch)
    task = asyncio.create_task(CopilotChatModel().ainvoke("Hello"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
