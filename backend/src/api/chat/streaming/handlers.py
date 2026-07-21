"""Unified streaming handler with hybrid automatic flow routing."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import structlog
from fastapi import Depends, Header, Request
from fastapi.responses import StreamingResponse

from ....agent.chat_agent import ChatAgent
from ....agent.flow_router import AgentFlowRouter, FlowRoutingDecision
from ....agent.langgraph_react_agent import FinancialAnalysisReActAgent
from ....core.local_user import LOCAL_USER_ID
from ....database.repositories.message_repository import MessageRepository
from ....services.agent_run_service import AgentRunService
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
from ...dependencies.run_deps import get_agent_run_service
from ...schemas.agent_events import AgentEventSequencer, parse_sse_data
from ...schemas.chat_models import ChatRequest
from .cancellation import (
    ClientDisconnected,
    await_task_completion,
    await_task_or_disconnect,
    cancel_and_await,
)
from .deep_agent import stream_with_deep_agent
from .helpers import create_run_state_event, format_sse_event
from .lifecycle import ChatStreamLifecycle
from .react_agent import stream_with_react_agent
from .simple_agent import stream_with_simple_agent

logger = structlog.get_logger()


async def chat_stream_unified(
    request: ChatRequest,
    http_request: Request,
    chat_service: ChatService = Depends(get_chat_service),
    simple_agent: ChatAgent = Depends(get_chat_agent),
    react_agent: FinancialAnalysisReActAgent = Depends(get_react_agent),
    deep_agent: Any = Depends(get_deep_agent),
    context_manager: ContextWindowManager = Depends(get_context_manager),
    message_repo: MessageRepository = Depends(get_message_repository),
    flow_router: AgentFlowRouter = Depends(get_flow_router),
    run_service: AgentRunService = Depends(get_agent_run_service),
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
        response = await stream_with_simple_agent(
            request,
            user_id,
            chat_service,
            simple_agent,
            context_manager,
            message_repo,
            client_request=http_request,
        )
        return _wrap_persistence_event_stream(
            response,
            run_id=f"event_{uuid.uuid4().hex}",
        )

    run = await run_service.create_chat_run(
        requested_policy=request.agent_version,
    )
    routing_task = asyncio.create_task(
        flow_router.select(
            message=request.message,
            current_symbol=request.current_symbol,
            requested_version=request.agent_version,
        )
    )

    async def persist_unstarted_cancellation(
        *,
        agent_type: str,
        cancel_reason: str,
    ) -> None:
        lifecycle = ChatStreamLifecycle(
            request=request,
            user_id=user_id,
            chat_service=chat_service,
            context_manager=context_manager,
            message_repo=message_repo,
            run_id=run.run_id,
            run_service=run_service,
        )
        await lifecycle.start()
        await lifecycle.persist_request()
        await lifecycle.cancel(
            active_task=None,
            agent_type=agent_type,
            cancel_reason=cancel_reason,
        )

    try:
        decision = await await_task_or_disconnect(routing_task, http_request)
    except ClientDisconnected:
        await cancel_and_await(routing_task)
        await persist_unstarted_cancellation(
            agent_type="flow_router",
            cancel_reason="client_disconnected_during_routing",
        )
        logger.info("Client disconnected during flow routing")
        return StreamingResponse(iter(()), media_type="text/event-stream")
    except asyncio.CancelledError:
        await cancel_and_await(routing_task)
        await persist_unstarted_cancellation(
            agent_type="flow_router",
            cancel_reason="client_disconnected_during_routing",
        )
        raise
    except Exception as exc:
        await run_service.fail(
            run.run_id,
            error_code="ROUTING_ERROR",
            error_message=str(exc),
        )
        raise

    running_run = await run_service.mark_running(
        run.run_id,
        selected_policy=decision.flow,
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
            client_request=http_request,
            run_id=run.run_id,
            run_service=run_service,
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
            client_request=http_request,
            run_id=run.run_id,
            run_service=run_service,
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
            client_request=http_request,
            run_id=run.run_id,
            run_service=run_service,
        )

    async def persist_prelude_cancellation() -> None:
        await persist_unstarted_cancellation(
            agent_type=decision.flow,
            cancel_reason="client_disconnected_before_agent_stream",
        )

    async def persist_stream_failure(exc: Exception) -> None:
        await run_service.fail(
            run.run_id,
            error_code="EVENT_ENVELOPE_ERROR",
            error_message=str(exc),
        )

    return _prepend_route_event(
        response,
        decision,
        running_run or run,
        on_prelude_cancel=persist_prelude_cancellation,
        on_stream_failure=persist_stream_failure,
    )


def _prepend_route_event(
    response: StreamingResponse,
    decision: FlowRoutingDecision,
    run: Any,
    *,
    on_prelude_cancel: Callable[[], Awaitable[None]] | None = None,
    on_stream_failure: Callable[[Exception], Awaitable[None]] | None = None,
) -> StreamingResponse:
    """Wrap the complete agent stream in sequenced event envelopes."""

    async def routed_stream() -> AsyncIterator[Any]:
        inner_started = False
        stream_finished = False
        sequencer = AgentEventSequencer(run.run_id)
        try:
            prelude = [
                create_run_state_event(
                    run.run_id,
                    run.status,
                    run.execution_mode,
                ),
                format_sse_event(decision.as_event()),
            ]
            for chunk in prelude:
                for event in parse_sse_data(chunk):
                    yield sequencer.format_sse(event)
            inner_started = True
            async for chunk in response.body_iterator:
                for event in parse_sse_data(chunk):
                    yield sequencer.format_sse(event)
            stream_finished = True
        except Exception as exc:
            if on_stream_failure is not None:
                failure_task = asyncio.create_task(on_stream_failure(exc))
                try:
                    await asyncio.shield(failure_task)
                except asyncio.CancelledError:
                    await await_task_completion(failure_task)
                    raise
            raise
        finally:
            if not stream_finished:
                close = getattr(response.body_iterator, "aclose", None)
                if inner_started and close is not None:
                    await close()
                elif on_prelude_cancel is not None:
                    await on_prelude_cancel()

    return StreamingResponse(routed_stream(), media_type="text/event-stream")


def _wrap_persistence_event_stream(
    response: StreamingResponse,
    *,
    run_id: str,
) -> StreamingResponse:
    """Envelope persistence-only endpoint events without creating an agent run."""

    async def event_stream() -> AsyncIterator[Any]:
        sequencer = AgentEventSequencer(run_id)
        stream_finished = False
        try:
            async for chunk in response.body_iterator:
                for event in parse_sse_data(chunk):
                    yield sequencer.format_sse(event)
            stream_finished = True
        finally:
            if not stream_finished:
                close = getattr(response.body_iterator, "aclose", None)
                if close is not None:
                    await close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
