"""
Deep agent streaming handler (v4-deep).

This module contains the streaming response logic for the Deep ReAct Agent,
which uses hierarchical sub-agents (Technical, News, Financial, Debater)
with optional adversarial debate loop.

Key features:
- Real-time event streaming via asyncio.Queue + on_event callback
- Structured deep_* SSE events for frontend accordion tree
- Feature flag DEEP_STREAMING_V2 for gradual rollout
- Fallback to batch mode when streaming disabled
"""

import asyncio
import os
from collections.abc import AsyncGenerator
from typing import Any

import structlog
from fastapi.responses import StreamingResponse

from ....core.utils import extract_token_usage_from_agent_result
from ....core.utils.date_utils import utcnow
from ....core.utils.title_utils import extract_title_from_response
from ....database.repositories.message_repository import MessageRepository
from ....services.chat_service import ChatService
from ....services.context_window_manager import ContextWindowManager
from ....services.credit_service import CreditService
from ...schemas.chat_models import ChatRequest
from ..helpers import (
    compact_context_if_needed,
    get_or_create_chat,
)
from .helpers import (
    create_chunk_event,
    create_done_event,
    create_error_event,
    create_latency_event,
    create_thinking_event,
    format_sse_event,
)

logger = structlog.get_logger()

# Feature flag: enable structured event streaming (default: true)
DEEP_STREAMING_V2 = os.environ.get("DEEP_STREAMING_V2", "true").lower() in (
    "true",
    "1",
    "yes",
)


async def stream_with_deep_agent(
    request: ChatRequest,
    user_id: str,
    chat_service: ChatService,
    agent: Any,  # DeepAgentAdapter — lazy import to avoid startup crash if deepagents missing
    credit_service: CreditService,
    context_manager: ContextWindowManager,
    message_repo: MessageRepository,
    debug: bool = False,
) -> StreamingResponse:
    """Stream using Deep ReAct Agent (v4-deep) with hierarchical sub-agents.

    When DEEP_STREAMING_V2 is enabled, emits structured deep_* SSE events
    in real-time as sub-agents and tools execute. Otherwise, falls back to
    batch mode (wait for completion, then stream chunks).
    """

    async def generate_stream() -> AsyncGenerator[str, None]:
        chat_id = None
        transaction = None
        request_start = utcnow()
        ttft_recorded = False

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

            await chat_service.add_message(
                chat_id=chat_id,
                user_id=user_id,
                role=request.role,
                content=request.message,
                source=request.source or "chat",
                metadata=request.metadata,
                tool_call=request.tool_call,
            )

            if request.role != "user" or request.source == "tool":
                yield create_done_event(chat_id)
                return

            estimated_cost = 30.0
            has_credits = await credit_service.check_balance(
                user_id=user_id, estimated_cost=estimated_cost
            )
            if not has_credits:
                yield create_error_event(
                    "Insufficient credits. Deep analysis requires minimum 30 credits.",
                    "INSUFFICIENT_CREDITS",
                )
                return

            transaction = await credit_service.create_pending_transaction(
                user_id=user_id,
                chat_id=chat_id,
                estimated_cost=estimated_cost,
                model=request.model,
            )
            yield create_latency_event("credit_checked", get_elapsed_ms())

            # Context preparation
            messages = await chat_service.get_chat_messages(chat_id, user_id)
            conversation_history = await compact_context_if_needed(
                messages=messages,
                chat_id=chat_id,
                context_manager=context_manager,
                message_repo=message_repo,
                model=request.model,
            )
            if (
                conversation_history
                and conversation_history[-1]["role"] == "user"
                and conversation_history[-1]["content"] == request.message
            ):
                conversation_history = conversation_history[:-1]

            yield create_latency_event("context_prepared", get_elapsed_ms())
            yield create_thinking_event("deep_analysis", chat_id)

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
                # Real-time streaming: events flow through asyncio.Queue
                # as the agent emits them, instead of batching after completion
                event_queue: asyncio.Queue[str | None] = asyncio.Queue()
                result_holder: dict[str, Any] = {}

                def on_event(event: dict[str, Any]) -> None:
                    """Synchronous callback — push SSE string into queue.

                    Protected against serialization errors to prevent
                    crashing the agent task on malformed events.
                    """
                    try:
                        event_queue.put_nowait(format_sse_event(event))
                    except Exception:
                        logger.warning(
                            "Failed to enqueue SSE event",
                            event_type=event.get("type"),
                            exc_info=True,
                        )

                async def run_agent() -> None:
                    """Run agent in background task, signal completion via sentinel."""
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
                            ),
                            timeout=480.0,
                        )
                        result_holder.update(r)
                    finally:
                        await event_queue.put(None)  # sentinel

                agent_task = asyncio.create_task(run_agent())

                # Yield events in real-time as they arrive
                while True:
                    event_str = await event_queue.get()
                    if event_str is None:
                        break
                    if not ttft_recorded:
                        ttft_recorded = True
                        yield create_latency_event("first_event", get_elapsed_ms())
                    yield event_str

                # Propagate any agent exceptions
                await agent_task
                result = result_holder
            else:
                result = await asyncio.wait_for(
                    agent.ainvoke(
                        user_message=request.message,
                        conversation_history=conversation_history,
                        debug=debug,
                        language=request.language,
                        user_id=user_id,
                        current_symbol=request.current_symbol,
                    ),
                    timeout=480.0,
                )

        except TimeoutError:
            logger.error("Deep agent timeout", chat_id=chat_id, timeout_seconds=480)
            if transaction:
                await credit_service.fail_transaction(transaction.transaction_id)
            yield create_error_event(
                "Deep analysis timed out (8 min limit). Try a simpler query.",
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
            if transaction:
                await credit_service.fail_transaction(transaction.transaction_id)
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
                if transaction:
                    await credit_service.fail_transaction(transaction.transaction_id)
                yield create_error_event(result["error"], "AGENT_EXECUTION_FAILED")
                return

            logger.info(
                "Deep agent execution completed",
                chat_id=chat_id,
                trace_id=trace_id,
                tool_executions=tool_executions,
                answer_length=len(final_answer),
            )

            # Token estimation fallback
            if input_tokens == 0 and output_tokens == 0:
                logger.warning(
                    "No token usage from deep agent — using estimate",
                    chat_id=chat_id,
                )
                output_tokens = max(len(final_answer) // 4, 100)
                input_tokens = output_tokens * 3

            # Tool info (batch mode only — streaming mode sends per-tool events)
            if tool_executions > 0 and not DEEP_STREAMING_V2:
                yield format_sse_event(
                    {
                        "type": "tool_info",
                        "tool_executions": tool_executions,
                        "trace_id": trace_id,
                        "agent_type": "deep_react",
                    }
                )

            # Persist BEFORE streaming chunks — if SSE disconnects during
            # chunk delivery, the message is already saved to MongoDB.
            assistant_message = await chat_service.add_message(
                chat_id=chat_id,
                user_id=user_id,
                role="assistant",
                content=final_answer,
                source="llm",
                metadata={
                    "tool_executions": tool_executions,
                    "trace_id": trace_id,
                    "agent_type": "deep_react",
                    "transaction_id": transaction.transaction_id,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            )

            (
                updated_transaction,
                updated_user,
            ) = await credit_service.complete_transaction_with_deduction(
                transaction_id=transaction.transaction_id,
                message_id=assistant_message.message_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=request.model,
                thinking_enabled=request.thinking_enabled,
            )

            if updated_transaction and updated_user:
                logger.info(
                    "Transaction completed for deep agent",
                    transaction_id=updated_transaction.transaction_id,
                    actual_cost=updated_transaction.actual_cost,
                    remaining_credits=updated_user.credits,
                )

            await chat_service.update_title_if_new(
                chat_id=chat_id,
                llm_title=llm_title,
                user_message=request.message,
            )

            # Stream final answer in chunks (after persistence — safe if client disconnects)
            CHUNK_SIZE = 10
            for i in range(0, len(final_answer), CHUNK_SIZE):
                chunk_text = final_answer[i : i + CHUNK_SIZE]
                if not ttft_recorded:
                    ttft_recorded = True
                    yield create_latency_event("first_chunk", get_elapsed_ms())
                yield create_chunk_event(chunk_text)
                await asyncio.sleep(0.03)

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
                credits_used=(
                    updated_transaction.actual_cost if updated_transaction else 0
                ),
                remaining_credits=(updated_user.credits if updated_user else None),
            )

        except Exception as e:
            logger.error("Stream error (v4-deep)", error=str(e), chat_id=chat_id)
            if transaction:
                await credit_service.fail_transaction(transaction.transaction_id)
            yield format_sse_event({"type": "error", "error": str(e)})

    return StreamingResponse(generate_stream(), media_type="text/event-stream")
