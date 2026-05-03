"""
User repository for user authentication and profile management.
Handles CRUD operations for user collection.
"""

from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorCollection

from src.core.utils.date_utils import utcnow

from ...models.user import User, UserCreate


def hash_password(password: str) -> str:
    """STUB (W3c): password hashing removed. Stores a placeholder marker."""
    return f"stub:{len(password)}"

logger = structlog.get_logger()


class UserRepository:
    """Repository for user data access operations."""

    def __init__(self, collection: AsyncIOMotorCollection):
        """
        Initialize user repository.

        Args:
            collection: MongoDB collection for users
        """
        self.collection = collection

    async def create(self, user_create: UserCreate) -> User:
        """
        Create a new user.

        Args:
            user_create: User creation data

        Returns:
            Created user with generated ID
        """
        # Generate user_id (use MongoDB ObjectId pattern)
        import uuid

        user_id = f"user_{uuid.uuid4().hex[:12]}"

        # Auto-generate username from email or phone if not provided
        if user_create.username:
            username = user_create.username
        elif user_create.email:
            username = f"User_{user_create.email.split('@')[0][:8]}"
        elif user_create.phone_number:
            username = f"User_{user_create.phone_number[-4:]}"
        else:
            username = f"User_{user_id[:8]}"

        # Hash password if provided
        password_hash = None
        if user_create.password:
            password_hash = hash_password(user_create.password)

        user = User(
            user_id=user_id,
            email=user_create.email,
            phone_number=user_create.phone_number,
            wechat_openid=user_create.wechat_openid,
            username=username,
            password_hash=password_hash,
            email_verified=False,  # Will be set to True after email verification
            is_admin=False,  # Default to non-admin
            created_at=utcnow(),
            last_login=None,
        )

        # Convert to dict for MongoDB
        user_dict = user.model_dump()

        # Insert into database
        await self.collection.insert_one(user_dict)

        logger.info(
            "User created",
            user_id=user_id,
            email=user_create.email,
            phone=user_create.phone_number,
            has_password=password_hash is not None,
        )

        return user

    async def get_by_id(self, user_id: str) -> User | None:
        """
        Get user by ID.

        Args:
            user_id: User identifier

        Returns:
            User if found, None otherwise
        """
        user_dict = await self.collection.find_one({"user_id": user_id})

        if not user_dict:
            return None

        # Remove MongoDB _id field
        user_dict.pop("_id", None)

        return User(**user_dict)

    async def get_by_ids(self, user_ids: list[str]) -> dict[str, User]:
        """
        Batch fetch multiple users by IDs (solves N+1 query problem).

        Args:
            user_ids: List of user identifiers

        Returns:
            Dictionary mapping user_id to User object
        """
        if not user_ids:
            return {}

        # Fetch all users in one query
        cursor = self.collection.find({"user_id": {"$in": user_ids}})

        users_map = {}
        async for user_dict in cursor:
            user_dict.pop("_id", None)
            user = User(**user_dict)
            users_map[user.user_id] = user

        return users_map

    async def get_by_email(self, email: str) -> User | None:
        """
        Get user by email address.

        Args:
            email: Email address

        Returns:
            User if found, None otherwise
        """
        user_dict = await self.collection.find_one({"email": email})

        if not user_dict:
            return None

        # Remove MongoDB _id field
        user_dict.pop("_id", None)

        return User(**user_dict)

    async def get_by_phone(self, phone_number: str) -> User | None:
        """
        Get user by phone number.

        Args:
            phone_number: Phone number with country code

        Returns:
            User if found, None otherwise
        """
        user_dict = await self.collection.find_one({"phone_number": phone_number})

        if not user_dict:
            return None

        # Remove MongoDB _id field
        user_dict.pop("_id", None)

        return User(**user_dict)

    async def get_by_username(self, username: str) -> User | None:
        """
        Get user by username.

        Args:
            username: Username to search for

        Returns:
            User if found, None otherwise
        """
        user_dict = await self.collection.find_one({"username": username})

        if not user_dict:
            return None

        # Remove MongoDB _id field
        user_dict.pop("_id", None)

        return User(**user_dict)

    async def update_last_login(self, user_id: str) -> User | None:
        """
        Update user's last login timestamp.

        Args:
            user_id: User identifier

        Returns:
            Updated user if found, None otherwise
        """
        result = await self.collection.find_one_and_update(
            {"user_id": user_id},
            {"$set": {"last_login": utcnow()}},
            return_document=True,  # Return updated document
        )

        if not result:
            return None

        # Remove MongoDB _id field
        result.pop("_id", None)

        logger.info("User last_login updated", user_id=user_id)

        return User(**result)

    async def add_vote(self, user_id: str, item_id: str, session: Any = None) -> bool:
        """
        Add a feedback item ID to user's voted items list.

        Args:
            user_id: User identifier
            item_id: Feedback item identifier to add
            session: Optional MongoDB session for transactions

        Returns:
            True if successful, False if user not found
        """
        result = await self.collection.update_one(
            {"user_id": user_id},
            {"$addToSet": {"feedbackVotes": item_id}},  # $addToSet prevents duplicates
            session=session,
        )

        if result.matched_count == 0:
            logger.warning("Failed to add vote - user not found", user_id=user_id)
            return False

        logger.info("Vote added to user", user_id=user_id, item_id=item_id)
        return True

    async def remove_vote(
        self, user_id: str, item_id: str, session: Any = None
    ) -> bool:
        """
        Remove a feedback item ID from user's voted items list.

        Args:
            user_id: User identifier
            item_id: Feedback item identifier to remove
            session: Optional MongoDB session for transactions

        Returns:
            True if successful, False if user not found
        """
        result = await self.collection.update_one(
            {"user_id": user_id},
            {"$pull": {"feedbackVotes": item_id}},
            session=session,
        )

        if result.matched_count == 0:
            logger.warning("Failed to remove vote - user not found", user_id=user_id)
            return False

        logger.info("Vote removed from user", user_id=user_id, item_id=item_id)
        return True

    async def get_user_votes(self, user_id: str) -> list[str]:
        """
        Get all feedback item IDs that a user has voted for.

        Args:
            user_id: User identifier

        Returns:
            List of feedback item IDs (empty list if user not found or no votes)
        """
        user_dict = await self.collection.find_one(
            {"user_id": user_id},
            {"feedbackVotes": 1},  # Only fetch feedbackVotes field
        )

        if not user_dict:
            return []

        votes: list[str] = user_dict.get("feedbackVotes", [])
        return votes

    async def deduct_credits(
        self,
        user_id: str,
        cost: float,
        tokens: int,
        session: Any = None,
    ) -> User | None:
        """
        Deduct credits from user balance and update lifetime stats.
        Uses atomic operations to prevent race conditions.

        Args:
            user_id: User identifier
            cost: Credits to deduct
            tokens: Tokens consumed (for lifetime tracking)
            session: Optional MongoDB session for transactions

        Returns:
            Updated user if successful, None if user not found
        """
        result = await self.collection.find_one_and_update(
            {"user_id": user_id},
            {
                "$inc": {
                    "credits": -cost,  # Subtract from balance
                    "total_credits_spent": cost,  # Add to lifetime total
                    "total_tokens_used": tokens,  # Add to lifetime tokens
                }
            },
            return_document=True,
            session=session,
        )

        if not result:
            logger.warning("Failed to deduct credits - user not found", user_id=user_id)
            return None

        # Remove MongoDB _id field
        result.pop("_id", None)

        logger.info(
            "Credits deducted",
            user_id=user_id,
            cost=cost,
            tokens=tokens,
            new_balance=result.get("credits"),
        )

        return User(**result)

    async def adjust_credits(
        self, user_id: str, amount: float, reason: str
    ) -> User | None:
        """
        Manually adjust user credits (admin operation for refunds/corrections).

        Args:
            user_id: User identifier
            amount: Credits to add (positive) or deduct (negative)
            reason: Reason for adjustment (for audit trail)

        Returns:
            Updated user if successful, None if user not found
        """
        result = await self.collection.find_one_and_update(
            {"user_id": user_id},
            {"$inc": {"credits": amount}},
            return_document=True,
        )

        if not result:
            logger.warning("Failed to adjust credits - user not found", user_id=user_id)
            return None

        # Remove MongoDB _id field
        result.pop("_id", None)

        logger.info(
            "Credits adjusted",
            user_id=user_id,
            amount=amount,
            reason=reason,
            new_balance=result.get("credits"),
        )

        return User(**result)

    async def get_active_users_with_portfolios(self) -> list[dict[str, Any]]:
        """
        Get all active users who have portfolio orders or watchlist items.

        This is used by the portfolio analysis agent to determine which users
        need automated analysis.

        Architecture: Alpaca is the single source of truth for holdings.
        Users are identified by:
        1. Having portfolio orders (orders placed via MCP tools)
        2. OR having watchlist items (symbols being tracked)

        Returns:
            List of user dictionaries with user_id and username
        """
        # Use aggregation to find users who have either orders or watchlist items
        pipeline = [
            {
                "$lookup": {
                    "from": "portfolio_orders",
                    "localField": "user_id",
                    "foreignField": "user_id",
                    "as": "orders",
                }
            },
            {
                "$lookup": {
                    "from": "watchlist",
                    "localField": "user_id",
                    "foreignField": "user_id",
                    "as": "watchlist",
                }
            },
            {
                "$match": {
                    "$or": [
                        {"orders": {"$ne": []}},  # Has portfolio orders
                        {"watchlist": {"$ne": []}},  # Has watchlist items
                    ]
                }
            },
            {
                "$project": {
                    "user_id": 1,
                    "username": 1,
                    "_id": 0,
                }
            },
        ]

        users = []
        async for user_doc in self.collection.aggregate(pipeline):
            users.append(user_doc)

        logger.info(
            "Found users with portfolios",
            count=len(users),
        )

        return users
