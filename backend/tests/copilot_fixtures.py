"""Recorded Copilot HTTP boundary; no real login tokens or provider calls."""

import json
import time

import httpx
from pydantic import SecretStr

from src.services.copilot.catalog import CopilotModel
from src.services.copilot.service import CopilotService


def sse(output, *, deltas=None, status="completed"):
    events = list(deltas or [])
    events.append(
        {
            "type": "response." + status,
            "response": {
                "status": status,
                "output": output,
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "input_tokens_details": {"cached_tokens": 3},
                },
            },
        }
    )
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content="".join(
            "data: " + json.dumps(e, ensure_ascii=False) + "\n\n" for e in events
        ),
    )


def text_output(text):
    return [
        {
            "type": "message",
            "id": "msg_fixture",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }
    ]


def ready_service(tmp_path, handler, monkeypatch):
    service = CopilotService(tmp_path, transport=httpx.MockTransport(handler))
    state = service.store.read()
    state.github_token = SecretStr("fixture-github")
    state.access_token = SecretStr("fixture-copilot")
    state.expires_at = time.time() + 3600
    state.selected_model = "gpt-6-astra"
    state.models = [CopilotModel(id="gpt-6-astra", name="Recorded GPT")]
    state.catalog_at = time.time()
    service.store.save(state)
    from src.services.copilot import context

    context._profile.set(None)
    for module in [
        "src.agent.copilot_chat_model",
        "src.services.copilot.context",
        "src.api.copilot",
        "src.services.copilot.service",
    ]:
        monkeypatch.setattr(module + ".get_copilot_service", lambda: service)
    return service
