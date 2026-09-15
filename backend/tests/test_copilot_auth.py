"""Native Copilot auth contracts; all HTTP uses recorded in-memory transport."""

import asyncio
import time

import httpx
import pytest

from src.services.copilot.service import CopilotService
from src.services.copilot.protocol import CopilotError


def upstream(request):
    if request.url.path == "/login/device/code":
        return httpx.Response(
            200,
            json={
                "device_code": "private-device",
                "user_code": "TEST-CODE",
                "verification_uri": "https://github.com/login/device",
                "expires_in": 900,
                "interval": 1,
            },
        )
    if request.url.path == "/login/oauth/access_token":
        return httpx.Response(200, json={"access_token": "private-github"})
    if request.url.path == "/copilot_internal/v2/token":
        return httpx.Response(
            200, json={"token": "private-copilot", "expires_at": time.time() + 3600}
        )
    if request.url.path == "/models":
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "gpt-6-astra",
                        "name": "GPT test",
                        "model_picker_enabled": True,
                        "policy": {"state": "enabled"},
                        "supported_endpoints": ["/responses"],
                        "capabilities": {
                            "supports": {"tool_calls": True},
                            "limits": {"max_output_tokens": 4096},
                        },
                    }
                ]
            },
        )
    raise AssertionError(request.url.path)


@pytest.mark.asyncio
async def test_auth_model_selection_and_private_restart(tmp_path):
    service = CopilotService(tmp_path, transport=httpx.MockTransport(upstream))
    started = await service.start_login()
    assert started["login"]["user_code"] == "TEST-CODE"
    assert "private-device" not in str(started)
    await asyncio.sleep(1.01)
    logged_in = await service.poll_login(started["login"]["attempt_id"])
    assert logged_in["authenticated"]
    assert "private-github" not in str(logged_in)
    models = await service.models()
    assert [m.id for m in models] == ["gpt-6-astra"]
    await service.select_model("gpt-6-astra")
    restarted = CopilotService(tmp_path, transport=httpx.MockTransport(upstream))
    assert restarted.status()["selected_model"] == "gpt-6-astra"
    restarted.logout()
    assert not service.status()["authenticated"]
    with pytest.raises(CopilotError):
        await service.authorization()
