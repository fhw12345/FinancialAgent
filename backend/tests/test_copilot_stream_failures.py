import asyncio
import json

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agent.copilot_chat_model import CopilotChatModel
from src.services.copilot.catalog import CopilotModel
from src.services.copilot.protocol import CopilotError
from tests.copilot_fixtures import ready_service, sse, text_output
from tests.test_copilot_auth import upstream


@pytest.mark.asyncio
async def test_401_refresh_once_and_429_never_replays(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path != "/responses":
            return upstream(request)
        if calls.count("/responses") == 1:
            return httpx.Response(401)
        return sse(text_output("OK"))

    ready_service(tmp_path, handler, monkeypatch)
    assert (await CopilotChatModel().ainvoke("test")).content == "OK"
    assert calls == ["/responses", "/copilot_internal/v2/token", "/responses"]
    calls.clear()

    def limited(request):
        calls.append(request.url.path)
        return httpx.Response(429, json={"message": "private"})

    ready_service(tmp_path, limited, monkeypatch)
    with pytest.raises(CopilotError, match="rate_limited"):
        await CopilotChatModel().ainvoke("test")
    assert calls == ["/responses"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        "data: {invalid}\n\n",
        'data: {"type":"response.output_text.delta","delta":"partial"}\n\n',
        'data: {"type":"response.completed"}',
        "",
    ],
)
async def test_truncated_invalid_streams_fail(tmp_path, monkeypatch, body):
    ready_service(tmp_path, lambda _: httpx.Response(200, content=body), monkeypatch)
    with pytest.raises(CopilotError):
        await CopilotChatModel().ainvoke("test")


@pytest.mark.asyncio
async def test_tool_loop_model_binding_survives_selection_change(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body["model"])
        return sse(text_output("OK"))

    service = ready_service(tmp_path, handler, monkeypatch)
    first = await CopilotChatModel().ainvoke("one")
    state = service.store.read()
    state.selected_model = "gpt-5-mini"
    state.models.append(CopilotModel(id="gpt-5-mini", name="Other"))
    service.store.save(state)
    second = await CopilotChatModel().ainvoke(
        [HumanMessage("one"), first, HumanMessage("continue this run")]
    )
    assert second.content == "OK" and calls == ["gpt-6-astra", "gpt-6-astra"]


@pytest.mark.asyncio
async def test_abort_closes_http_stream(tmp_path, monkeypatch):
    entered = asyncio.Event()
    closed = asyncio.Event()

    class Delayed(httpx.AsyncByteStream):
        async def __aiter__(self):
            entered.set()
            await asyncio.sleep(60)
            yield b""

        async def aclose(self):
            closed.set()

    ready_service(
        tmp_path, lambda _: httpx.Response(200, stream=Delayed()), monkeypatch
    )
    task = asyncio.create_task(CopilotChatModel().ainvoke("test"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", ["invalid", "[]", "null"])
async def test_invalid_arguments_fail_even_for_streaming(
    tmp_path, monkeypatch, arguments
):
    output = [
        {
            "type": "function_call",
            "call_id": "call_bad",
            "name": "probe",
            "arguments": arguments,
        }
    ]
    ready_service(tmp_path, lambda _: sse(output), monkeypatch)
    with pytest.raises(CopilotError, match="invalid_tool_arguments"):
        async for _ in CopilotChatModel().astream("test"):
            pass


@pytest.mark.asyncio
async def test_concurrent_rejected_tokens_refresh_only_once(tmp_path, monkeypatch):
    rejected = 0
    refreshes = 0
    barrier = asyncio.Event()

    async def handler(request):
        nonlocal rejected, refreshes
        if request.url.path == "/copilot_internal/v2/token":
            refreshes += 1
            return upstream(request)
        if request.headers["Authorization"] == "Bearer fixture-copilot":
            rejected += 1
            if rejected == 10:
                barrier.set()
            await barrier.wait()
            return httpx.Response(401)
        return sse(text_output("ok"))

    ready_service(tmp_path, handler, monkeypatch)
    results = await asyncio.gather(
        *(CopilotChatModel().ainvoke("hello") for _ in range(10))
    )
    assert all(result.content == "ok" for result in results)
    assert refreshes == 1


def test_duplicate_completion_and_changed_tool_identity_fail():
    from src.services.copilot.responses import ResponseChunks

    decoder = ResponseChunks("gpt-6-astra")
    event = {
        "type": "response.completed",
        "response": {
            "status": "completed",
            "output": text_output("ok"),
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    }
    decoder.feed(event)
    with pytest.raises(CopilotError, match="events_after_completion"):
        decoder.feed(event)
    decoder = ResponseChunks("gpt-6-astra")
    decoder.feed(
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"type": "function_call", "call_id": "one", "name": "probe"},
        }
    )
    with pytest.raises(CopilotError, match="tool_identity_changed"):
        decoder.feed(
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "item": {
                    "type": "function_call",
                    "call_id": "two",
                    "name": "probe",
                    "arguments": "{}",
                },
            }
        )
