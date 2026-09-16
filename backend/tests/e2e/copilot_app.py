"""Real app/Chat/storage + recorded GitHub/Copilot transport. Never imports pi auth."""

import json
import time
from pathlib import Path

import httpx
from fastapi.responses import JSONResponse

from src.agent import copilot_chat_model
from src.api import copilot
from src.core.config import get_settings
from src.main import app
from src.services.cache_warming_service import CacheWarmingService
from src.services.copilot import context
from src.services.copilot.service import CopilotService
from src.services.translation_service import _cache_key
from tests.copilot_fixtures import sse, text_output
from tests.copilot_chat_fixtures import chat_sse, chat_tool

approved = False
mode = "normal"
requests = []
model_requests = []


def recorded(request):
    requests.append(request.url.path)
    path = request.url.path
    if path == "/login/device/code":
        return httpx.Response(
            200,
            json={
                "device_code": "fake-device",
                "user_code": "TEST-CODE",
                "verification_uri": "https://github.com/login/device",
                "expires_in": 900,
                "interval": 1,
            },
        )
    if path == "/login/oauth/access_token":
        if mode in ("denied", "expired"):
            return httpx.Response(
                200,
                json={
                    "error": "access_denied" if mode == "denied" else "expired_token"
                },
            )
        return httpx.Response(
            200,
            json=(
                {"access_token": "fake-gh"}
                if approved
                else {"error": "authorization_pending"}
            ),
        )
    if path == "/copilot_internal/v2/token":
        return httpx.Response(
            200, json={"token": "fake-cp", "expires_at": time.time() + 3600}
        )
    if path == "/models":
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "gpt-6-astra",
                        "name": "Recorded GPT",
                        "model_picker_enabled": True,
                        "policy": {"state": "enabled"},
                        "supported_endpoints": ["/responses"],
                    },
                    *[
                        {
                            "id": mid,
                            "name": "Recorded " + mid,
                            "vendor": vendor,
                            "model_picker_enabled": True,
                            "policy": {"state": "enabled"},
                            "supported_endpoints": [endpoint],
                            "capabilities": {"supports": {"tool_calls": True}},
                        }
                        for mid, vendor, endpoint in [
                            ("gpt-5.4-mini", "OpenAI", "/responses"),
                            ("gpt-5.4", "OpenAI", "/responses"),
                            ("gpt-5.6-sol", "OpenAI", "/responses"),
                            ("gemini-3.8-flash", "Google", "/chat/completions"),
                            ("grok-4.6", "xAI", "/responses"),
                            ("mai-code-1.1-flash", "Microsoft", "/responses"),
                        ]
                    ],
                    {
                        "id": "claude-test",
                        "model_picker_enabled": True,
                        "policy": {"state": "enabled"},
                        "supported_endpoints": ["/v1/messages"],
                    },
                    {
                        "id": "gpt-5-disabled",
                        "model_picker_enabled": True,
                        "policy": {"state": "disabled"},
                    },
                ]
            },
        )
    if path in ("/responses", "/chat/completions"):
        body = json.loads(request.content)
        model_requests.append({"model": body["model"], "endpoint": path})
    if path == "/chat/completions":
        if mode == "limited":
            return httpx.Response(429)
        if body.get("tools"):
            return chat_tool(body["tools"][0]["function"]["name"], {"connected": True})
        return chat_sse([{"content": "NATIVE_GEMINI_CHAT_OK"}])
    if path == "/responses":
        if mode == "limited":
            return httpx.Response(429, json={"message": "recorded limit"})
        body = json.loads(request.content)
        if any(t.get("name") == "ConnectionResult" for t in body.get("tools", [])):
            return sse(
                [
                    {
                        "type": "function_call",
                        "id": "fc_connection",
                        "call_id": "call_connection",
                        "name": "ConnectionResult",
                        "arguments": '{"connected":true}',
                        "status": "completed",
                    }
                ]
            )
        if "NATIVE_GEMINI_CHAT_OK" in json.dumps(body):
            return sse(text_output("NATIVE_GEMINI_CHAT_OK"))
        return sse(
            text_output("NATIVE_COPILOT_CHAT_OK"),
            deltas=[
                {
                    "type": "response.output_text.delta",
                    "delta": "NATIVE_COPILOT_CHAT_OK",
                }
            ],
        )
    raise AssertionError(f"Unexpected external path: {path}")


service = CopilotService(
    Path(get_settings().copilot_state_dir), transport=httpx.MockTransport(recorded)
)
copilot.get_copilot_service = lambda: service
context.get_copilot_service = lambda: service
copilot_chat_model.get_copilot_service = lambda: service


async def skip_warming(self, symbols=None):
    return {"status": "skipped", "reason": "recorded_copilot_e2e"}


CacheWarmingService.warm_startup_cache = skip_warming


@app.middleware("http")
async def no_market_widgets(request, call_next):
    if request.url.path == "/api/market/market-movers":
        return JSONResponse(
            {"top_gainers": [], "top_losers": [], "most_actively_traded": []}
        )
    return await call_next(request)


@app.post("/api/test/copilot/reset")
async def reset():
    global approved, mode
    approved = False
    mode = "normal"
    requests.clear()
    model_requests.clear()
    await app.state.redis.delete(_cache_key("NATIVE_GEMINI_CHAT_OK", "zh-CN"))
    service.logout()
    return {"reset": True}


@app.post("/api/test/copilot/approve")
async def approve():
    global approved
    approved = True
    return {"approved": True}


@app.post("/api/test/copilot/mode/{value}")
async def change_mode(value: str):
    global mode
    assert value in ("normal", "denied", "expired", "limited")
    mode = value
    return {"mode": mode}


@app.get("/api/test/copilot/evidence")
async def evidence():
    return {
        "requests": requests,
        "model_requests": model_requests,
        "authenticated": service.status()["authenticated"],
    }
