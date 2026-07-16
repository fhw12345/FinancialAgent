"""Unified streaming handler with hybrid automatic flow routing."""

from collections.abc import AsyncIterator
from typing import Any

import structlog
from fastapi import Depends, Header
from fastapi.responses import StreamingResponse

from ....agent.chat_agent import ChatAgent
from ....agent.flow_router import AgentFlowRouter, FlowRoutingDecision
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
    get_flow_router,
    get_message_repository,
    get_react_agent,
)
from ...schemas.chat_models import ChatRequest
from .deep_agent import stream_with_deep_agent
from .helpers import format_sse_event
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
    flow_router: AgentFlowRouter = Depends(get_flow_router),
    x_debug: str | None = Header(None, alias="X-Debug"),
) -> StreamingResponse:
    """Select and execute the appropriate chat flow for one request."""
    user_id = LOCAL_USER_ID
    logger.info(
        "Unified stream request",
        agent_version=request.agent_version,
        chat_id=request.chat_id,
    )

    # Button-analysis persistence and non-user messages never invoke an agent,
    # so they must not pay for or emit an automatic routing decision.
    if request.role != "user" or request.source == "tool":
        return await stream_with_simple_agent(
            request,
            user_id,
            chat_service,
            simple_agent,
            context_manager,
            message_repo,
        )

    decision = await flow_router.select(
        message=request.message,
        current_symbol=request.current_symbol,
        requested_version=request.agent_version,
    )
    route_metadata = decision.as_metadata()
    debug_enabled = bool(x_debug and x_debug.lower() in ("true", "1", "yes"))

    logger.info(
        "Chat flow selected",
        flow=decision.flow,
        source=decision.source,
        reason_code=decision.reason_code,
        chat_id=request.chat_id,
    )

    if decision.flow == "v2":
        response = await stream_with_simple_agent(
            request,
            user_id,
            chat_service,
            simple_agent,
            context_manager,
            message_repo,
            route_metadata,
        )
    elif decision.flow == "v3":
        response = await stream_with_react_agent(
            request,
            user_id,
            chat_service,
            react_agent,
            context_manager,
            message_repo,
            debug_enabled,
            route_metadata,
        )
    else:
        response = await stream_with_deep_agent(
            request,
            user_id,
            chat_service,
            deep_agent,
            context_manager,
            message_repo,
            debug_enabled,
            route_metadata,
        )

    return _prepend_route_event(response, decision)


def _prepend_route_event(
    response: StreamingResponse,
    decision: FlowRoutingDecision,
) -> StreamingResponse:
    """Prepend the existing data-only SSE envelope with route metadata."""

    async def routed_stream() -> AsyncIterator[Any]:
        yield format_sse_event(decision.as_event())
        async for chunk in response.body_iterator:
            yield chunk

    return StreamingResponse(routed_stream(), media_type="text/event-stream")
