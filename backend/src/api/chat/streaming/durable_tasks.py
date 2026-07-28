"""Cancellation-safe helpers for durable lifecycle tasks."""

import asyncio

import anyio


async def await_task_through_cancellation[
    ResultT
](task: asyncio.Task[ResultT],) -> tuple[ResultT, bool]:
    """Finish a durable task before reporting whether its waiter was cancelled."""
    try:
        return await asyncio.shield(task), False
    except asyncio.CancelledError:
        with anyio.CancelScope(shield=True):
            return await task, True
