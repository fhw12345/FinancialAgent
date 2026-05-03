"""
User models for authentication and user management.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """Request model for creating a new user."""

    email: str | None = Field(None, description="Email address")
    phone_number: str | None = Field(None, description="Phone number with country code")
    wechat_openid: str | None = Field(None, description="WeChat OpenID")
    username: str = Field(..., description="Username for login (unique)")
    password: str | None = Field(None, description="Password (will be hashed)")


class User(BaseModel):
    """User model for database storage. Supports multiple auth methods."""

    user_id: str = Field(..., description="Unique user identifier")
    email: str | None = Field(None, description="Email address (unique if set)")
    phone_number: str | None = Field(None, description="Phone number (unique if set)")
    wechat_openid: str | None = Field(None, description="WeChat OpenID (unique if set)")
    username: str = Field(..., description="Username for login (unique)")
    password_hash: str | None = Field(None, description="Bcrypt password hash")
    email_verified: bool = Field(False, description="Email verification status")
    is_admin: bool = Field(False, description="Admin privileges flag")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: datetime | None = Field(None, description="Last login timestamp")
    feedbackVotes: list[str] = Field(
        default_factory=list,
        description="List of feedback item IDs this user has voted for",
    )

    # Credit system fields
    credits: float = Field(
        default=1000.0,
        description="User's current credit balance (1元 = 100 credits)",
    )
    total_tokens_used: int = Field(
        default=0, description="Lifetime total tokens consumed"
    )
    total_credits_spent: float = Field(
        default=0.0, description="Lifetime total credits spent"
    )

    @property
    def admin(self) -> bool:
        """
        Check if user has admin privileges.

        MVP: Hardcoded username check OR database flag.
        Future: Migrate to database-driven role system.
        """
        return self.is_admin

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_abc123",
                "email": "user@163.com",
                "phone_number": None,
                "wechat_openid": None,
                "username": "User_163",
                "is_admin": False,
                "created_at": "2025-10-05T10:00:00Z",
                "last_login": "2025-10-05T10:00:00Z",
            }
        }


class UserInDB(User):
    """User model with database ID."""

    id: str = Field(alias="_id")
