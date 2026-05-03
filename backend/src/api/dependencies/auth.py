"""
Shared authentication dependencies for all API endpoints.

W3a STUB: All authentication is bypassed for the private single-user fork.
- get_current_user_id / get_current_user / require_admin always succeed.
- Function signatures are preserved so existing Depends(...) call sites
  keep working unchanged. W3b will remove the Depends calls themselves.
- No JWT decode, no Redis lookup, no Mongo lookup is performed.
"""

import structlog
from fastapi import Depends, Header

from ...core.local_user import LOCAL_USER_ID, build_local_user
from ...database.mongodb import MongoDB
from ...database.redis import RedisCache
from ...database.repositories.user_repository import UserRepository
from ...models.user import User

logger = structlog.get_logger()


def get_mongodb() -> MongoDB:
    """Get MongoDB instance from app state."""
    from ...main import app

    mongodb: MongoDB = app.state.mongodb
    return mongodb


def get_redis_cache() -> RedisCache:
    """Get RedisCache instance from app state."""
    from ...main import app

    redis_cache: RedisCache = app.state.redis
    return redis_cache


def get_user_repository(mongodb: MongoDB = Depends(get_mongodb)) -> UserRepository:
    """Get user repository instance."""
    users_collection = mongodb.get_collection("users")
    return UserRepository(users_collection)


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
) -> None:
    """STUB: AuthService removed in W3c — kept as a no-op dependency for callers."""
    return None


async def get_current_user_id(
    authorization: str | None = Header(None),
) -> str:
    """STUB: always returns the fixed local user id."""
    return LOCAL_USER_ID


async def get_current_user(
    user_id: str = Depends(get_current_user_id),
) -> User:
    """STUB: always returns the fixed local User instance."""
    return build_local_user()


async def require_admin(
    x_admin_secret: str | None = Header(None),
    authorization: str | None = Header(None),
) -> None:
    """STUB: admin gate is always open for the local single-user fork."""
    return None
