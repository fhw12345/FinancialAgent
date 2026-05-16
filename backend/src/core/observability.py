"""
Optional Langfuse observability wrapper.

If LANGFUSE_ENABLED=false (default) or langfuse package not installed,
@observe becomes a no-op decorator. This makes Langfuse a true optional dep.
"""

import os
from collections.abc import Callable
from functools import wraps
from typing import Any

LANGFUSE_ENABLED = os.getenv("LANGFUSE_ENABLED", "false").lower() == "true"


def _noop_observe(*args: Any, **kwargs: Any) -> Callable:
    """No-op replacement for @observe when Langfuse is disabled or unavailable."""
    if len(args) == 1 and callable(args[0]) and not kwargs:
        # Used as @observe without parens
        return args[0]

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*a: Any, **kw: Any) -> Any:
            return func(*a, **kw)

        return wrapper

    return decorator


if LANGFUSE_ENABLED:
    try:
        from langfuse.decorators import (
            observe as _real_observe,  # type: ignore[import-not-found]
        )

        observe = _real_observe
    except ImportError:
        observe = _noop_observe
else:
    observe = _noop_observe


__all__ = ["observe", "LANGFUSE_ENABLED"]
