"""Shared local storage dependencies."""

from ...database.mongodb import MongoDB
from ...database.redis import RedisCache


def get_mongodb() -> MongoDB:
    """Get the application MongoDB connection."""
    from ...main import app

    mongodb: MongoDB = app.state.mongodb
    return mongodb


def get_redis_cache() -> RedisCache:
    """Get the application Redis connection."""
    from ...main import app

    redis_cache: RedisCache = app.state.redis
    return redis_cache
