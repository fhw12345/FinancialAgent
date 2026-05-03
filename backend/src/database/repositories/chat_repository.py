"""
Chat repository for conversation management.
Handles CRUD operations for chat collection with UI state management.

W5b: user_id removed from schema. Method signatures keep `user_id` as an
ignored parameter so existing call sites stay valid; queries no longer
filter by user_id.
"""

from typing import Any

import structlog
from motor.motor_asyncio import AsyncIOMotorCollection

from src.core.utils.date_utils import utcnow

from ...models.chat import Chat, ChatCreate, ChatUpdate, UIState

logger = structlog.get_logger()


class ChatRepository:
    """Repository for chat data access operations."""

    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def ensure_indexes(self) -> None:
        """Create indexes for optimal query performance."""
        await self.collection.create_index(
            [("is_archived", 1), ("updated_at", -1)],
            name="idx_chats_updated",
        )
        await self.collection.create_index(
            [("ui_state.current_symbol", 1), ("is_archived", 1)],
            name="idx_symbol_lookup",
        )
        logger.info("Chat indexes ensured")

    async def create(self, chat_create: ChatCreate) -> Chat:
        import uuid

        chat_id = f"chat_{uuid.uuid4().hex[:12]}"

        chat = Chat(
            chat_id=chat_id,
            title=chat_create.title,
            is_archived=False,
            ui_state=UIState(),
            last_message_preview=None,
            created_at=utcnow(),
            updated_at=utcnow(),
            last_message_at=None,
        )

        await self.collection.insert_one(chat.model_dump())
        logger.info("Chat created", chat_id=chat_id)
        return chat

    async def get(self, chat_id: str) -> Chat | None:
        chat_dict = await self.collection.find_one({"chat_id": chat_id})
        if not chat_dict:
            return None
        chat_dict.pop("_id", None)
        return Chat(**chat_dict)

    async def list_by_user(
        self,
        user_id: str | None = None,
        limit: int = 50,
        skip: int = 0,
        include_archived: bool = False,
    ) -> list[Chat]:
        """List all chats. user_id parameter is ignored (kept for API compat)."""
        query: dict[str, Any] = {}
        if not include_archived:
            query["is_archived"] = False

        cursor = (
            self.collection.find(query).sort("updated_at", -1).skip(skip).limit(limit)
        )

        chats = []
        async for chat_dict in cursor:
            chat_dict.pop("_id", None)
            chats.append(Chat(**chat_dict))
        return chats

    async def update(self, chat_id: str, chat_update: ChatUpdate) -> Chat | None:
        update_dict: dict[str, Any] = {"updated_at": utcnow()}

        if chat_update.title is not None:
            update_dict["title"] = chat_update.title
        if chat_update.is_archived is not None:
            update_dict["is_archived"] = chat_update.is_archived
        if chat_update.ui_state is not None:
            update_dict["ui_state"] = chat_update.ui_state.model_dump()
        if chat_update.last_message_preview is not None:
            update_dict["last_message_preview"] = chat_update.last_message_preview

        result = await self.collection.find_one_and_update(
            {"chat_id": chat_id},
            {"$set": update_dict},
            return_document=True,
        )

        if not result:
            return None
        result.pop("_id", None)
        logger.info("Chat updated", chat_id=chat_id, fields=list(update_dict.keys()))
        return Chat(**result)

    async def update_ui_state(self, chat_id: str, ui_state: UIState) -> Chat | None:
        result = await self.collection.find_one_and_update(
            {"chat_id": chat_id},
            {"$set": {"ui_state": ui_state.model_dump(), "updated_at": utcnow()}},
            return_document=True,
        )
        if not result:
            return None
        result.pop("_id", None)
        return Chat(**result)

    async def update_last_message_at(self, chat_id: str) -> Chat | None:
        result = await self.collection.find_one_and_update(
            {"chat_id": chat_id},
            {"$set": {"last_message_at": utcnow(), "updated_at": utcnow()}},
            return_document=True,
        )
        if not result:
            return None
        result.pop("_id", None)
        return Chat(**result)

    async def find_by_symbol(
        self, user_id: str | None = None, symbol: str = ""
    ) -> Chat | None:
        """Find active chat with specific symbol. user_id ignored."""
        chat_dict = await self.collection.find_one(
            {"ui_state.current_symbol": symbol, "is_archived": False}
        )
        if not chat_dict:
            return None
        chat_dict.pop("_id", None)
        return Chat(**chat_dict)

    async def delete(self, chat_id: str) -> bool:
        result = await self.collection.delete_one({"chat_id": chat_id})
        if result.deleted_count > 0:
            logger.info("Chat deleted", chat_id=chat_id)
            return True
        return False
