"""Device login, subscription token refresh and permitted model selection.

One FastAPI worker owns this service. Async single-flight serializes network
refresh/poll operations; SQLite CAS also prevents stale writes after logout.
"""

import asyncio
import math
import time
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from pydantic import SecretStr

from ...core.llm_roles import BALANCED_MODELS, ROLE_LABELS, ROLE_MODEL_FIELDS
from .catalog import CopilotModel, parse_catalog
from .protocol import (
    CLIENT_ID,
    DEFAULT_API,
    GITHUB,
    HEADERS,
    TOKEN_URL,
    CopilotError,
    api_from_token,
    check_response,
)
from .store import CopilotStore, CredentialState, DeviceAttempt


class CopilotService:
    def __init__(
        self, directory: Path, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.store = CopilotStore(directory)
        self.transport = transport
        self._lock = asyncio.Lock()

    def client(self, timeout: float = 20) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self.transport, timeout=timeout, follow_redirects=False
        )

    async def _json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with self.client() as client:
                response = await client.request(method, url, **kwargs)
                check_response(response)
                data = response.json()
                if not isinstance(data, dict):
                    raise CopilotError("invalid_upstream_response")
                return data
        except httpx.TimeoutException:
            raise CopilotError("upstream_timeout") from None
        except httpx.TransportError:
            raise CopilotError("upstream_unavailable") from None
        except ValueError:
            raise CopilotError("invalid_upstream_response") from None

    def status(self) -> dict[str, Any]:
        state = self.store.read()
        device = state.device
        login = None
        if device:
            pending = device.state == "pending" and device.expires_at > time.time()
            login = {
                "attempt_id": device.attempt_id,
                "state": device.state if device.expires_at > time.time() else "expired",
                "user_code": device.user_code if pending else "",
                "verification_uri": "https://github.com/login/device",
                "expires_at": device.expires_at,
                "interval": device.interval,
            }
        return {
            "github_authorized": bool(state.github_token.get_secret_value()),
            "authenticated": bool(
                state.github_token.get_secret_value()
                and state.access_token.get_secret_value()
            ),
            "selected_model": state.selected_model,
            "models": [model.model_dump() for model in state.models],
            "role_models": dict(state.role_models),
            "routing_revision": state.routing_revision,
            "recommended_role_models": dict(BALANCED_MODELS),
            "roles": [
                {"id": role, "label": label} for role, label in ROLE_LABELS.items()
            ],
            "login": login,
        }

    async def start_login(self) -> dict[str, Any]:
        async with self._lock:
            state = self.store.read()
            if (
                state.device
                and state.device.state == "pending"
                and state.device.expires_at > time.time()
            ):
                return self.status()
            # Replacing an account is explicit. Invalidate every old run binding.
            state = CredentialState(
                revision=state.revision, routing_revision=state.routing_revision + 1
            )
            self.store.save(state)
            data = await self._json(
                "POST",
                GITHUB + "/login/device/code",
                headers=HEADERS,
                data={"client_id": CLIENT_ID, "scope": "read:user"},
            )
            code, user_code = data.get("device_code"), data.get("user_code")
            expiry, interval = data.get("expires_in"), data.get("interval", 5)
            if (
                not isinstance(code, str)
                or not code
                or not isinstance(user_code, str)
                or not user_code
                or data.get("verification_uri") != "https://github.com/login/device"
                or not isinstance(expiry, (float, int))
                or not 0 < expiry <= 3600
                or not isinstance(interval, (float, int))
                or not 1 <= interval <= 60
            ):
                raise CopilotError("invalid_device_response")
            state.device = DeviceAttempt(
                attempt_id=uuid4().hex,
                device_code=SecretStr(code),
                user_code=user_code,
                expires_at=time.time() + expiry,
                interval=interval,
                next_poll=time.time() + interval,
            )
            self.store.save(state)
            return self.status()

    async def poll_login(self, attempt_id: str) -> dict[str, Any]:
        async with self._lock:
            state = self.store.read()
            device = state.device
            if not device or device.attempt_id != attempt_id:
                raise CopilotError("login_attempt_changed", 409)
            if device.state != "pending":
                return self.status()
            now = time.time()
            if device.expires_at <= now:
                device.state = "expired"
                device.device_code = SecretStr("")
                self.store.save(state)
                return self.status()
            if now < device.next_poll:
                return self.status()
            device.next_poll = now + device.interval
            self.store.save(state)
            data = await self._json(
                "POST",
                GITHUB + "/login/oauth/access_token",
                headers=HEADERS,
                data={
                    "client_id": CLIENT_ID,
                    "device_code": device.device_code.get_secret_value(),
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
            error = data.get("error")
            if error in ("authorization_pending", "slow_down"):
                if error == "slow_down":
                    device.interval = min(device.interval + 5, 120)
                device.next_poll = time.time() + device.interval
                self.store.save(state)
                return self.status()
            token = data.get("access_token")
            if error or not isinstance(token, str) or not token:
                device.state = (
                    "denied"
                    if error == "access_denied"
                    else "expired" if error == "expired_token" else "failed"
                )
                device.device_code = SecretStr("")
                self.store.save(state)
                return self.status()
            state.github_token = SecretStr(token)
            state.device = None
            self.store.save(state)
            await self._refresh(state)
            return self.status()

    async def _refresh(self, state: CredentialState) -> CredentialState:
        if not state.github_token.get_secret_value():
            raise CopilotError("authorization_required", 401)
        try:
            data = await self._json(
                "GET",
                TOKEN_URL,
                headers={
                    **HEADERS,
                    "Authorization": "Bearer " + state.github_token.get_secret_value(),
                },
            )
        except CopilotError as error:
            if error.status_code == 401:
                # Only clear the generation which actually failed authorization.
                current = self.store.read()
                if current.generation == state.generation:
                    self.store.clear()
            raise
        token, expires = data.get("token"), data.get("expires_at")
        if (
            not isinstance(token, str)
            or not token
            or not isinstance(expires, (int, float))
            or not math.isfinite(expires)
            or expires <= time.time()
        ):
            raise CopilotError("invalid_subscription_token")
        state.base_url = api_from_token(token)
        state.access_token = SecretStr(token)
        state.expires_at = expires
        state.issued_at = time.time()
        state.token_revision += 1
        self.store.save(state)
        return state

    async def _authorized(self, *, force: bool = False) -> CredentialState:
        state = self.store.read()
        if (
            force
            or not state.access_token.get_secret_value()
            or state.expires_at
            <= time.time() + min(300, max(0, (state.expires_at - state.issued_at) / 2))
        ):
            state = await self._refresh(state)
        return state

    async def authorization(
        self,
        *,
        generation: str | None = None,
        force: bool = False,
        rejected_revision: int | None = None,
    ) -> CredentialState:
        async with self._lock:
            state = self.store.read()
            if generation is not None and state.generation != generation:
                raise CopilotError("session_changed", 409)
            if (
                rejected_revision is not None
                and state.token_revision != rejected_revision
            ):
                force = False  # A peer has already refreshed the rejected token.
            return await self._authorized(force=force)

    async def models(self, *, refresh: bool = True) -> list[CopilotModel]:
        async with self._lock:
            state = await self._authorized()
            if not refresh and state.catalog_at > time.time() - 300:
                return state.models
            for attempt in range(2):
                try:
                    data = await self._json(
                        "GET",
                        state.base_url + "/models",
                        headers={
                            **HEADERS,
                            "Authorization": "Bearer "
                            + state.access_token.get_secret_value(),
                        },
                    )
                    break
                except CopilotError as error:
                    if error.status_code != 401 or attempt:
                        raise
                    state = await self._authorized(force=True)
            state.models = parse_catalog(data, individual=state.base_url == DEFAULT_API)
            state.catalog_at = time.time()
            self.store.save(state)
            return state.models

    async def select_model(
        self, model_id: str, expected_revision: int | None = None
    ) -> dict[str, Any]:
        models = await self.models()
        async with self._lock:
            state = self.store.read()
            if not state.github_token.get_secret_value():
                raise CopilotError("authorization_required", 401)
            if model_id not in {model.id for model in models} or model_id not in {
                model.id for model in state.models
            }:
                raise CopilotError("model_not_available", 422)
            if (
                expected_revision is not None
                and expected_revision != state.routing_revision
            ):
                raise CopilotError("routing_changed_reload", 409)
            if state.selected_model != model_id:
                state.routing_revision += 1
            state.selected_model = model_id
            self.store.save(state)
            return self.status()

    async def update_routing(
        self, role_models: dict[str, str], expected_revision: int
    ) -> dict[str, Any]:
        if set(role_models) - ROLE_MODEL_FIELDS.keys():
            raise CopilotError("unknown_model_role", 422)
        models = await self.models()
        async with self._lock:
            state = self.store.read()
            if expected_revision != state.routing_revision:
                raise CopilotError("routing_changed_reload", 409)
            available = {m.id for m in models} & {m.id for m in state.models}
            if (
                not state.github_token.get_secret_value()
                or not set(role_models.values()) <= available
            ):
                raise CopilotError("model_not_available", 422)
            state.role_models = dict(role_models)
            state.routing_revision += 1
            self.store.save(state)
            return self.status()

    def logout(self) -> dict[str, Any]:
        # No await/lock: cancellation immediately invalidates in-flight CAS writes.
        self.store.clear()
        return self.status()


@lru_cache(maxsize=1)
def get_copilot_service() -> CopilotService:
    from ...core.config import get_settings

    return CopilotService(Path(get_settings().copilot_state_dir))
