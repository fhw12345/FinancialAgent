"""Shared cancellation helpers for chat streaming handlers."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

import anyio
import structlog
from fastapi import Request

from ....core.utils.date_utils import utcnow
from ....models.message import MessageMetadata
from ....services.agent_run_service import AgentRunService
from ....services.chat_service import ChatService

logger = structlog.get_logger()


class ClientDisconnected(Exception):
    """Raised when the ASGI request reports a disconnected client."""


async def raise_if_disconnected(request: Request | None) -> None:
    """Raise when the browser has closed or aborted the response stream."""
    if request is not None and await request.is_disconnected():
        raise ClientDisconnected()


async def cancel_and_await(task: asyncio.Task[Any] | None) -> None:
    """Cancel one unfinished task and await its termination."""
    if task is None or task.done():
        return
    with anyio.CancelScope(shield=True):
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def await_task_completion(task: asyncio.Future[Any] | None) -> None:
    """Await a shielded task without cancelling its underlying operation."""
    if task is None:
        return
    try:
        with anyio.CancelScope(shield=True):
            await task
    except asyncio.CancelledError:
        with anyio.CancelScope(shield=True):
            with suppress(asyncio.CancelledError):
                await task
    except Exception:
        logger.exception("Shielded terminal persistence failed")


async def await_task_or_disconnect(
    task: asyncio.Task[Any],
    request: Request | None,
    *,
    poll_seconds: float = 0.1,
) -> Any:
    """Wait for a task while periodically checking client connectivity."""
    while not task.done():
        await raise_if_disconnected(request)
        await asyncio.wait({task}, timeout=poll_seconds)
    return await task


async def await_disconnect_grace(
    request: Request | None,
    *,
    grace_seconds: float = 0.15,
) -> None:
    """Allow a final Stop/connection-close signal to arrive before completion."""
    deadline = asyncio.get_running_loop().time() + grace_seconds
    while asyncio.get_running_loop().time() < deadline:
        await raise_if_disconnected(request)
        await asyncio.sleep(0.02)
    await raise_if_disconnected(request)


async def persist_cancelled_run(
    *,
    chat_service: ChatService,
    chat_id: str | None,
    user_id: str,
    run_id: str,
    language: str,
    agent_type: str,
    route_metadata: dict[str, str] | None,
    partial_content: str = "",
    extra_raw_data: dict[str, Any] | None = None,
    run_service: AgentRunService | None = None,
    cancel_reason: str = "client_cancelled",
) -> None:
    """Persist a user-visible cancellation marker and durable run status."""
    cancelled_at = utcnow()
    cancellation_text = "请求已取消。" if language == "zh-CN" else "Request cancelled."
    content = (
        f"{partial_content.rstrip()}\n\n{cancellation_text}"
        if partial_content.strip()
        else cancellation_text
    )
    raw_data: dict[str, Any] = {
        "agent_type": agent_type,
        "route_selected": route_metadata,
        **(extra_raw_data or {}),
    }

    try:
        with anyio.CancelScope(shield=True):
            if run_service is not None:
                cancelled_run = await run_service.cancel(
                    run_id,
                    cancel_reason=cancel_reason,
                )
                if cancelled_run is None:
                    return
            if chat_id is None:
                return
            await chat_service.upsert_run_message(
                chat_id=chat_id,
                run_id=run_id,
                content=content,
                metadata=MessageMetadata(
                    run_id=run_id,
                    run_status="cancelled",
                    cancelled_at=cancelled_at,
                    raw_data=raw_data,
                ),
            )
    except Exception:
        logger.exception(
            "Failed to persist cancelled run",
            chat_id=chat_id,
            agent_type=agent_type,
        )
