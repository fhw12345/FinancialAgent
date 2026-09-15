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
from tests.copilot_fixtures import sse, text_output

approved = False
mode = "normal"
requests = []


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
        if mode == "denied":
            return httpx.Response(200, json={"error": "access_denied"})
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
    assert value in ("normal", "denied", "limited")
    mode = value
    return {"mode": mode}


@app.get("/api/test/copilot/evidence")
async def evidence():
    return {"requests": requests, "authenticated": service.status()["authenticated"]}
