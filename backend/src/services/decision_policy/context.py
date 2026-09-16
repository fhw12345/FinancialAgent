"""Bind assessment writes to the canonical background run, not per-flow random IDs."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_run_id: ContextVar[str | None] = ContextVar("assessment_run_id", default=None)


def current_run_id() -> str | None:
    return _run_id.get()


@contextmanager
def assessment_run(run_id: str) -> Iterator[None]:
    token = _run_id.set(run_id)
    try:
        yield
    finally:
        _run_id.reset(token)
