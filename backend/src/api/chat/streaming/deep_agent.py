"""
Deep agent streaming handler (v4-deep).

Streaming response logic for the Deep ReAct Agent with hierarchical
sub-agents (Technical, News, Financial, Debater) and optional debate loop.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from fastapi import Request
from fastapi.responses import StreamingResponse

from ....core.utils import extract_token_usage_from_agent_result
from ....core.utils.date_utils import utcnow
from ....core.utils.title_utils import extract_title_from_response
from ....database.repositories.message_repository import MessageRepository
from ....models.message import MessageMetadata
from ....services.chat_service import ChatService
from ....services.context_window_manager import ContextWindowManager
from ....services.conversation_context_service import ConversationContextService
from ...schemas.chat_models import ChatRequest
from ..helpers import get_or_create_chat
from .cancellation import (
    ClientDisconnected,
    await_disconnect_grace,
    await_task_completion,
    await_task_or_disconnect,
    cancel_and_await,
    persist_cancelled_run,
    raise_if_disconnected,
)
from .helpers import (
    create_chunk_event,
    create_clarification_event,
    create_done_event,
    create_error_event,
    create_latency_event,
    create_thinking_event,
    format_sse_event,
)

logger = structlog.get_logger()

DEEP_STREAMING_V2 = os.environ.get("DEEP_STREAMING_V2", "true").lower() in (
    "true",
    "1",
    "yes",
)


async def stream_with_deep_agent(
    request: ChatRequest,
    user_id: str,
    chat_service: ChatService,
    agent: Any,  # DeepAgentAdapter — lazy import
    context_manager: ContextWindowManager,
    message_repo: MessageRepository,
    debug: bool = False,
    route_metadata: dict[str, str] | None = None,
    client_request: Request | None = None,
) -> StreamingResponse:
    """Stream using Deep ReAct Agent (v4-deep) with hierarchical sub-agents."""

    async def generate_stream() -> AsyncGenerator[str, None]:
        chat_id = None
        collected_events: list[dict[str, Any]] = []
        request_start = utcnow()
        ttft_recorded = False
        agent_task: asyncio.Task[Any] | None = None
        terminal_task: asyncio.Task[Any] | None = None
        run_id = f"run_{uuid.uuid4().hex}"

        def get_elapsed_ms() -> int:
            return int((utcnow() - request_start).total_seconds() * 1000)

        try:
            # ===== Phase 1: Setup =====
            chat_id, chat_created_event = await get_or_create_chat(
                request, user_id, chat_service
            )
            if chat_created_event:
                yield format_sse_event(chat_created_event)

            yield create_thinking_event("initializing", chat_id)

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
                return

            await chat_service.update_title_if_new(
                chat_id=chat_id,
                llm_title=None,
                user_message=request.message,
                current_symbol=request.current_symbol,
            )

            messages = await chat_service.get_chat_messages(chat_id, user_id)
            context_service = ConversationContextService(
                context_manager=context_manager,
                message_repo=message_repo,
            )
            prepared_context = await context_service.prepare(
                chat_id=chat_id,
                messages=messages,
                current_message=current_message,
            )
            conversation_history = prepared_context.history

            yield create_latency_event("context_prepared", get_elapsed_ms())
            yield create_thinking_event("deep_analysis", chat_id)

            resolution = await agent.resolve_symbol(
                user_message=request.message,
                current_symbol=request.current_symbol,
                conversation_history=conversation_history,
            )
            if resolution.status != "resolved" or resolution.symbol is None:
                has_candidates = bool(resolution.candidates)
                if request.language == "zh-CN":
                    clarification_message = (
                        "请选择要分析的公司。"
                        if has_candidates
                        else "我无法确定你要分析的股票。"
                    )
                else:
                    clarification_message = (
                        "Please select the company you want to analyze."
                        if has_candidates
                        else "I could not identify the stock you want to analyze."
                    )
                clarification = {
                    "clarification_type": "symbol",
                    "reason_code": resolution.reason_code,
                    "message": clarification_message,
                    "original_request": request.message,
                    "candidates": [
                        candidate.model_dump() for candidate in resolution.candidates
                    ],
                }
                await chat_service.add_message(
                    chat_id=chat_id,
                    user_id=user_id,
                    role="assistant",
                    content=clarification_message,
                    source="llm",
                    metadata={
                        "agent_type": "deep_react",
                        "raw_data": {
                            "clarification_required": {
                                "type": "clarification_required",
                                **clarification,
                            },
                            "route_selected": route_metadata,
                        },
                    },
                )
                yield create_clarification_event(clarification)
                yield create_done_event(chat_id, clarification_required=True)
                return

            logger.info(
                "Starting deep agent invocation",
                chat_id=chat_id,
                user_id=user_id,
                streaming_v2=DEEP_STREAMING_V2,
                message_preview=request.message[:100],
                elapsed_ms=get_elapsed_ms(),
            )

            # ===== Phase 2: Agent Invocation =====
            yield create_latency_event("agent_started", get_elapsed_ms())

            result: dict[str, Any]

            if DEEP_STREAMING_V2:
                event_queue: asyncio.Queue[str | None] = asyncio.Queue()
                result_holder: dict[str, Any] = {}

                def on_event(event: dict[str, Any]) -> None:
                    try:
                        event_queue.put_nowait(format_sse_event(event))
                        collected_events.append(event)
                    except Exception:
                        logger.warning(
                            "Failed to enqueue SSE event",
                            event_type=event.get("type"),
                            exc_info=True,
                        )

                async def run_agent() -> None:
                    try:
                        r = await asyncio.wait_for(
                            agent.ainvoke(
                                user_message=request.message,
                                conversation_history=conversation_history,
                                debug=debug,
                                language=request.language,
                                user_id=user_id,
                                on_event=on_event,
                                current_symbol=request.current_symbol,
                                resolved_symbol=resolution.symbol,
                            ),
                            timeout=600.0,
                        )
                        result_holder.update(r)
                    finally:
                        event_queue.put_nowait(None)

                agent_task = asyncio.create_task(run_agent())

                while True:
                    await raise_if_disconnected(client_request)
                    try:
                        event_str = await asyncio.wait_for(
                            event_queue.get(),
                            timeout=0.1,
                        )
                    except TimeoutError:
                        continue
                    if event_str is None:
                        break
                    if not ttft_recorded:
                        ttft_recorded = True
                        yield create_latency_event("first_event", get_elapsed_ms())
                    yield event_str

                await agent_task
                result = result_holder
            else:
                agent_task = asyncio.create_task(
                    asyncio.wait_for(
                        agent.ainvoke(
                            user_message=request.message,
                            conversation_history=conversation_history,
                            debug=debug,
                            language=request.language,
                            user_id=user_id,
                            current_symbol=request.current_symbol,
                            resolved_symbol=resolution.symbol,
                        ),
                        timeout=600.0,
                    )
                )
                result = await await_task_or_disconnect(
                    agent_task,
                    client_request,
                )

        except (asyncio.CancelledError, ClientDisconnected) as exc:
            await cancel_and_await(agent_task)
            await await_task_completion(terminal_task)
            cancelled_event = {
                "type": "deep_cancelled",
                "seq": len(collected_events) + 1,
                "timestamp": utcnow().isoformat(),
            }
            await persist_cancelled_run(
                chat_service=chat_service,
                chat_id=chat_id,
                user_id=user_id,
                run_id=run_id,
                language=request.language,
                agent_type="deep_react",
                route_metadata=route_metadata,
                extra_raw_data={
                    "deep_events": [*collected_events, cancelled_event],
                },
            )
            logger.info("Deep agent request cancelled", chat_id=chat_id)
            if isinstance(exc, asyncio.CancelledError):
                raise
            return
        except TimeoutError:
            logger.error("Deep agent timeout", chat_id=chat_id, timeout_seconds=600)
            # Persist partial events so the accordion can be restored.
            if collected_events and chat_id:
                try:
                    await chat_service.add_message(
                        chat_id=chat_id,
                        user_id=user_id,
                        role="assistant",
                        content="Deep analysis timed out. Partial results may be available.",
                        source="llm",
                        metadata={
                            "agent_type": "deep_react",
                            "raw_data": {
                                "deep_events": collected_events,
                                "route_selected": route_metadata,
                            },
                        },
                    )
                except Exception:
                    logger.warning("Failed to persist partial deep events on timeout")
            yield create_error_event(
                "Deep analysis timed out (10 min limit). Try a simpler query.",
                "AGENT_TIMEOUT",
            )
            return
        except Exception as e:
            logger.error(
                "Deep agent execution error",
                chat_id=chat_id,
                error=str(e),
                exc_info=True,
            )
            if collected_events and chat_id:
                try:
                    await chat_service.add_message(
                        chat_id=chat_id,
                        user_id=user_id,
                        role="assistant",
                        content=f"Deep analysis encountered an error: {e!s}",
                        source="llm",
                        metadata={
                            "agent_type": "deep_react",
                            "raw_data": {
                                "deep_events": collected_events,
                                "route_selected": route_metadata,
                            },
                        },
                    )
                except Exception:
                    logger.warning("Failed to persist partial deep events on error")
            yield create_error_event(f"Deep analysis failed: {e!s}", "AGENT_ERROR")
            return

        # ===== Phase 3: Process Result =====
        try:
            raw_answer = result["final_answer"]
            tool_executions = result.get("tool_executions", 0)
            trace_id = result.get("trace_id", "unknown")

            llm_title, final_answer = extract_title_from_response(raw_answer)
            final_answer = final_answer or ""

            token_usage = extract_token_usage_from_agent_result(result)
            input_tokens = token_usage["input_tokens"]
            output_tokens = token_usage["output_tokens"]

            if "error" in result:
                logger.error(
                    "Deep agent returned error",
                    chat_id=chat_id,
                    error=result["error"],
                )
                yield create_error_event(result["error"], "AGENT_EXECUTION_FAILED")
                return

            logger.info(
                "Deep agent execution completed",
                chat_id=chat_id,
                trace_id=trace_id,
                tool_executions=tool_executions,
                answer_length=len(final_answer),
            )

            if tool_executions > 0 and not DEEP_STREAMING_V2:
                yield format_sse_event(
                    {
                        "type": "tool_info",
                        "tool_executions": tool_executions,
                        "trace_id": trace_id,
                        "agent_type": "deep_react",
                    }
                )

            CHUNK_SIZE = 10
            for i in range(0, len(final_answer), CHUNK_SIZE):
                await raise_if_disconnected(client_request)
                chunk_text = final_answer[i : i + CHUNK_SIZE]
                if not ttft_recorded:
                    ttft_recorded = True
                    yield create_latency_event("first_chunk", get_elapsed_ms())
                yield create_chunk_event(chunk_text)
                await asyncio.sleep(0.03)

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
                            "agent_type": "deep_react",
                            "deep_events": collected_events,
                            "route_selected": route_metadata,
                            "research_context": result.get("research_context"),
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
            await cancel_and_await(agent_task)
            await await_task_completion(terminal_task)
            cancelled_event = {
                "type": "deep_cancelled",
                "seq": len(collected_events) + 1,
                "timestamp": utcnow().isoformat(),
            }
            await persist_cancelled_run(
                chat_service=chat_service,
                chat_id=chat_id,
                user_id=user_id,
                run_id=run_id,
                language=request.language,
                agent_type="deep_react",
                route_metadata=route_metadata,
                extra_raw_data={
                    "deep_events": [*collected_events, cancelled_event],
                },
            )
            if isinstance(exc, asyncio.CancelledError):
                raise
            return
        except Exception as e:
            logger.error("Stream error (v4-deep)", error=str(e), chat_id=chat_id)
            yield format_sse_event({"type": "error", "error": str(e)})

    return StreamingResponse(generate_stream(), media_type="text/event-stream")
