"""Durable Deep verdict signal persistence."""

import asyncio
from typing import Any

from ....models.run_identity import message_id_for_run
from .durable_tasks import await_task_through_cancellation


async def persist_completed_verdict(
    *,
    agent: Any,
    symbol: str,
    verdict: object,
    chat_id: str,
    run_id: str,
) -> None:
    """Persist a completed Deep verdict and propagate cancellation afterward."""
    persist_verdict = getattr(agent, "persist_verdict_decision", None)
    if not isinstance(verdict, dict) or not callable(persist_verdict):
        return
    signal_task = asyncio.create_task(
        persist_verdict(
            symbol=symbol,
            verdict=verdict,
            chat_id=chat_id,
            run_id=run_id,
            message_id=message_id_for_run(run_id),
        )
    )
    _, cancelled = await await_task_through_cancellation(signal_task)
    if cancelled:
        raise asyncio.CancelledError
