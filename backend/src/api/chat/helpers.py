"""
Helper functions for chat operations.

This module contains utility functions for chat context management,
symbol instruction building, and other shared logic used by both
CRUD endpoints and streaming handlers.
"""

from typing import Any

import structlog

from ...database.repositories.message_repository import MessageRepository
from ...models.chat import UIState
from ...models.message import Message, MessageMetadata
from ...services.chat_service import ChatService
from ...services.context_window_manager import ContextWindowManager
from ..schemas.chat_models import ChatRequest

logger = structlog.get_logger()


# ===== Helper Functions =====


async def get_or_create_chat(
    request: ChatRequest,
    user_id: str,
    chat_service: ChatService,
) -> tuple[str, dict[str, Any] | None]:
    """
    Get existing chat or create new one for streaming endpoints.

    Args:
        request: Chat request with optional chat_id
        user_id: Current user ID
        chat_service: Chat service instance

    Returns:
        Tuple of (chat_id, chat_created_event_dict)
        chat_created_event_dict is None if using existing chat,
        or a dict with chat_id and type='chat_created' if new chat was created
    """
    if request.chat_id:
        chat = await chat_service.get_chat(request.chat_id, user_id)
        return chat.chat_id, None
    else:
        chat_title = request.title if request.title else "New Chat"
        chat = await chat_service.create_chat(user_id, title=chat_title)
        return chat.chat_id, {"chat_id": chat.chat_id, "type": "chat_created"}


def build_symbol_context_instruction(current_symbol: str | None) -> str:
    """
    Build symbol context instruction to append to user message.

    Instead of injecting as a system message (which conflicts with agent's
    system prompt), append this as context to the user message itself.
    This follows the same pattern as language instructions.

    Args:
        current_symbol: Active symbol from chat ui_state (e.g., "AAPL", "GOOG")

    Returns:
        Instruction string to append, or empty string if no symbol

    Example:
        >>> build_symbol_context_instruction("AAPL")
        "[Context: User has selected symbol 'AAPL' in the UI. Use this symbol if..."
    """
    if not current_symbol:
        return ""

    return (
        f"\n\n[Context: User has selected symbol '{current_symbol}' in the UI. "
        f"Use this symbol if their question doesn't explicitly mention a different symbol. "
        f"If they mention a different symbol, prioritize their explicit choice.]"
    )


async def get_active_symbol_instruction(
    chat_id: str,
    user_id: str,
    chat_service: ChatService,
    request_symbol: str | None = None,
) -> str:
    """
    Get active symbol and build instruction string.

    Priority order:
    1. request_symbol (from chat request body) - eliminates race condition
    2. chat.ui_state.current_symbol (from DB) - fallback for restoration

    This is a shared helper used by both v2 (Simple Agent) and v3 (ReAct Agent).
    Returns an instruction string to append to the user message (not a system message).

    Args:
        chat_id: Chat identifier
        user_id: User identifier
        chat_service: Service to fetch chat data
        request_symbol: Symbol passed directly in request (takes priority)

    Returns:
        Symbol context instruction string (empty if no symbol)
    """
    # Priority 1: Use request symbol (avoids race condition with UI state sync)
    if request_symbol:
        logger.info(
            "Using symbol from request (priority)",
            chat_id=chat_id,
            symbol=request_symbol,
        )
        # Also update DB ui_state for future restoration
        await chat_service.update_ui_state(
            chat_id, user_id, UIState(current_symbol=request_symbol)
        )
        return build_symbol_context_instruction(request_symbol)

    # Priority 2: Fallback to DB ui_state
    chat = await chat_service.get_chat(chat_id, user_id)
    current_symbol = None
    if chat and chat.ui_state:
        current_symbol = chat.ui_state.current_symbol

    if current_symbol:
        logger.info(
            "Using symbol from DB ui_state (fallback)",
            chat_id=chat_id,
            symbol=current_symbol,
        )
        return build_symbol_context_instruction(current_symbol)

    return ""


async def compact_context_if_needed(
    messages: list[Message],
    chat_id: str,
    context_manager: ContextWindowManager,
    message_repo: MessageRepository,
) -> list[dict[str, str]]:
    """
    Check if context compaction is needed and perform it if so.

    This implements sliding window + summarization for long conversation histories.
    When token count exceeds 75% of model limit, old messages are summarized and
    deleted to prevent hitting context limits.

    Args:
        messages: List of Message objects from DB
        chat_id: Chat identifier for persisting summary
        context_manager: ContextWindowManager instance
        message_repo: MessageRepository for persisting summary and deleting old messages
    Returns:
        List of messages in conversation_history format (role/content dicts)
    """
    if not messages:
        return []

    # Calculate total tokens using tiktoken
    total_tokens = context_manager.calculate_context_tokens(messages)

    # Check if compaction is needed (> 75% of context limit)
    should_compact = context_manager.should_compact(total_tokens)

    if not should_compact:
        # No compaction needed - return messages as conversation_history format
        logger.debug(
            "Context within limits, no compaction needed",
            chat_id=chat_id,
            total_tokens=total_tokens,
            message_count=len(messages),
        )
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    # Context compaction needed
    logger.info(
        "Context compaction triggered",
        chat_id=chat_id,
        total_tokens=total_tokens,
        message_count=len(messages),
    )

    # Extract HEAD, BODY, TAIL structure
    head, body, tail = context_manager.extract_context_structure(messages)

    if not body:
        # Nothing to summarize in body - return as-is
        logger.info(
            "No body messages to summarize",
            chat_id=chat_id,
            head_count=len(head),
            tail_count=len(tail),
        )
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    # Generate summary using LLM
    summary_text = await context_manager.summarize_history(
        body_messages=body,
        symbol=None,  # General chat, no specific symbol
        llm_service=True,  # Use LLM for summarization
    )

    if summary_text:
        # Persist summary message to database
        summary_metadata = MessageMetadata(
            is_summary=True,
            summarized_message_count=len(body),
        )
        summary_message_create = {
            "chat_id": chat_id,
            "role": "assistant",
            "content": f"## 📋 Previous Conversation Summary\n\n{summary_text}",
            "source": "llm",
            "metadata": summary_metadata,
        }
        await message_repo.create(summary_message_create)

        # Delete old messages (body), keeping head and tail
        keep_count = context_manager.tail_keep
        deleted_count = await message_repo.delete_old_messages_keep_recent(
            chat_id=chat_id,
            keep_count=keep_count,
            exclude_summaries=True,
        )

        logger.info(
            "Context compacted and persisted",
            chat_id=chat_id,
            summarized_count=len(body),
            deleted_count=deleted_count,
            kept_count=keep_count,
            original_tokens=total_tokens,
            summary_tokens=context_manager.estimate_tokens(summary_text),
        )

    # Reconstruct compacted context
    compacted_messages = context_manager.reconstruct_context(
        head=head, summary_text=summary_text, tail=tail
    )

    # Convert to conversation_history format
    return [{"role": msg.role, "content": msg.content} for msg in compacted_messages]
