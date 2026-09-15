"""Request-local model/account pinning, inherited by background asyncio tasks."""

from contextvars import ContextVar
from dataclasses import dataclass

from starlette.types import ASGIApp, Receive, Scope, Send

from .service import get_copilot_service


@dataclass(frozen=True)
class CopilotProfile:
    model: str
    generation: str


_profile: ContextVar[CopilotProfile | None] = ContextVar(
    "copilot_profile", default=None
)


def current_profile() -> CopilotProfile:
    existing = _profile.get()
    if existing is not None:
        return existing
    state = get_copilot_service().store.read()
    profile = CopilotProfile(state.selected_model or "not-selected", state.generation)
    _profile.set(profile)
    return profile


class CopilotContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        token = _profile.set(None)
        try:
            await self.app(scope, receive, send)
        finally:
            _profile.reset(token)
