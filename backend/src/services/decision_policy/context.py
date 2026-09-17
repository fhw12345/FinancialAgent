"""Bind assessment writes to the canonical background run, not per-flow random IDs."""

import asyncio
from collections.abc import Coroutine, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_run_id: ContextVar[str | None] = ContextVar("assessment_run_id", default=None)


def create_run_task[
    T
](run_id: str, coroutine: Coroutine[Any, Any, T]) -> asyncio.Task[T]:
    with assessment_run(run_id):
        return asyncio.create_task(coroutine)


def current_run_id() -> str | None:
    return _run_id.get()


@contextmanager
def assessment_run(run_id: str) -> Iterator[None]:
    token = _run_id.set(run_id)
    try:
        yield
    finally:
        _run_id.reset(token)
