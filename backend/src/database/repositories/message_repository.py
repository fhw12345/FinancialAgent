"""
Message repository for conversation history.
Handles CRUD operations for message collection.
"""

from typing import TYPE_CHECKING

import structlog
from motor.motor_asyncio import AsyncIOMotorCollection

from src.core.utils.date_utils import utcnow
from src.services.persistence_translator import translate_for_persistence

from ...models.message import Message, MessageCreate, MessageMetadata

if TYPE_CHECKING:
    from src.database.redis import RedisCache

logger = structlog.get_logger()


class MessageRepository:
    """Repository for message data access operations."""

    def __init__(
        self,
        collection: AsyncIOMotorCollection,
        redis_cache: "RedisCache",
    ):
        """
        Initialize message repository.

        Args:
            collection: MongoDB collection for messages
            redis_cache: Redis cache used by the write-time translator
        """
        self.collection = collection
        self._redis = redis_cache

    async def ensure_indexes(self) -> None:
        """
        Create indexes for optimal query performance.
        Called during application startup.

        Note: Uses existing index names to avoid conflicts with previously created indexes.
        """
        await self.collection.create_index("chat_id", name="chat_id_1")
        await self.collection.create_index(
            [("chat_id", 1), ("timestamp", 1)], name="idx_chat_messages"
        )
        await self.collection.create_index(
            "metadata.transaction_id", sparse=True, name="metadata.transaction_id_1"
        )

        logger.info("Message indexes ensured")

    async def create(self, message_create: MessageCreate) -> Message:
        """
        Create a new message with zh-CN translation persisted alongside.

        Args:
            message_create: Message creation data

        Returns:
            Created message with generated ID
        """
        # Generate message_id
        import uuid

        message_id = f"msg_{uuid.uuid4().hex[:12]}"

        # Translate user-visible English to zh-CN before insert.
        # Failure path: returns {"content_zh": None}; English still persists.
        translations = await translate_for_persistence(
            {"content": message_create.content},
            redis_cache=self._redis,
        )

        message = Message(
            message_id=message_id,
            chat_id=message_create.chat_id,
            role=message_create.role,
            content=message_create.content,
            content_zh=translations.get("content_zh"),
            source=message_create.source,
            timestamp=utcnow(),
            metadata=message_create.metadata,
            tool_call=message_create.tool_call,
        )

        # Convert to dict for MongoDB
        message_dict = message.model_dump()

        # Insert into database
        await self.collection.insert_one(message_dict)

        logger.info(
            "Message created",
            message_id=message_id,
            chat_id=message_create.chat_id,
            source=message_create.source,
            translated=translations.get("content_zh") is not None,
        )

        return message

    async def get_by_chat(
        self,
        chat_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Message]:
        """
        Get messages for a chat.

        Args:
            chat_id: Chat identifier
            limit: Maximum number of messages to return
            offset: Number of messages to skip (for pagination)

        Returns:
            List of messages sorted by timestamp ascending
        """
        cursor = (
            self.collection.find({"chat_id": chat_id})
            .sort("timestamp", 1)  # Ascending (oldest first)
            .skip(offset)
            .limit(limit)
        )

        messages = []
        async for message_dict in cursor:
            # Remove MongoDB _id field
            message_dict.pop("_id", None)
            messages.append(Message(**message_dict))

        return messages

    async def get_by_chat_reverse(
        self,
        chat_id: str,
        limit: int = 100,
    ) -> list[Message]:
        """
        Get messages for a chat in reverse chronological order.
        Useful for finding recent analysis messages.

        Args:
            chat_id: Chat identifier
            limit: Maximum number of messages to return

        Returns:
            List of messages sorted by timestamp descending (newest first)
        """
        cursor = (
            self.collection.find({"chat_id": chat_id})
            .sort("timestamp", -1)  # Descending (newest first)
            .limit(limit)
        )

        messages = []
        async for message_dict in cursor:
            # Remove MongoDB _id field
            message_dict.pop("_id", None)
            messages.append(Message(**message_dict))

        return messages

    async def get_tool_messages(
        self,
        chat_id: str,
        tool_name: str | None = None,
        symbol: str | None = None,
        limit: int = 20,
    ) -> list[Message]:
        """
        Get tool output messages for a chat.
        Optionally filter by tool name and/or symbol.

        Args:
            chat_id: Chat identifier
            tool_name: Optional tool name to filter by (e.g., "fibonacci", "stochastic")
            symbol: Optional symbol to filter by
            limit: Maximum number of messages to return

        Returns:
            List of tool messages sorted by timestamp descending
        """
        # Build query
        query = {
            "chat_id": chat_id,
            "source": "tool",
        }

        if tool_name:
            query["metadata.selected_tool"] = tool_name

        if symbol:
            query["metadata.symbol"] = symbol

        cursor = self.collection.find(query).sort("timestamp", -1).limit(limit)

        messages = []
        async for message_dict in cursor:
            # Remove MongoDB _id field
            message_dict.pop("_id", None)
            messages.append(Message(**message_dict))

        return messages

    async def delete_by_chat(self, chat_id: str) -> int:
        """
        Delete all messages for a chat (cascade delete).

        Args:
            chat_id: Chat identifier

        Returns:
            Number of messages deleted
        """
        result = await self.collection.delete_many({"chat_id": chat_id})
        deleted_count: int = result.deleted_count

        logger.info("Messages deleted", chat_id=chat_id, count=deleted_count)

        return deleted_count

    async def count_by_chat(self, chat_id: str) -> int:
        """
        Count messages in a chat.

        Args:
            chat_id: Chat identifier

        Returns:
            Message count
        """
        count: int = await self.collection.count_documents({"chat_id": chat_id})
        return count

    async def get_by_transaction_id(self, transaction_id: str) -> Message | None:
        """
        Get message by transaction ID (for reconciliation).

        Args:
            transaction_id: Transaction identifier from metadata

        Returns:
            Message if found, None otherwise
        """
        message_dict = await self.collection.find_one(
            {"metadata.transaction_id": transaction_id}
        )

        if not message_dict:
            return None

        # Remove MongoDB _id field
        message_dict.pop("_id", None)

        return Message(**message_dict)

    async def get_analysis_messages(
        self,
        user_id: str | None = None,
        symbol: str | None = None,
        analysis_id: str | None = None,
        limit: int = 100,
    ) -> list[Message]:
        """Get analysis messages with optional filters. user_id ignored."""
        # Build query
        query: dict = {
            "source": {
                "$in": ["tool", "llm"]
            },  # Analysis messages from tools or LLM (watchlist)
        }

        if symbol:
            query["metadata.symbol"] = symbol

        if analysis_id:
            query["metadata.analysis_id"] = analysis_id

        # TODO: Add user_id filter (requires JOIN with chats collection)
        # For now, filter by symbol which is most common use case

        cursor = self.collection.find(query).sort("timestamp", -1).limit(limit)

        messages = []
        async for message_dict in cursor:
            # Remove MongoDB _id field
            message_dict.pop("_id", None)
            messages.append(Message(**message_dict))

        logger.info(
            "Analysis messages queried",
            symbol=symbol,
            analysis_id=analysis_id,
            count=len(messages),
        )

        return messages

    async def update_metadata(
        self, message_id: str, metadata: MessageMetadata
    ) -> Message | None:
        """
        Update message metadata.

        Args:
            message_id: Message ID to update
            metadata: New metadata to set

        Returns:
            Updated message or None if not found
        """
        result = await self.collection.find_one_and_update(
            {"message_id": message_id},
            {"$set": {"metadata": metadata.model_dump(exclude_none=True)}},
            return_document=True,
        )

        if result:
            result.pop("_id", None)
            logger.info("Message metadata updated", message_id=message_id)
            return Message(**result)

        logger.warning("Message not found for metadata update", message_id=message_id)
        return None

    async def update_metadata_batch(
        self, updates: list[tuple[str, MessageMetadata]]
    ) -> int:
        """
        Batch update message metadata.

        Uses bulk_write() for efficient bulk updates, reducing
        database round trips from N to 1.

        Args:
            updates: List of (message_id, metadata) tuples

        Returns:
            Number of messages modified
        """
        if not updates:
            return 0

        from pymongo import UpdateOne

        operations = [
            UpdateOne(
                {"message_id": msg_id},
                {"$set": {"metadata": meta.model_dump(exclude_none=True)}},
            )
            for msg_id, meta in updates
        ]

        result = await self.collection.bulk_write(operations)

        logger.info(
            "Message metadata batch updated",
            matched=result.matched_count,
            modified=result.modified_count,
        )

        return result.modified_count

    async def delete_old_messages_keep_recent(
        self,
        chat_id: str,
        keep_count: int,
        exclude_summaries: bool = True,
    ) -> int:
        """
        Delete old messages from a chat, keeping the most recent N messages.

        Used during context compaction to clean up old analysis history
        after a summary has been persisted.

        Args:
            chat_id: Chat identifier
            keep_count: Number of recent messages to keep
            exclude_summaries: If True, never delete summary messages (is_summary=True)

        Returns:
            Number of messages deleted
        """
        # First, get the message_ids of recent messages to keep
        keep_query = {"chat_id": chat_id}

        cursor = (
            self.collection.find(keep_query, {"message_id": 1})
            .sort("timestamp", -1)  # Newest first
            .limit(keep_count)
        )

        keep_message_ids = [doc["message_id"] async for doc in cursor]

        # Build delete query: delete messages NOT in keep list
        delete_query: dict = {
            "chat_id": chat_id,
            "message_id": {"$nin": keep_message_ids},
        }

        # Optionally exclude summary messages from deletion
        if exclude_summaries:
            delete_query["metadata.is_summary"] = {"$ne": True}

        result = await self.collection.delete_many(delete_query)
        deleted_count: int = result.deleted_count

        logger.info(
            "Old messages deleted during compaction",
            chat_id=chat_id,
            deleted_count=deleted_count,
            kept_count=len(keep_message_ids),
        )

        return deleted_count
