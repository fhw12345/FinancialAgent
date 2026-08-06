"""
Rate limiting dependencies for API endpoints.

Uses SlowAPI's in-process storage for the local single-user service.
"""

from collections.abc import Callable
from typing import cast

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/minute"],
)


# Rate limit decorators for different endpoint types
def rate_limit_standard[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """
    Standard rate limit for read operations.

    Allows 60 requests per minute (1 per second).

    Usage:
        @router.get("/endpoint")
        @rate_limit_standard
        async def endpoint():
            pass
    """
    return cast(Callable[P, R], limiter.limit("60/minute")(func))


def rate_limit_expensive[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """
    Restrictive rate limit for expensive operations (external API calls).

    Allows 10 requests per minute.

    Usage:
        @router.get("/portfolio/history")
        @rate_limit_expensive
        async def get_portfolio_history():
            pass
    """
    return cast(Callable[P, R], limiter.limit("10/minute")(func))


def rate_limit_critical[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """
    Very restrictive rate limit for critical operations (LLM, trading).

    Allows 2 requests per minute.

    Usage:
        @router.post("/watchlist/analyze")
        @rate_limit_critical
        async def trigger_analysis():
            pass
    """
    return cast(Callable[P, R], limiter.limit("2/minute")(func))


def rate_limit_write[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """
    Moderate rate limit for write operations.

    Allows 30 requests per minute.

    Usage:
        @router.post("/watchlist")
        @rate_limit_write
        async def add_to_watchlist():
            pass
    """
    return cast(Callable[P, R], limiter.limit("30/minute")(func))
