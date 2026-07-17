"""
Simple agent streaming handler (v2).

This module contains the streaming response logic for the Simple Agent (v2),
handling SSE streaming and context management.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from fastapi import Request
from fastapi.responses import StreamingResponse

from ....agent.chat_agent import ChatAgent
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
    format_sse_event,
)

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
) -> StreamingResponse:
    """Stream using simple ChatAgent (v2) with context compaction."""

    async def generate_stream() -> AsyncGenerator[str, None]:
        chat_id = None
        active_task: asyncio.Task[None] | None = None
        terminal_task: asyncio.Task[Any] | None = None
        full_response = ""
        run_id = f"run_{uuid.uuid4().hex}"

        try:
            # Create or get chat
            chat_id, chat_created_event = await get_or_create_chat(
                request, user_id, chat_service
            )
            if chat_created_event:
                yield format_sse_event(chat_created_event)

            # Save user message
            current_message = await chat_service.add_message(
                chat_id=chat_id,
                user_id=user_id,
                role=request.role,
                content=request.message,
                source=request.source,
                metadata=request.metadata,
                tool_call=request.tool_call,
            )

            # Only invoke LLM for user messages from actual chat (not tool results or assistant messages)
            if request.role != "user" or request.source == "tool":
                yield create_done_event(chat_id)
                logger.info(
                    "Skipping agent invocation (v2)",
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

            messages_list = await chat_service.get_chat_messages(
                chat_id=chat_id, user_id=user_id
            )
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
                messages=messages_list,
                current_message=current_message,
                symbol_instruction=symbol_instruction,
                symbol_source=(
                    "request"
                    if request.current_symbol
                    else "chat_ui_state" if symbol_instruction else None
                ),
            )
            conversation_history = prepared_context.complete_history()

            logger.info(
                "Prepared conversation history (v2)",
                message_count=len(conversation_history),
                chat_id=chat_id,
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
                    yield create_chunk_event(chunk)

                await active_task
                if stream_error is not None:
                    raise stream_error
                await await_disconnect_grace(client_request)

            except TimeoutError:
                logger.error(
                    "Agent streaming timeout (v2)",
                    chat_id=chat_id,
                    user_id=user_id,
                    timeout_seconds=120,
                )
                yield create_error_event(
                    "Request timeout. The response is taking too long. Please try again.",
                    "STREAM_TIMEOUT",
                )
                return
            except (asyncio.CancelledError, ClientDisconnected):
                raise
            except Exception as e:
                logger.error(
                    "Agent streaming error (v2)",
                    chat_id=chat_id,
                    user_id=user_id,
                    error=str(e),
                    exc_info=True,
                )
                yield create_error_event(
                    f"Streaming failed: {str(e)}",
                    "STREAM_ERROR",
                )
                return

            # Get token usage from agent (best-effort, for telemetry only)
            token_usage = agent.get_last_token_usage()

            # Save assistant message
            terminal_task = asyncio.create_task(
                chat_service.upsert_run_message(
                    chat_id=chat_id,
                    run_id=run_id,
                    content=full_response,
                    metadata=MessageMetadata(
                        run_id=run_id,
                        run_status="completed",
                        model="simple_chat",
                        tokens=token_usage.total_tokens if token_usage else 0,
                        input_tokens=token_usage.input_tokens if token_usage else 0,
                        output_tokens=token_usage.output_tokens if token_usage else 0,
                        raw_data=(
                            {"route_selected": route_metadata}
                            if route_metadata is not None
                            else None
                        ),
                    ),
                )
            )
            await asyncio.shield(terminal_task)

            yield create_done_event(chat_id)

        except (asyncio.CancelledError, ClientDisconnected) as exc:
            await cancel_and_await(active_task)
            await await_task_completion(terminal_task)
            await persist_cancelled_run(
                chat_service=chat_service,
                chat_id=chat_id,
                user_id=user_id,
                run_id=run_id,
                language=request.language,
                agent_type="simple_chat",
                route_metadata=route_metadata,
                partial_content=full_response,
            )
            logger.info("Simple agent request cancelled", chat_id=chat_id)
            if isinstance(exc, asyncio.CancelledError):
                raise
            return
        except Exception as e:
            logger.error("Stream error (v2)", error=str(e), chat_id=chat_id)
            yield format_sse_event({"type": "error", "error": str(e)})

    return StreamingResponse(generate_stream(), media_type="text/event-stream")
