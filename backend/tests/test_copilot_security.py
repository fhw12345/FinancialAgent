import asyncio
import os
import time

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.copilot import router
from src.services.copilot.catalog import parse_catalog
from src.services.copilot.context import CopilotContextMiddleware
from src.services.copilot.protocol import CopilotError, api_from_token
from src.services.copilot.service import CopilotService
from tests.copilot_fixtures import ready_service
from tests.test_copilot_auth import upstream


def due(service):
    state = service.store.read()
    state.device.next_poll = 0
    service.store.save(state)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,expected",
    [
        ("authorization_pending", "pending"),
        ("slow_down", "pending"),
        ("access_denied", "denied"),
        ("expired_token", "expired"),
        ("other", "failed"),
    ],
)
async def test_device_states_and_no_early_poll(tmp_path, error, expected):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(
                200,
                json={
                    "error": error,
                    "error_description": "NEVER EXPOSE THIS PRIVATE BODY",
                },
            )
        return upstream(request)

    service = CopilotService(tmp_path, transport=httpx.MockTransport(handler))
    start = await service.start_login()
    attempt = start["login"]["attempt_id"]
    assert (await service.start_login())["login"]["attempt_id"] == attempt
    await service.poll_login(attempt)
    assert calls == ["/login/device/code"]
    due(service)
    state = await service.poll_login(attempt)
    assert state["login"]["state"] == expected
    assert not state["authenticated"]
    assert "NEVER EXPOSE" not in str(state)
    if error == "slow_down":
        assert state["login"]["interval"] == 6
    if expected != "pending":
        assert not service.store.read().device.device_code.get_secret_value()


@pytest.mark.asyncio
async def test_expiry_and_logout_late_oauth_response(tmp_path):
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(request):
        if request.url.path == "/login/oauth/access_token":
            entered.set()
            await release.wait()
        return upstream(request)

    service = CopilotService(tmp_path, transport=httpx.MockTransport(handler))
    started = await service.start_login()
    due(service)
    task = asyncio.create_task(service.poll_login(started["login"]["attempt_id"]))
    await entered.wait()
    service.logout()
    release.set()
    with pytest.raises(CopilotError, match="session_changed"):
        await task
    assert not service.status()["github_authorized"]
    started = await service.start_login()
    stored = service.store.read()
    stored.device.expires_at = 0
    service.store.save(stored)
    assert (await service.poll_login(started["login"]["attempt_id"]))["login"][
        "state"
    ] == "expired"


@pytest.mark.asyncio
async def test_single_flight_token_refresh(tmp_path, monkeypatch):
    count = 0

    async def handler(request):
        nonlocal count
        count += 1
        await asyncio.sleep(0.02)
        return upstream(request)

    service = ready_service(tmp_path, handler, monkeypatch)
    state = service.store.read()
    state.expires_at = 0
    service.store.save(state)
    await asyncio.gather(*(service.authorization() for _ in range(10)))
    assert count == 1
    if os.name != "nt":
        assert service.store.path.stat().st_mode & 0o777 == 0o600
        assert tmp_path.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "api.individual.githubcopilot.com.evil.example",
        "api.individual.githubcopilot.com@evil.example",
        "api.individual.githubcopilot.com/path",
        "api.individual.githubcopilot.com:443",
    ],
)
def test_rejects_credential_exfiltration_hosts(host):
    with pytest.raises(CopilotError):
        api_from_token("proxy-ep=" + host)
    assert (
        api_from_token("proxy-ep=proxy.individual.githubcopilot.com")
        == "https://api.individual.githubcopilot.com"
    )


@pytest.mark.asyncio
async def test_untrusted_verification_uri_and_redirect(tmp_path):
    for response in [
        httpx.Response(302, headers={"Location": "https://evil.example"}),
        httpx.Response(
            200,
            json={
                "device_code": "private",
                "user_code": "CODE",
                "verification_uri": "https://evil.example",
                "expires_in": 900,
                "interval": 5,
            },
        ),
    ]:
        service = CopilotService(
            tmp_path, transport=httpx.MockTransport(lambda _: response)
        )
        with pytest.raises(CopilotError):
            await service.start_login()
        assert service.status()["login"] is None


def test_catalog_permissions_and_supported_protocols():
    def row(model, **extras):
        return {
            "id": model,
            "model_picker_enabled": True,
            "policy": {"state": "enabled"},
            **extras,
        }

    data = {
        "data": [
            row("gpt-6-astra"),
            row("claude-opus-4.8"),
            row("gpt-5-disabled", policy={"state": "disabled"}),
            row("gpt-5-no-tools", capabilities={"supports": {"tool_calls": False}}),
            row("gpt-5-chat", supported_endpoints=["/chat/completions"]),
            row("gpt-5-unconfigured", policy={"state": "unconfigured"}),
        ]
    }
    assert [m.id for m in parse_catalog(data, individual=True)] == ["gpt-6-astra"]
    fallback = {"data": [row("gpt-6-astra", model_picker_enabled=False)]}
    assert len(parse_catalog(fallback, individual=True)) == 1
    assert parse_catalog(fallback, individual=False) == []


@pytest.mark.asyncio
async def test_api_requires_local_header_origin_and_hides_tokens(tmp_path, monkeypatch):
    service = ready_service(tmp_path, upstream, monkeypatch)
    app = FastAPI()
    app.add_middleware(CopilotContextMiddleware)
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        status = await client.get("/api/llm/copilot/status")
        assert status.headers["cache-control"] == "no-store"
        assert (
            "fixture-github" not in status.text and "fixture-copilot" not in status.text
        )
        assert (await client.post("/api/llm/copilot/logout")).status_code == 403
        assert (
            await client.post(
                "/api/llm/copilot/logout",
                headers={
                    "X-Financial-Agent-Local": "1",
                    "Origin": "https://evil.example",
                },
            )
        ).status_code == 403
        assert service.status()["authenticated"]
        assert (
            await client.post(
                "/api/llm/copilot/logout", headers={"X-Financial-Agent-Local": "1"}
            )
        ).status_code == 200
        assert not service.status()["authenticated"]


@pytest.mark.asyncio
async def test_subscription_failure_keeps_distinct_github_state(tmp_path):
    def handler(request):
        if request.url.path == "/copilot_internal/v2/token":
            return httpx.Response(
                403, json={"token": "private-error-token", "message": "private body"}
            )
        return upstream(request)

    service = CopilotService(tmp_path, transport=httpx.MockTransport(handler))
    start = await service.start_login()
    due(service)
    with pytest.raises(CopilotError, match="account_or_model_not_permitted") as error:
        await service.poll_login(start["login"]["attempt_id"])
    assert "private" not in str(error.value)
    assert (
        service.status()["github_authorized"] and not service.status()["authenticated"]
    )
