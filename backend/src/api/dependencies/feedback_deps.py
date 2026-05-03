"""
Dependency injection for feedback platform endpoints.
"""

from fastapi import Depends, Header, HTTPException, status

from ...core.config import get_settings
from ...database.mongodb import MongoDB
from ...database.repositories.comment_repository import CommentRepository
from ...database.repositories.feedback_repository import FeedbackRepository
from ...database.repositories.user_repository import UserRepository
from ...services.feedback_export_service import FeedbackExportService
from ...services.feedback_service import FeedbackService
from ...services.oss_service import OSSService, get_oss_service


def get_mongodb() -> MongoDB:
    """Get MongoDB instance from app state."""
    from ...main import app

    mongodb: MongoDB = app.state.mongodb
    return mongodb


def get_feedback_repository(
    mongodb: MongoDB = Depends(get_mongodb),
) -> FeedbackRepository:
    """Get feedback repository instance."""
    feedback_collection = mongodb.get_collection("feedback_items")
    return FeedbackRepository(feedback_collection)


def get_comment_repository(
    mongodb: MongoDB = Depends(get_mongodb),
) -> CommentRepository:
    """Get comment repository instance."""
    comments_collection = mongodb.get_collection("comments")
    return CommentRepository(comments_collection)


def get_user_repository(mongodb: MongoDB = Depends(get_mongodb)) -> UserRepository:
    """Get user repository instance."""
    users_collection = mongodb.get_collection("users")
    return UserRepository(users_collection)


def get_feedback_service(
    feedback_repo: FeedbackRepository = Depends(get_feedback_repository),
    comment_repo: CommentRepository = Depends(get_comment_repository),
    user_repo: UserRepository = Depends(get_user_repository),
    mongodb: MongoDB = Depends(get_mongodb),
) -> FeedbackService:
    """Get feedback service instance."""
    return FeedbackService(feedback_repo, comment_repo, user_repo, mongodb)


def get_feedback_export_service(
    feedback_repo: FeedbackRepository = Depends(get_feedback_repository),
    comment_repo: CommentRepository = Depends(get_comment_repository),
    user_repo: UserRepository = Depends(get_user_repository),
) -> FeedbackExportService:
    """Get feedback export service instance."""
    return FeedbackExportService(feedback_repo, comment_repo, user_repo)


def get_oss_service_dep() -> OSSService:
    """Get OSS service instance for feedback image uploads."""
    settings = get_settings()
    return get_oss_service(
        access_key_id=settings.oss_access_key,
        access_key_secret=settings.oss_secret_key,
        endpoint=settings.oss_endpoint,
        bucket_name=settings.oss_bucket,
    )


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
) -> None:
    """STUB: AuthService removed in W3c — kept as a no-op dependency."""
    return None


async def get_current_user_id(
    authorization: str | None = Header(None),
) -> str:
    """STUB (W3a): always returns the fixed local user id."""
    from ...core.local_user import LOCAL_USER_ID

    return LOCAL_USER_ID


async def get_current_user_id_optional(
    authorization: str | None = Header(None),
) -> str | None:
    """STUB (W3a): always returns the fixed local user id."""
    from ...core.local_user import LOCAL_USER_ID

    return LOCAL_USER_ID
