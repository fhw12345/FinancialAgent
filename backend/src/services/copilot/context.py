"""Immutable per-request routing snapshot, inherited by background asyncio tasks."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from types import MappingProxyType

from starlette.types import ASGIApp, Receive, Scope, Send

from ...core.llm_roles import ROLE_MODEL_FIELDS
from .catalog import CopilotAPI, CopilotModel
from .protocol import CopilotError
from .service import get_copilot_service


@dataclass(frozen=True)
class CopilotProfile:
    model: str
    generation: str
    role: str = "simple_chat"
    api: CopilotAPI = "openai-responses"
    routing_revision: int = 0


@dataclass(frozen=True)
class RoutingSnapshot:
    default: str
    generation: str
    revision: int
    roles: Mapping[str, str]
    models: Mapping[str, CopilotModel]


_profile: ContextVar[RoutingSnapshot | None] = ContextVar(
    "copilot_profile", default=None
)


def routing_snapshot() -> RoutingSnapshot:
    snapshot = _profile.get()
    if snapshot is None:
        state = get_copilot_service().store.read()
        snapshot = RoutingSnapshot(
            state.selected_model or "not-selected",
            state.generation,
            state.routing_revision,
            MappingProxyType(dict(state.role_models)),
            MappingProxyType({m.id: m.model_copy(deep=True) for m in state.models}),
        )
        _profile.set(snapshot)
    return snapshot


def current_profile(role: str = "simple_chat") -> CopilotProfile:
    if role not in ROLE_MODEL_FIELDS:
        raise CopilotError("unknown_model_role", 422)
    snapshot = routing_snapshot()
    model_id = snapshot.roles.get(role, snapshot.default)
    model = snapshot.models.get(model_id)
    return CopilotProfile(
        model_id,
        snapshot.generation,
        role,
        model.api if model else "openai-responses",
        snapshot.revision,
    )


@contextmanager
def probe_model(model_id: str, role: str) -> Iterator[None]:
    """Explicit connection test only; never changes persistent role/default config."""
    snapshot = routing_snapshot()
    if model_id not in snapshot.models or role not in ROLE_MODEL_FIELDS:
        raise CopilotError("model_or_role_not_available", 422)
    token = _profile.set(
        replace(snapshot, roles=MappingProxyType({**snapshot.roles, role: model_id}))
    )
    try:
        yield
    finally:
        _profile.reset(token)


class CopilotContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        token = _profile.set(None)
        try:
            await self.app(scope, receive, send)
        finally:
            _profile.reset(token)
