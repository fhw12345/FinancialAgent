"""
Unified streaming handler with version routing.

This module contains the main chat_stream_unified endpoint that routes
requests to either the Simple Agent (v2) or ReAct Agent (v3) based on
the requested agent version.
"""

from typing import Any

import structlog
from fastapi import Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from ....agent.chat_agent import ChatAgent
from ....agent.langgraph_react_agent import FinancialAnalysisReActAgent
from ....core.local_user import LOCAL_USER_ID
from ....database.repositories.message_repository import MessageRepository
from ....services.chat_service import ChatService
from ....services.context_window_manager import ContextWindowManager
from ...dependencies.chat_deps import (
    get_chat_agent,
    get_chat_service,
    get_context_manager,
    get_deep_agent,
    get_message_repository,
    get_react_agent,
)
from ...schemas.chat_models import ChatRequest
from .deep_agent import stream_with_deep_agent
from .react_agent import stream_with_react_agent
from .simple_agent import stream_with_simple_agent

logger = structlog.get_logger()


async def chat_stream_unified(
    request: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
    simple_agent: ChatAgent = Depends(get_chat_agent),
    react_agent: FinancialAnalysisReActAgent = Depends(get_react_agent),
    deep_agent: Any = Depends(get_deep_agent),
    context_manager: ContextWindowManager = Depends(get_context_manager),
    message_repo: MessageRepository = Depends(get_message_repository),
    x_debug: str | None = Header(None, alias="X-Debug"),
) -> StreamingResponse:
    """Unified streaming endpoint with version selection (v2/v3/v4-deep)."""
    user_id = LOCAL_USER_ID
    logger.info(
        "Unified stream request",
        agent_version=request.agent_version,
        chat_id=request.chat_id,
    )

    if request.agent_version == "v2":
        return await stream_with_simple_agent(
            request,
            user_id,
            chat_service,
            simple_agent,
            context_manager,
            message_repo,
        )
    elif request.agent_version == "v3":
        debug_enabled: bool = bool(x_debug and x_debug.lower() in ("true", "1", "yes"))
        return await stream_with_react_agent(
            request,
            user_id,
            chat_service,
            react_agent,
            context_manager,
            message_repo,
            debug_enabled,
        )
    elif request.agent_version == "v4-deep":
        debug_enabled = bool(x_debug and x_debug.lower() in ("true", "1", "yes"))
        return await stream_with_deep_agent(
            request,
            user_id,
            chat_service,
            deep_agent,
            context_manager,
            message_repo,
            debug_enabled,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agent_version: {request.agent_version}. Must be 'v2', 'v3', or 'v4-deep'",
        )
