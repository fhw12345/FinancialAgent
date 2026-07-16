"""
Helper functions for chat operations.

This module contains utility functions for chat context management,
symbol instruction building, and other shared logic used by both
CRUD endpoints and streaming handlers.
"""

from typing import Any

import structlog

from ...services.chat_service import ChatService
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
