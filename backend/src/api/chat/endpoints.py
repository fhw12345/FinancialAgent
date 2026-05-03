"""
Chat CRUD endpoints for persistent chat management.
"""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException

from ...core.exceptions import NotFoundError
from ...services.chat_service import ChatService
from ..dependencies.chat_deps import get_chat_service
from ..schemas.chat_models import (
    ChatDetailResponse,
    ChatListResponse,
    UpdateUIStateRequest,
)

logger = structlog.get_logger()

router = APIRouter()


@router.post("/chats")
async def create_empty_chat(
    chat_service: ChatService = Depends(get_chat_service),
) -> dict[str, str]:
    """Create an empty chat (triggered by symbol selection)."""
    try:
        logger.info("Creating empty chat")
        chat = await chat_service.create_chat(title="New Chat")
        logger.info("Empty chat created", chat_id=chat.chat_id)
        return {"chat_id": chat.chat_id}
    except Exception as e:
        logger.error("Failed to create empty chat", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to create chat: {str(e)}"
        ) from e


@router.get("/chats", response_model=ChatListResponse)
async def list_user_chats(
    page: int = 1,
    page_size: int = 20,
    include_archived: bool = False,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatListResponse:
    """List all chats."""
    try:
        chats, total = await chat_service.list_user_chats(
            page=page,
            page_size=page_size,
            include_archived=include_archived,
        )

        logger.info("Chats listed", count=len(chats), page=page)

        return ChatListResponse(
            chats=chats,
            total=total,
            page=page,
            page_size=page_size,
        )

    except ValueError as e:
        logger.error("Validation error listing chats", error=str(e))
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Failed to list chats", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to list chats",
        ) from e


@router.get("/chats/{chat_id}", response_model=ChatDetailResponse)
async def get_chat_detail(
    chat_id: str,
    limit: int | None = None,
    offset: int = 0,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatDetailResponse:
    """Get chat with messages for state restoration."""
    try:
        chat = await chat_service.get_chat(chat_id)

        messages = await chat_service.get_chat_messages(
            chat_id, limit=limit, offset=offset
        )

        logger.info(
            "Chat detail retrieved",
            chat_id=chat_id,
            message_count=len(messages),
        )

        return ChatDetailResponse(
            chat=chat,
            messages=messages,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get chat detail", chat_id=chat_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve chat",
        ) from e


@router.delete("/chats/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: str,
    chat_service: ChatService = Depends(get_chat_service),
) -> None:
    """Delete a chat and all its messages."""
    try:
        deleted = await chat_service.delete_chat(chat_id)

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="Chat not found",
            )

        logger.info("Chat deleted via API", chat_id=chat_id)

        return None

    except NotFoundError as e:
        logger.error("Chat not found for deletion", chat_id=chat_id, error=str(e))
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error("Failed to delete chat", chat_id=chat_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to delete chat") from e


@router.patch("/chats/{chat_id}/ui-state")
async def update_chat_ui_state(
    chat_id: str,
    request: UpdateUIStateRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> Any:
    """Update chat UI state (debounced from frontend)."""
    try:
        updated_chat = await chat_service.update_ui_state(
            chat_id, ui_state=request.ui_state
        )

        logger.info(
            "UI state updated",
            chat_id=chat_id,
            symbol=request.ui_state.current_symbol,
        )

        return updated_chat

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update UI state", chat_id=chat_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to update UI state",
        ) from e
