"""
ReAct agent streaming handler (v3).

Streaming response logic for the ReAct Agent (v3): SSE streaming, tool
execution callbacks, latency metrics, and context management.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from fastapi import Request
from fastapi.responses import StreamingResponse

from ....agent.callbacks.tool_execution_callback import ToolExecutionCallback
from ....agent.langgraph_react_agent import FinancialAnalysisReActAgent
from ....core.utils import extract_token_usage_from_agent_result
from ....core.utils.date_utils import utcnow
from ....core.utils.title_utils import extract_title_from_response
from ....database.repositories.message_repository import MessageRepository
from ....models.message import MessageMetadata
from ....services.chat_service import ChatService
from ....services.context_window_manager import ContextWindowManager
from ....services.conversation_context_service import ConversationContextService
from ...schemas.chat_models import ChatRequest
from ..helpers import get_active_symbol_instruction, get_or_create_chat
from .cancellation import (
    ClientDisconnected,
    await_disconnect_grace,
    await_task_completion,
    cancel_and_await,
    persist_cancelled_run,
    raise_if_disconnected,
)
from .helpers import (
    create_chunk_event,
    create_done_event,
    create_error_event,
    create_latency_event,
    create_stream_mode_event,
    create_thinking_event,
    format_sse_event,
)

logger = structlog.get_logger()


async def stream_with_react_agent(
    request: ChatRequest,
    user_id: str,
    chat_service: ChatService,
    agent: FinancialAnalysisReActAgent,
    context_manager: ContextWindowManager,
    message_repo: MessageRepository,
    debug: bool = False,
    route_metadata: dict[str, str] | None = None,
    client_request: Request | None = None,
) -> StreamingResponse:
    """Stream using SDK ReAct Agent (v3) with real-time tool execution visibility."""

    async def generate_stream() -> AsyncGenerator[str, None]:
        chat_id = None
        tool_event_queue: asyncio.Queue[dict[str, Any]] | None = None
        agent_task: asyncio.Task[dict[str, Any]] | None = None
        terminal_task: asyncio.Task[Any] | None = None
        stream_active = False
        run_id = f"run_{uuid.uuid4().hex}"

        request_start = utcnow()
        first_response_chunk_recorded = False
        first_tool_recorded = False

        def get_elapsed_ms() -> int:
            return int((utcnow() - request_start).total_seconds() * 1000)

        try:
            chat_id, chat_created_event = await get_or_create_chat(
                request, user_id, chat_service
            )
            if chat_created_event:
                yield format_sse_event(chat_created_event)

            yield create_thinking_event("initializing", chat_id)

            logger.debug(
                "Saving message with tool_call",
                has_tool_call=request.tool_call is not None,
            )
            current_message = await chat_service.add_message(
                chat_id=chat_id,
                user_id=user_id,
                role=request.role,
                content=request.message,
                source=request.source,
                metadata=request.metadata,
                tool_call=request.tool_call,
            )

            if request.role != "user" or request.source == "tool":
                yield create_done_event(chat_id)
                logger.info(
                    "Skipping agent invocation (v3)",
                    role=request.role,
                    source=request.source,
                    reason="non-user role or tool source",
                )
                return

            await chat_service.update_title_if_new(
                chat_id=chat_id,
                llm_title=None,
                user_message=request.message,
                current_symbol=request.current_symbol,
            )

            messages = await chat_service.get_chat_messages(chat_id, user_id)

            symbol_instruction = await get_active_symbol_instruction(
                chat_id=chat_id,
                user_id=user_id,
                chat_service=chat_service,
                request_symbol=request.current_symbol,
            )

            context_service = ConversationContextService(
                context_manager=context_manager,
                message_repo=message_repo,
            )
            prepared_context = await context_service.prepare(
                chat_id=chat_id,
                messages=messages,
                current_message=current_message,
                symbol_instruction=symbol_instruction,
                symbol_source=(
                    "request"
                    if request.current_symbol
                    else "chat_ui_state" if symbol_instruction else None
                ),
            )

            logger.info(
                "Conversation history prepared for agent",
                chat_id=chat_id,
                total_messages=len(messages),
                conversation_history_count=prepared_context.history_message_count,
                elapsed_ms=get_elapsed_ms(),
            )

            yield create_latency_event("context_prepared", get_elapsed_ms())
            yield create_thinking_event("reasoning", chat_id)
            yield create_stream_mode_event("buffered")

            tool_event_queue = asyncio.Queue()
            tool_callback = ToolExecutionCallback(tool_event_queue, request.language)
            stream_active = True

            async def stream_tool_events_background() -> AsyncGenerator[str, None]:
                nonlocal stream_active, agent_task
                MAX_QUEUE_SIZE = 100
                while stream_active:
                    try:
                        await raise_if_disconnected(client_request)
                        queue_size = tool_event_queue.qsize()
                        if queue_size > MAX_QUEUE_SIZE:
                            logger.error(
                                "Event queue overflow - circuit breaker triggered",
                                queue_size=queue_size,
                                max_size=MAX_QUEUE_SIZE,
                            )
                            while not tool_event_queue.empty():
                                try:
                                    tool_event_queue.get_nowait()
                                except asyncio.QueueEmpty:
                                    break
                            stream_active = False
                            break

                        event = await asyncio.wait_for(
                            tool_event_queue.get(), timeout=0.1
                        )
                        yield format_sse_event(event)
                    except TimeoutError:
                        if agent_task and agent_task.done():
                            stream_active = False
                            break
                        continue
                    except (asyncio.CancelledError, ClientDisconnected):
                        raise
                    except Exception as e:
                        logger.error(
                            "Error streaming tool event", error=str(e), exc_info=True
                        )
                        break

                while not tool_event_queue.empty():
                    try:
                        event = tool_event_queue.get_nowait()
                        yield format_sse_event(event)
                    except asyncio.QueueEmpty:
                        break

            try:
                yield create_latency_event("agent_started", get_elapsed_ms())

                agent_task = asyncio.create_task(
                    asyncio.wait_for(
                        agent.ainvoke(
                            user_message=prepared_context.current_message,
                            conversation_history=prepared_context.history,
                            debug=debug,
                            additional_callbacks=[tool_callback],
                            language=request.language,
                            chat_id=chat_id,
                        ),
                        timeout=120.0,
                    )
                )

                async for tool_event in stream_tool_events_background():
                    if not first_tool_recorded:
                        first_tool_recorded = True
                        tool_name = None
                        if isinstance(tool_event, str) and tool_event.startswith(
                            "data: "
                        ):
                            try:
                                event_data = json.loads(tool_event[6:].strip())
                                tool_name = event_data.get("tool_name")
                            except (json.JSONDecodeError, AttributeError):
                                pass
                        elif isinstance(tool_event, dict):
                            tool_name = tool_event.get("tool_name")
                        yield create_latency_event(
                            "first_tool",
                            get_elapsed_ms(),
                            tool_name=tool_name,
                        )
                    yield tool_event

                result = await agent_task

            except TimeoutError:
                logger.error(
                    "Agent execution timeout",
                    chat_id=chat_id,
                    user_id=user_id,
                    timeout_seconds=120,
                )
                if tool_event_queue:
                    async for tool_event in stream_tool_events_background():
                        yield tool_event
                yield create_error_event(
                    "Request timeout. The analysis is taking too long. Please try again with a simpler question.",
                    "AGENT_TIMEOUT",
                )
                return
            except (asyncio.CancelledError, ClientDisconnected):
                raise
            except Exception as e:
                logger.error(
                    "Agent execution error",
                    chat_id=chat_id,
                    user_id=user_id,
                    error=str(e),
                    exc_info=True,
                )
                if tool_event_queue:
                    async for tool_event in stream_tool_events_background():
                        yield tool_event
                yield create_error_event(
                    f"Agent execution failed: {str(e)}",
                    "AGENT_ERROR",
                )
                return

            raw_answer = result["final_answer"]
            tool_executions = result.get("tool_executions", 0)
            trace_id = result.get("trace_id", "unknown")

            llm_title, final_answer = extract_title_from_response(raw_answer)

            token_usage = extract_token_usage_from_agent_result(result)
            input_tokens = token_usage["input_tokens"]
            output_tokens = token_usage["output_tokens"]

            if "error" in result:
                logger.error(
                    "Agent execution failed with error",
                    chat_id=chat_id,
                    trace_id=trace_id,
                    error=result["error"],
                )
                yield create_error_event(
                    result["error"],
                    "AGENT_EXECUTION_FAILED",
                )
                return

            logger.info(
                "ReAct agent execution completed",
                chat_id=chat_id,
                trace_id=trace_id,
                tool_executions=tool_executions,
                answer_length=len(final_answer),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            if tool_executions > 0:
                yield format_sse_event(
                    {
                        "type": "tool_info",
                        "tool_executions": tool_executions,
                        "trace_id": trace_id,
                    }
                )

            await raise_if_disconnected(client_request)
            if final_answer:
                if not first_response_chunk_recorded:
                    first_response_chunk_recorded = True
                    yield create_latency_event(
                        "first_response_chunk",
                        get_elapsed_ms(),
                    )
                yield create_chunk_event(final_answer)

            await await_disconnect_grace(client_request)
            terminal_task = asyncio.create_task(
                chat_service.upsert_run_message(
                    chat_id=chat_id,
                    run_id=run_id,
                    content=final_answer,
                    metadata=MessageMetadata(
                        run_id=run_id,
                        run_status="completed",
                        trace_id=trace_id,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        raw_data={
                            "tool_executions": tool_executions,
                            "route_selected": route_metadata,
                            "agent_type": "react_sdk",
                        },
                    ),
                )
            )
            await asyncio.shield(terminal_task)

            await chat_service.update_title_if_new(
                chat_id=chat_id,
                llm_title=llm_title,
                user_message=request.message,
            )

            total_duration_ms = get_elapsed_ms()
            yield create_latency_event(
                "stream_complete",
                total_duration_ms,
                trace_id=trace_id,
                tool_executions=tool_executions,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            yield create_done_event(
                chat_id,
                tool_executions=tool_executions,
                trace_id=trace_id,
            )

        except (asyncio.CancelledError, ClientDisconnected) as exc:
            stream_active = False
            await cancel_and_await(agent_task)
            await await_task_completion(terminal_task)
            await persist_cancelled_run(
                chat_service=chat_service,
                chat_id=chat_id,
                user_id=user_id,
                run_id=run_id,
                language=request.language,
                agent_type="react_sdk",
                route_metadata=route_metadata,
            )
            logger.info("ReAct agent request cancelled", chat_id=chat_id)
            if isinstance(exc, asyncio.CancelledError):
                raise
            return
        except Exception as e:
            logger.error("Stream error (v3)", error=str(e), chat_id=chat_id)
            yield format_sse_event({"type": "error", "error": str(e)})

    return StreamingResponse(generate_stream(), media_type="text/event-stream")
