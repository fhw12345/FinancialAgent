"""
Local single-user stub for the private fork.

W3a: Auth has been stubbed. All Depends(get_current_user) calls now resolve
to this fixed user. Real JWT/Redis/Mongo auth paths are bypassed but the
function signatures in api/dependencies/auth.py are preserved so call sites
can be deleted mechanically in W3b.
"""

from datetime import datetime

from ..models.user import User

LOCAL_USER_ID = "local"
LOCAL_USERNAME = "local"
LOCAL_EMAIL = "local@localhost"


def build_local_user() -> User:
    """Return a fixed local User instance with admin privileges."""
    return User(
        user_id=LOCAL_USER_ID,
        email=LOCAL_EMAIL,
        phone_number=None,
        wechat_openid=None,
        username=LOCAL_USERNAME,
        password_hash=None,
        email_verified=True,
        is_admin=True,
        created_at=datetime(2026, 1, 1),
        last_login=datetime(2026, 1, 1),
        feedbackVotes=[],
        credits=1_000_000.0,
        total_tokens_used=0,
        total_credits_spent=0.0,
    )
