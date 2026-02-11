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
from ....database.repositories.message_repository import MessageRepository
from ....services.chat_service import ChatService
from ....services.context_window_manager import ContextWindowManager
from ....services.credit_service import CreditService
from ...dependencies.chat_deps import (
    get_chat_agent,
    get_chat_service,
    get_context_manager,
    get_current_user_id,
    get_deep_agent,
    get_message_repository,
    get_react_agent,
)
from ...dependencies.credit_deps import get_credit_service
from ...schemas.chat_models import ChatRequest
from .deep_agent import stream_with_deep_agent
from .react_agent import stream_with_react_agent
from .simple_agent import stream_with_simple_agent

logger = structlog.get_logger()


async def chat_stream_unified(
    request: ChatRequest,
    user_id: str = Depends(get_current_user_id),
    chat_service: ChatService = Depends(get_chat_service),
    simple_agent: ChatAgent = Depends(get_chat_agent),
    react_agent: FinancialAnalysisReActAgent = Depends(get_react_agent),
    deep_agent: Any = Depends(get_deep_agent),
    credit_service: CreditService = Depends(get_credit_service),
    context_manager: ContextWindowManager = Depends(get_context_manager),
    message_repo: MessageRepository = Depends(get_message_repository),
    x_debug: str | None = Header(None, alias="X-Debug"),
) -> StreamingResponse:
    """
    Unified streaming endpoint with version selection.

    **Authentication**: Requires Bearer token in Authorization header.

    **Agent Versions:**
    - **v2**: Simple ChatAgent - Basic LLM wrapper for general chat
    - **v3** (default): SDK ReAct Agent - Autonomous tool chaining for financial analysis
    - **v4-deep**: Deep hierarchical agent - Sub-agents + skills + adversarial debate

    **Request:**
    ```json
    {
      "message": "Analyze AAPL with Fibonacci",
      "chat_id": "chat_abc123",      // Optional
      "agent_version": "v3",          // Optional: "v2" or "v3" (default: v3)
      "model": "qwen-plus",           // Optional LLM model
      "thinking_enabled": false       // Optional thinking mode
    }
    ```

    **Response:** Server-Sent Events stream

    **Example:**
    ```bash
    # Use v3 (SDK ReAct Agent with tools)
    curl -X POST https://klinematrix.com/api/chat/stream \\
      -H "Authorization: Bearer $TOKEN" \\
      -d '{"message": "Analyze AAPL", "agent_version": "v3"}'

    # Use v2 (simple chat)
    curl -X POST https://klinematrix.com/api/chat/stream \\
      -H "Authorization: Bearer $TOKEN" \\
      -d '{"message": "Hello", "agent_version": "v2"}'
    ```
    """
    logger.info(
        "Unified stream request",
        agent_version=request.agent_version,
        user_id=user_id,
        chat_id=request.chat_id,
    )

    # Route to appropriate agent based on version
    if request.agent_version == "v2":
        # Use simple ChatAgent (basic LLM wrapper)
        return await stream_with_simple_agent(
            request,
            user_id,
            chat_service,
            simple_agent,
            credit_service,
            context_manager,
            message_repo,
        )
    elif request.agent_version == "v3":
        # Use SDK ReAct Agent (tool chaining)
        debug_enabled: bool = bool(x_debug and x_debug.lower() in ("true", "1", "yes"))
        return await stream_with_react_agent(
            request,
            user_id,
            chat_service,
            react_agent,
            credit_service,
            context_manager,
            message_repo,
            debug_enabled,
        )
    elif request.agent_version == "v4-deep":
        # Use Deep hierarchical agent (sub-agents + debate)
        debug_enabled = bool(x_debug and x_debug.lower() in ("true", "1", "yes"))
        return await stream_with_deep_agent(
            request,
            user_id,
            chat_service,
            deep_agent,
            credit_service,
            context_manager,
            message_repo,
            debug_enabled,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agent_version: {request.agent_version}. Must be 'v2', 'v3', or 'v4-deep'",
        )
