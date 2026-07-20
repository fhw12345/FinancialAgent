"""
Simple agent streaming handler (v2).

This module contains the streaming response logic for the Simple Agent (v2),
handling SSE streaming and context management.
"""

import asyncio
from collections.abc import AsyncGenerator

import structlog
from fastapi import Request
from fastapi.responses import StreamingResponse

from ....agent.chat_agent import ChatAgent
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
    format_sse_event,
)
from .lifecycle import ChatCompletion, ChatFailure, ChatStreamLifecycle

logger = structlog.get_logger()


async def stream_with_simple_agent(
    request: ChatRequest,
    user_id: str,
    chat_service: ChatService,
    agent: ChatAgent,
    context_manager: ContextWindowManager,
    message_repo: MessageRepository,
    route_metadata: dict[str, str] | None = None,
    client_request: Request | None = None,
    run_id: str | None = None,
    run_service: AgentRunService | None = None,
) -> StreamingResponse:
    """Stream using simple ChatAgent (v2) with context compaction."""

    async def generate_stream() -> AsyncGenerator[str, None]:
        active_task: asyncio.Task[None] | None = None
        full_response = ""
        first_model_token_recorded = False
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

            prepared_context = await lifecycle.prepare_context(
                include_symbol_context=True
            )
            if prepared_context is None:
                yield create_done_event(lifecycle.require_chat_id())
                logger.info(
                    "Skipping agent invocation (v2)",
                    role=request.role,
                    source=request.source,
                    reason="non-user role or tool source",
                )
                return

            conversation_history = prepared_context.complete_history()
            yield create_stream_mode_event("model_tokens")

            logger.info(
                "Prepared conversation history (v2)",
                message_count=len(conversation_history),
                chat_id=lifecycle.chat_id,
            )

            # Pump provider chunks through a queue so disconnects are observed
            # even while waiting for the next model token.
            try:
                chunk_queue: asyncio.Queue[str | None] = asyncio.Queue()
                stream_error: BaseException | None = None

                async def run_agent_stream() -> None:
                    nonlocal stream_error
                    try:
                        async with asyncio.timeout(120.0):
                            async for chunk in agent.stream_chat(
                                messages=conversation_history,
                                language=request.language,
                            ):
                                await chunk_queue.put(chunk)
                    except BaseException as exc:
                        stream_error = exc
                    finally:
                        chunk_queue.put_nowait(None)

                active_task = asyncio.create_task(run_agent_stream())

                while True:
                    await raise_if_disconnected(client_request)
                    try:
                        chunk = await asyncio.wait_for(
                            chunk_queue.get(),
                            timeout=0.1,
                        )
                    except TimeoutError:
                        continue
                    if chunk is None:
                        break
                    full_response += chunk
                    if not first_model_token_recorded:
                        first_model_token_recorded = True
                        yield create_latency_event(
                            "first_model_token",
                            lifecycle.elapsed_ms(),
                        )
                    yield create_chunk_event(chunk)

                await active_task
                if stream_error is not None:
                    raise stream_error
                await await_disconnect_grace(client_request)

            except TimeoutError:
                logger.error(
                    "Agent streaming timeout (v2)",
                    chat_id=lifecycle.chat_id,
                    user_id=user_id,
                    timeout_seconds=120,
                )
                async for event in lifecycle.fail(
                    ChatFailure(
                        execution_mode="instant",
                        error_code="STREAM_TIMEOUT",
                        error_message="Direct model stream timed out",
                        client_message=(
                            "Request timeout. The response is taking too long. "
                            "Please try again."
                        ),
                    )
                ):
                    yield event
                return
            except (asyncio.CancelledError, ClientDisconnected):
                raise
            except Exception as e:
                logger.error(
                    "Agent streaming error (v2)",
                    chat_id=lifecycle.chat_id,
                    user_id=user_id,
                    error=str(e),
                    exc_info=True,
                )
                async for event in lifecycle.fail(
                    ChatFailure(
                        execution_mode="instant",
                        error_code="STREAM_ERROR",
                        error_message=str(e),
                        client_message=f"Streaming failed: {str(e)}",
                    )
                ):
                    yield event
                return

            token_usage = agent.get_last_token_usage()
            async for event in lifecycle.complete(
                ChatCompletion(
                    content=full_response,
                    execution_mode="instant",
                    agent_type="simple_chat",
                    model="simple_chat",
                    total_tokens=token_usage.total_tokens if token_usage else 0,
                    input_tokens=token_usage.input_tokens if token_usage else 0,
                    output_tokens=token_usage.output_tokens if token_usage else 0,
                    raw_data=(
                        {"route_selected": route_metadata}
                        if route_metadata is not None
                        else None
                    ),
                )
            ):
                yield event

        except (asyncio.CancelledError, ClientDisconnected, GeneratorExit) as exc:
            await lifecycle.cancel(
                active_task=active_task,
                agent_type="simple_chat",
                partial_content=full_response,
            )
            logger.info("Simple agent request cancelled", chat_id=lifecycle.chat_id)
            if isinstance(exc, (asyncio.CancelledError, GeneratorExit)):
                raise
            return
        except Exception as e:
            logger.error(
                "Stream error (v2)",
                error=str(e),
                chat_id=lifecycle.chat_id,
            )
            async for event in lifecycle.fail(
                ChatFailure(
                    execution_mode="instant",
                    error_code="STREAM_ERROR",
                    error_message=str(e),
                    client_message=str(e),
                    include_error_code=False,
                )
            ):
                yield event

    return StreamingResponse(generate_stream(), media_type="text/event-stream")
