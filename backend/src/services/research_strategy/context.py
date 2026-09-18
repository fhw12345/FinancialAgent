"""Task-local immutable strategy inputs and actual prompt receipts; never mutate shared agents."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from ...models.research_strategy import StrategyReview

_current: ContextVar[dict[str, StrategyReview] | None] = ContextVar(
    "research_strategy", default=None
)


@contextmanager
def strategy_scope(reviews: dict[str, StrategyReview]) -> Iterator[None]:
    token = _current.set(reviews if reviews else None)
    try:
        yield
    finally:
        _current.reset(token)


def current() -> dict[str, StrategyReview]:
    return _current.get() or {}


def phase1_prompt(symbol: str) -> str | None:
    from ...agent.prompt_registry import get_prompt

    review = current().get(symbol)
    if review is None:
        return None
    spec = get_prompt("strategy-fundamental")
    review.prompt_versions[spec.prompt_id] = spec.versioned_id
    return spec.render(
        review=json.dumps(review.model_dump(mode="json"), ensure_ascii=False)
    )
