"""
Chat service for managing conversations with LLM.
Business logic layer coordinating chats, messages, and LLM interactions.
"""

from typing import Any, Literal

import structlog
from pydantic import BaseModel, Field

from ..core.config import Settings
from ..core.exceptions import NotFoundError, ValidationError
from ..database.repositories.chat_repository import ChatRepository
from ..database.repositories.message_repository import MessageRepository
from ..models.chat import Chat, ChatCreate, ChatUpdate, UIState
from ..models.message import Message, MessageCreate, MessageMetadata

logger = structlog.get_logger()


class ChatTitleResponse(BaseModel):
    """Structured LLM response for title generation."""

    title: str = Field(
        ...,
        max_length=50,
        description="Concise chat title (e.g., 'AAPL Fibonacci Analysis')",
    )
    response: str = Field(..., description="Full analysis response")


class ChatService:
    """Service for chat and message management with LLM integration."""

    def __init__(
        self,
        chat_repo: ChatRepository,
        message_repo: MessageRepository,
        settings: Settings,
    ):
        """
        Initialize chat service.

        Args:
            chat_repo: Repository for chat data access
            message_repo: Repository for message data access
            settings: Application settings
        """
        self.chat_repo = chat_repo
        self.message_repo = message_repo
        self.settings = settings

    async def create_chat(
        self, user_id: str | None = None, title: str = "New Chat"
    ) -> Chat:
        """
        Create a new chat. user_id ignored (W5b: schema no longer has user_id).
        """
        chat = await self.chat_repo.create(ChatCreate(title=title))
        logger.info("Chat created", chat_id=chat.chat_id)
        return chat

    async def get_chat(self, chat_id: str, user_id: str | None = None) -> Chat:
        """
        Get chat by id. user_id ignored (W5b: no ownership concept).
        """
        chat = await self.chat_repo.get(chat_id)

        if not chat:
            raise NotFoundError("Chat not found", chat_id=chat_id)

        return chat

    async def list_user_chats(
        self,
        user_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
        include_archived: bool = False,
    ) -> tuple[list[Chat], int]:
        """List chats with pagination. user_id ignored (W5b)."""
        if page < 1:
            raise ValidationError("Page must be >= 1", page=page)

        if page_size < 1 or page_size > 100:
            raise ValidationError("Page size must be 1-100", page_size=page_size)

        chats = await self.chat_repo.list_by_user(
            limit=page_size,
            skip=(page - 1) * page_size,
            include_archived=include_archived,
        )

        total = len(chats)
        return chats, total

    async def add_message(
        self,
        chat_id: str,
        user_id: str | None = None,
        role: Literal["user", "assistant", "system"] = "user",
        content: str = "",
        source: Literal["user", "llm", "tool"] = "user",
        metadata: MessageMetadata | dict[str, Any] | None = None,
        tool_call: Any | None = None,
    ) -> Message:
        """Add message to chat. user_id ignored (W5b)."""
        # Verify chat exists
        await self.get_chat(chat_id)

        # Convert dict metadata to MessageMetadata if needed
        if isinstance(metadata, dict):
            # For dict, wrap it in raw_data if it's analysis data
            if any(
                key in metadata
                for key in ["symbol", "timeframe", "fibonacci_levels", "stochastic_k"]
            ):
                metadata_obj = MessageMetadata(raw_data=metadata)
            else:
                # Try to construct MessageMetadata from dict fields
                metadata_obj = MessageMetadata(**metadata)
        elif metadata is None:
            metadata_obj = MessageMetadata()
        else:
            metadata_obj = metadata

        # Create message
        message = await self.message_repo.create(
            MessageCreate(
                chat_id=chat_id,
                role=role,
                content=content,
                source=source,
                metadata=metadata_obj,
                tool_call=tool_call,
            )
        )

        # Update chat with last message info
        await self.chat_repo.update(
            chat_id,
            ChatUpdate(last_message_preview=content[:200]),
        )
        await self.chat_repo.update_last_message_at(chat_id)

        logger.info(
            "Message added",
            chat_id=chat_id,
            message_id=message.message_id,
            role=role,
            source=source,
        )

        return message

    async def get_chat_messages(
        self,
        chat_id: str,
        user_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Message]:
        """Get messages for chat. user_id ignored (W5b)."""
        await self.get_chat(chat_id)

        messages = await self.message_repo.get_by_chat(
            chat_id, limit=limit or 100, offset=offset
        )

        return messages

    async def update_ui_state(
        self, chat_id: str, user_id: str | None = None, ui_state: UIState | None = None
    ) -> Chat:
        """Update chat UI state. user_id ignored (W5b)."""
        await self.get_chat(chat_id)

        # Update UI state
        updated_chat = await self.chat_repo.update_ui_state(chat_id, ui_state)

        if not updated_chat:
            raise NotFoundError("Chat not found", chat_id=chat_id)

        logger.info(
            "UI state updated",
            chat_id=chat_id,
            symbol=ui_state.current_symbol,
            interval=ui_state.current_interval,
        )

        return updated_chat

    def _generate_title_heuristic(self, user_message: str) -> str:
        """
        Generate chat title using heuristic (fallback when LLM doesn't provide title).

        Uses regex symbol extraction + keyword matching.

        Args:
            user_message: User's first message

        Returns:
            Generated title (max 50 chars)
        """
        from ..core.utils.title_utils import generate_chat_title

        return generate_chat_title(user_message)

    async def update_chat_title(self, chat_id: str, title: str) -> Chat | None:
        """
        Update a chat's title.

        Args:
            chat_id: Chat identifier
            title: New title

        Returns:
            Updated chat or None if not found
        """
        updated_chat = await self.chat_repo.update(chat_id, ChatUpdate(title=title))
        if updated_chat:
            logger.info("Chat title updated", chat_id=chat_id, title=title)
        return updated_chat

    async def update_title_if_new(
        self, chat_id: str, llm_title: str | None, user_message: str
    ) -> str | None:
        """
        Update chat title if it's still "New Chat".

        Priority: LLM-generated title > Heuristic fallback

        The LLM generates a title at the end of each response in format:
        [chat_title: Your Title Here]

        If LLM title is not available, falls back to heuristic extraction
        using symbol detection and action keywords.

        Args:
            chat_id: Chat identifier
            llm_title: Title extracted from LLM response (may be None)
            user_message: User's first message (for heuristic fallback)

        Returns:
            Title that was set, or None if skipped
        """
        # Check if we should update the title
        chat = await self.chat_repo.get(chat_id)
        if not chat or chat.title != "New Chat":
            return None

        # Use LLM title if available, otherwise fall back to heuristic
        if llm_title:
            title = llm_title
            source = "llm"
        else:
            title = self._generate_title_heuristic(user_message)
            source = "heuristic"

        # Update chat title
        await self.update_chat_title(chat_id, title)

        logger.info(
            "Auto-generated chat title",
            chat_id=chat_id,
            title=title,
            source=source,
            user_message_preview=user_message[:50] if user_message else "",
        )

        return title

    async def find_chat_by_symbol(
        self, user_id: str | None = None, symbol: str = ""
    ) -> Chat | None:
        """Find active chat for symbol. user_id ignored (W5b)."""
        return await self.chat_repo.find_by_symbol(symbol=symbol)

    async def get_or_create_symbol_chat(
        self, user_id: str | None = None, symbol: str = ""
    ) -> Chat:
        """Get existing chat for symbol or create new one. user_id ignored (W5b)."""
        existing_chat = await self.find_chat_by_symbol(symbol=symbol)

        if existing_chat:
            logger.info(
                "Reusing existing chat for symbol",
                symbol=symbol,
                chat_id=existing_chat.chat_id,
            )
            return existing_chat

        new_chat = await self.create_chat(title=f"{symbol} Analysis")

        ui_state = UIState(current_symbol=symbol)
        updated_chat = await self.update_ui_state(new_chat.chat_id, ui_state=ui_state)

        if not updated_chat:
            logger.warning(
                "Failed to update UI state after chat creation",
                chat_id=new_chat.chat_id,
            )
            return new_chat

        logger.info(
            "Created new chat for symbol",
            symbol=symbol,
            chat_id=updated_chat.chat_id,
        )

        return updated_chat

    async def delete_chat(self, chat_id: str, user_id: str | None = None) -> bool:
        """Delete chat and all associated messages. user_id ignored (W5b)."""
        await self.get_chat(chat_id)

        deleted_messages = await self.message_repo.delete_by_chat(chat_id)

        deleted = await self.chat_repo.delete(chat_id)

        if deleted:
            logger.info(
                "Chat deleted",
                chat_id=chat_id,
                messages_deleted=deleted_messages,
            )

        return deleted
