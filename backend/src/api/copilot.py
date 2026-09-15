"""Local-only Copilot account controls. Never returns a credential/device secret."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..agent.copilot_chat_model import test_connection
from ..core.config import get_settings
from ..services.copilot.service import get_copilot_service
from .dependencies.rate_limit import limiter


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def local_action(request: Request) -> None:
    origin = request.headers.get("origin")
    if request.headers.get("x-financial-agent-local") != "1" or (
        origin is not None and origin not in get_settings().cors_origins
    ):
        raise HTTPException(403, "Local action header and trusted origin required")


router = APIRouter(
    prefix="/api/llm/copilot", tags=["llm"], dependencies=[Depends(no_store)]
)


class PollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_.-]+$")


def public_status() -> dict[str, Any]:
    return {
        **get_copilot_service().status(),
        "provider_enabled": get_settings().llm_provider == "github_copilot",
    }


@router.get("/status")
async def status() -> dict[str, Any]:
    return public_status()


@router.post("/login", dependencies=[Depends(local_action)])
@limiter.limit("10/minute")
async def login(request: Request) -> dict[str, Any]:
    await get_copilot_service().start_login()
    return public_status()


@router.post("/poll", dependencies=[Depends(local_action)])
async def poll(body: PollRequest) -> dict[str, Any]:
    await get_copilot_service().poll_login(body.attempt_id)
    return public_status()


@router.post("/models", dependencies=[Depends(local_action)])
async def models() -> dict[str, Any]:
    await get_copilot_service().models()
    return public_status()


@router.post("/model", dependencies=[Depends(local_action)])
async def select_model(body: ModelRequest) -> dict[str, Any]:
    await get_copilot_service().select_model(body.model_id)
    return public_status()


@router.post("/logout", dependencies=[Depends(local_action)])
async def logout() -> dict[str, Any]:
    get_copilot_service().logout()
    return public_status()


@router.post("/test", dependencies=[Depends(local_action)])
@limiter.limit("5/minute")
async def probe(request: Request) -> dict[str, Any]:
    return await test_connection()
