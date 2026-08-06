"""
Optional Langfuse observability wrapper.

If LANGFUSE_ENABLED=false (default) or langfuse package not installed,
@observe becomes a no-op decorator. This makes Langfuse a true optional dep.
"""

import os
import typing
from collections.abc import Callable
from functools import wraps
from typing import Any, cast

LANGFUSE_ENABLED = os.getenv("LANGFUSE_ENABLED", "false").lower() == "true"


def _noop_observe(*args: Any, **kwargs: Any) -> Callable[..., typing.Any]:
    """No-op replacement for @observe when Langfuse is disabled or unavailable."""
    if len(args) == 1 and callable(args[0]) and not kwargs:
        # Used as @observe without parens
        return cast(Callable[..., Any], args[0])

    def decorator(
        func: Callable[..., typing.Any],
    ) -> Callable[..., typing.Any]:
        @wraps(func)
        def wrapper(*a: Any, **kw: Any) -> Any:
            return func(*a, **kw)

        return wrapper

    return decorator


if LANGFUSE_ENABLED:
    try:
        from langfuse.decorators import observe as _real_observe

        observe: Callable[..., Any] = _real_observe
    except ImportError:
        observe = _noop_observe
else:
    observe = _noop_observe


__all__ = ["observe", "LANGFUSE_ENABLED"]
