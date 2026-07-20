"""
ReAct agent streaming handler (v3).

Streaming response logic for the ReAct Agent (v3): SSE streaming, tool
execution callbacks, latency metrics, and context management.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from fastapi import Request
from fastapi.responses import StreamingResponse

from ....agent.callbacks.tool_execution_callback import ToolExecutionCallback
from ....agent.langgraph_react_agent import FinancialAnalysisReActAgent
from ....core.utils import extract_token_usage_from_agent_result
from ....core.utils.title_utils import extract_title_from_response
from ....database.repositories.message_repository import MessageRepository
from ....services.agent_run_service import AgentRunService
from ....services.chat_service import ChatService
from ....services.context_window_manager import ContextWindowManager
from ...schemas.chat_models import ChatRequest
from .cancellation import (
    ClientDisconnected,
    await_disconnect_grace,
    raise_if_disconnected,
)
from .helpers import (
    create_chunk_event,
    create_done_event,
    create_latency_event,
    create_stream_mode_event,
    create_thinking_event,
    format_sse_event,
)
from .lifecycle import ChatCompletion, ChatFailure, ChatStreamLifecycle

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
    run_id: str | None = None,
    run_service: AgentRunService | None = None,
) -> StreamingResponse:
    """Stream using SDK ReAct Agent (v3) with real-time tool execution visibility."""

    async def generate_stream() -> AsyncGenerator[str, None]:
        tool_event_queue: asyncio.Queue[dict[str, Any]] | None = None
        agent_task: asyncio.Task[dict[str, Any]] | None = None
        stream_active = False
        first_response_chunk_recorded = False
        first_tool_recorded = False
        lifecycle = ChatStreamLifecycle(
            request=request,
            user_id=user_id,
            chat_service=chat_service,
            context_manager=context_manager,
            message_repo=message_repo,
            route_metadata=route_metadata,
            run_id=run_id,
            run_service=run_service,
        )

        try:
            chat_created_event = await lifecycle.start()
            if chat_created_event:
                yield format_sse_event(chat_created_event)

            yield create_thinking_event("initializing", lifecycle.chat_id)

            logger.debug(
                "Saving message with tool_call",
                has_tool_call=request.tool_call is not None,
            )
            prepared_context = await lifecycle.prepare_context(
                include_symbol_context=True
            )
            if prepared_context is None:
                yield create_done_event(lifecycle.require_chat_id())
                logger.info(
                    "Skipping agent invocation (v3)",
                    role=request.role,
                    source=request.source,
                    reason="non-user role or tool source",
                )
                return

            logger.info(
                "Conversation history prepared for agent",
                chat_id=lifecycle.chat_id,
                total_messages=prepared_context.persisted_message_count,
                conversation_history_count=prepared_context.history_message_count,
                elapsed_ms=lifecycle.elapsed_ms(),
            )

            yield create_latency_event("context_prepared", lifecycle.elapsed_ms())
            yield create_thinking_event("reasoning", lifecycle.chat_id)
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
                yield create_latency_event("agent_started", lifecycle.elapsed_ms())

                agent_task = asyncio.create_task(
                    asyncio.wait_for(
                        agent.ainvoke(
                            user_message=prepared_context.current_message,
                            conversation_history=prepared_context.history,
                            debug=debug,
                            additional_callbacks=[tool_callback],
                            language=request.language,
                            chat_id=lifecycle.require_chat_id(),
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
                            lifecycle.elapsed_ms(),
                            tool_name=tool_name,
                        )
                    yield tool_event

                result = await agent_task

            except TimeoutError:
                logger.error(
                    "Agent execution timeout",
                    chat_id=lifecycle.chat_id,
                    user_id=user_id,
                    timeout_seconds=120,
                )
                if tool_event_queue:
                    async for tool_event in stream_tool_events_background():
                        yield tool_event
                async for event in lifecycle.fail(
                    ChatFailure(
                        execution_mode="agentic",
                        error_code="AGENT_TIMEOUT",
                        error_message="ReAct agent timed out",
                        client_message=(
                            "Request timeout. The analysis is taking too long. "
                            "Please try again with a simpler question."
                        ),
                    )
                ):
                    yield event
                return
            except (asyncio.CancelledError, ClientDisconnected):
                raise
            except Exception as e:
                logger.error(
                    "Agent execution error",
                    chat_id=lifecycle.chat_id,
                    user_id=user_id,
                    error=str(e),
                    exc_info=True,
                )
                if tool_event_queue:
                    async for tool_event in stream_tool_events_background():
                        yield tool_event
                async for event in lifecycle.fail(
                    ChatFailure(
                        execution_mode="agentic",
                        error_code="AGENT_ERROR",
                        error_message=str(e),
                        client_message=f"Agent execution failed: {str(e)}",
                    )
                ):
                    yield event
                return

            raw_answer = result["final_answer"]
            tool_executions = result.get("tool_executions", 0)
            trace_id = result.get("trace_id", "unknown")

            llm_title, extracted_answer = extract_title_from_response(raw_answer)
            final_answer = extracted_answer or ""

            token_usage = extract_token_usage_from_agent_result(result)
            input_tokens = token_usage["input_tokens"]
            output_tokens = token_usage["output_tokens"]

            if "error" in result:
                logger.error(
                    "Agent execution failed with error",
                    chat_id=lifecycle.chat_id,
                    trace_id=trace_id,
                    error=result["error"],
                )
                async for event in lifecycle.fail(
                    ChatFailure(
                        execution_mode="agentic",
                        error_code="AGENT_EXECUTION_FAILED",
                        error_message=str(result["error"]),
                        client_message=str(result["error"]),
                    )
                ):
                    yield event
                return

            logger.info(
                "ReAct agent execution completed",
                chat_id=lifecycle.chat_id,
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
                        lifecycle.elapsed_ms(),
                    )
                yield create_chunk_event(final_answer)

            await await_disconnect_grace(client_request)
            async for event in lifecycle.complete(
                ChatCompletion(
                    content=final_answer,
                    execution_mode="agentic",
                    agent_type="react_sdk",
                    llm_title=llm_title,
                    update_final_title=True,
                    trace_id=trace_id,
                    tool_calls=tool_executions,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    raw_data={
                        "tool_executions": tool_executions,
                        "route_selected": route_metadata,
                        "agent_type": "react_sdk",
                    },
                    latency_metrics={
                        "tool_executions": tool_executions,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                    },
                    done_data={
                        "tool_executions": tool_executions,
                        "trace_id": trace_id,
                    },
                )
            ):
                yield event

        except (asyncio.CancelledError, ClientDisconnected, GeneratorExit) as exc:
            stream_active = False
            await lifecycle.cancel(
                active_task=agent_task,
                agent_type="react_sdk",
            )
            logger.info("ReAct agent request cancelled", chat_id=lifecycle.chat_id)
            if isinstance(exc, (asyncio.CancelledError, GeneratorExit)):
                raise
            return
        except Exception as e:
            logger.error(
                "Stream error (v3)",
                error=str(e),
                chat_id=lifecycle.chat_id,
            )
            async for event in lifecycle.fail(
                ChatFailure(
                    execution_mode="agentic",
                    error_code="STREAM_ERROR",
                    error_message=str(e),
                    client_message=str(e),
                    include_error_code=False,
                )
            ):
                yield event

    return StreamingResponse(generate_stream(), media_type="text/event-stream")
