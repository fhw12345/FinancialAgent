"""Deep ReAct streaming with hierarchical research and optional debate."""

import asyncio
import os
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from fastapi import Request
from fastapi.responses import StreamingResponse

from ....core.utils import extract_token_usage_from_agent_result
from ....core.utils.date_utils import utcnow
from ....core.utils.title_utils import extract_title_from_response
from ....database.repositories.message_repository import MessageRepository
from ....services.agent_run_service import AgentRunService
from ....services.chat_service import ChatService
from ....services.context_window_manager import ContextWindowManager
from ...schemas.chat_models import ChatRequest
from .cancellation import (
    ClientDisconnected,
    await_disconnect_grace,
    await_task_or_disconnect,
    raise_if_disconnected,
)
from .deep_verdict_persistence import persist_completed_verdict
from .helpers import (
    create_chunk_event,
    create_done_event,
    create_latency_event,
    create_stream_mode_event,
    create_thinking_event,
    format_sse_event,
)
from .lifecycle import (
    ChatClarification,
    ChatCompletion,
    ChatFailure,
    ChatStreamLifecycle,
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
    run_id: str | None = None,
    run_service: AgentRunService | None = None,
) -> StreamingResponse:
    """Stream using Deep ReAct Agent (v4-deep) with hierarchical sub-agents."""

    async def generate_stream() -> AsyncGenerator[str, None]:
        collected_events: list[dict[str, Any]] = []
        first_progress_event_recorded = False
        first_response_chunk_recorded = False
        agent_task: asyncio.Task[Any] | None = None
        used_prompt_versions: dict[str, str] = {}
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

        async def persist_used_prompt_versions() -> None:
            if run_service is not None and used_prompt_versions:
                try:
                    await run_service.record_prompt_versions(
                        lifecycle.run_id,
                        dict(used_prompt_versions),
                    )
                except Exception:
                    logger.exception(
                        "Failed to persist Deep prompt versions",
                        run_id=lifecycle.run_id,
                    )

        try:
            # ===== Phase 1: Setup =====
            chat_created_event = await lifecycle.start()
            if chat_created_event:
                yield format_sse_event(chat_created_event)

            yield create_thinking_event("initializing", lifecycle.chat_id)

            prepared_context = await lifecycle.prepare_context(
                include_symbol_context=False
            )
            if prepared_context is None:
                yield create_done_event(lifecycle.require_chat_id())
                return

            conversation_history = prepared_context.history

            yield create_latency_event("context_prepared", lifecycle.elapsed_ms())
            yield create_thinking_event("deep_analysis", lifecycle.chat_id)
            yield create_stream_mode_event("buffered")

            resolution = await agent.resolve_symbol(
                user_message=request.message,
                current_symbol=request.current_symbol,
                conversation_history=conversation_history,
            )
            prompt_versions = resolution.prompt_versions
            if run_service is not None and prompt_versions:
                await run_service.record_prompt_versions(
                    lifecycle.run_id,
                    prompt_versions,
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
                async for event in lifecycle.clarify(
                    ChatClarification(
                        execution_mode="research",
                        agent_type="deep_react",
                        content=clarification_message,
                        payload=clarification,
                    )
                ):
                    yield event
                return

            logger.info(
                "Starting deep agent invocation",
                chat_id=lifecycle.chat_id,
                user_id=user_id,
                streaming_v2=DEEP_STREAMING_V2,
                message_preview=request.message[:100],
                elapsed_ms=lifecycle.elapsed_ms(),
            )

            # ===== Phase 2: Agent Invocation =====
            yield create_latency_event("agent_started", lifecycle.elapsed_ms())

            result: dict[str, Any]
            event_queue: asyncio.Queue[str | None] | None = None

            def on_event(event: dict[str, Any]) -> None:
                if event.get("type") == "prompt_used":
                    prompt_id = event.get("prompt_id")
                    version = event.get("version")
                    if isinstance(prompt_id, str) and isinstance(version, str):
                        used_prompt_versions[prompt_id] = version
                    return
                if event_queue is None:
                    return
                try:
                    event_queue.put_nowait(format_sse_event(event))
                    collected_events.append(event)
                except Exception:
                    logger.warning(
                        "Failed to enqueue SSE event",
                        event_type=event.get("type"),
                        exc_info=True,
                    )

            if DEEP_STREAMING_V2:
                event_queue = asyncio.Queue()
                result_holder: dict[str, Any] = {}

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
                    if not first_progress_event_recorded:
                        first_progress_event_recorded = True
                        yield create_latency_event(
                            "first_progress_event",
                            lifecycle.elapsed_ms(),
                        )
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
                            on_event=on_event,
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

        except (asyncio.CancelledError, ClientDisconnected, GeneratorExit) as exc:
            cancelled_event = {
                "type": "deep_cancelled",
                "seq": len(collected_events) + 1,
                "timestamp": utcnow().isoformat(),
            }
            await lifecycle.cancel(
                active_task=agent_task,
                agent_type="deep_react",
                extra_raw_data={
                    "deep_events": [*collected_events, cancelled_event],
                },
            )
            await persist_used_prompt_versions()
            logger.info("Deep agent request cancelled", chat_id=lifecycle.chat_id)
            if isinstance(exc, (asyncio.CancelledError, GeneratorExit)):
                raise
            return
        except TimeoutError:
            await persist_used_prompt_versions()
            logger.error(
                "Deep agent timeout",
                chat_id=lifecycle.chat_id,
                timeout_seconds=600,
            )
            # Persist partial events so the accordion can be restored.
            if collected_events and lifecycle.chat_id:
                try:
                    await chat_service.add_message(
                        chat_id=lifecycle.chat_id,
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
            async for event in lifecycle.fail(
                ChatFailure(
                    execution_mode="research",
                    error_code="AGENT_TIMEOUT",
                    error_message="Deep analysis timed out",
                    client_message=(
                        "Deep analysis timed out (10 min limit). "
                        "Try a simpler query."
                    ),
                )
            ):
                yield event
            return
        except Exception as e:
            await persist_used_prompt_versions()
            logger.error(
                "Deep agent execution error",
                chat_id=lifecycle.chat_id,
                error=str(e),
                exc_info=True,
            )
            if collected_events and lifecycle.chat_id:
                try:
                    await chat_service.add_message(
                        chat_id=lifecycle.chat_id,
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
            async for event in lifecycle.fail(
                ChatFailure(
                    execution_mode="research",
                    error_code="AGENT_ERROR",
                    error_message=str(e),
                    client_message=f"Deep analysis failed: {e!s}",
                )
            ):
                yield event
            return

        # ===== Phase 3: Process Result =====
        try:
            result_prompt_versions = result.get("prompt_versions", {})
            used_prompt_versions.update(result_prompt_versions)
            await persist_used_prompt_versions()
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
                    chat_id=lifecycle.chat_id,
                    error=result["error"],
                )
                async for event in lifecycle.fail(
                    ChatFailure(
                        execution_mode="research",
                        error_code="AGENT_EXECUTION_FAILED",
                        error_message=str(result["error"]),
                        client_message=str(result["error"]),
                    )
                ):
                    yield event
                return

            logger.info(
                "Deep agent execution completed",
                chat_id=lifecycle.chat_id,
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
            verdict = result.get("verdict")

            async def persist_verdict_after_durable_completion() -> None:
                await persist_completed_verdict(
                    agent=agent,
                    symbol=resolution.symbol,
                    verdict=verdict,
                    chat_id=lifecycle.require_chat_id(),
                    run_id=lifecycle.run_id,
                )

            async for event in lifecycle.complete(
                ChatCompletion(
                    content=final_answer,
                    execution_mode="research",
                    agent_type="deep_react",
                    llm_title=llm_title,
                    update_final_title=True,
                    trace_id=trace_id,
                    tool_calls=tool_executions,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    raw_data={
                        "tool_executions": tool_executions,
                        "agent_type": "deep_react",
                        "deep_events": collected_events,
                        "route_selected": route_metadata,
                        "research_context": result.get("research_context"),
                        "verdict": result.get("verdict"),
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
                    after_durable=persist_verdict_after_durable_completion,
                )
            ):
                yield event

        except (asyncio.CancelledError, ClientDisconnected, GeneratorExit) as exc:
            cancelled_event = {
                "type": "deep_cancelled",
                "seq": len(collected_events) + 1,
                "timestamp": utcnow().isoformat(),
            }
            await lifecycle.cancel(
                active_task=agent_task,
                agent_type="deep_react",
                extra_raw_data={
                    "deep_events": [*collected_events, cancelled_event],
                },
            )
            if isinstance(exc, (asyncio.CancelledError, GeneratorExit)):
                raise
            return
        except Exception as e:
            logger.error(
                "Stream error (v4-deep)",
                error=str(e),
                chat_id=lifecycle.chat_id,
            )
            async for event in lifecycle.fail(
                ChatFailure(
                    execution_mode="research",
                    error_code="STREAM_ERROR",
                    error_message=str(e),
                    client_message=str(e),
                    include_error_code=False,
                )
            ):
                yield event

    return StreamingResponse(generate_stream(), media_type="text/event-stream")
