"""Shared lifecycle ownership for all chat streaming engines."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import structlog

from ....core.utils.date_utils import utcnow
from ....database.repositories.message_repository import MessageRepository
from ....models.agent_run import ExecutionMode
from ....models.message import Message, MessageMetadata
from ....services.agent_run_service import AgentRunService
from ....services.chat_service import ChatService
from ....services.context_window_manager import ContextWindowManager
from ....services.conversation_context_service import (
    ConversationContextService,
    PreparedConversationContext,
)
from ...schemas.chat_models import ChatRequest
from ..helpers import get_active_symbol_instruction, get_or_create_chat
from .cancellation import (
    await_task_completion,
    cancel_and_await,
    persist_cancelled_run,
)
from .helpers import (
    create_clarification_event,
    create_done_event,
    create_error_event,
    create_latency_event,
    create_run_state_event,
    format_sse_event,
)

logger = structlog.get_logger()


@dataclass(frozen=True)
class ChatCompletion:
    content: str
    execution_mode: ExecutionMode
    agent_type: str
    llm_title: str | None = None
    update_final_title: bool = False
    model: str | None = None
    trace_id: str | None = None
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int | None = None
    raw_data: dict[str, Any] | None = None
    latency_metrics: dict[str, Any] = field(default_factory=dict)
    done_data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatFailure:
    execution_mode: ExecutionMode
    error_code: str
    error_message: str
    client_message: str
    include_error_code: bool = True


@dataclass(frozen=True)
class ChatClarification:
    execution_mode: ExecutionMode
    agent_type: str
    content: str
    payload: dict[str, Any]


class ChatStreamLifecycle:
    def __init__(
        self,
        *,
        request: ChatRequest,
        user_id: str,
        chat_service: ChatService,
        context_manager: ContextWindowManager,
        message_repo: MessageRepository,
        route_metadata: dict[str, str] | None = None,
        run_id: str | None = None,
        run_service: AgentRunService | None = None,
    ) -> None:
        self.request = request
        self.user_id = user_id
        self.chat_service = chat_service
        self.context_manager = context_manager
        self.message_repo = message_repo
        self.route_metadata = route_metadata
        self.run_id = run_id or f"run_{uuid.uuid4().hex}"
        self.run_service = run_service
        self.chat_id: str | None = None
        self.current_message: Message | None = None
        self.prepared_context: PreparedConversationContext | None = None
        self.terminal_task: asyncio.Task[Any] | None = None
        self.request_start = utcnow()

    def elapsed_ms(self) -> int:
        return int((utcnow() - self.request_start).total_seconds() * 1000)

    def require_chat_id(self) -> str:
        if self.chat_id is None:
            raise RuntimeError("Chat lifecycle has not been started")
        return self.chat_id

    async def start(self) -> dict[str, Any] | None:
        """Create or load the chat and attach the durable run."""
        self.chat_id, chat_created_event = await get_or_create_chat(
            self.request,
            self.user_id,
            self.chat_service,
        )
        if self.run_service is not None:
            await self.run_service.attach_chat(self.run_id, self.chat_id)
        return dict(chat_created_event) if chat_created_event is not None else None

    async def persist_request(self) -> bool:
        """Persist the incoming message and report whether an engine should run."""
        chat_id = self.require_chat_id()
        if self.current_message is None:
            self.current_message = await self.chat_service.add_message(
                chat_id=chat_id,
                user_id=self.user_id,
                role=self.request.role,
                content=self.request.message,
                source=self.request.source,
                metadata=self.request.metadata,
                tool_call=self.request.tool_call,
            )
        return bool(self.request.role == "user" and self.request.source != "tool")

    async def prepare_context(
        self,
        *,
        include_symbol_context: bool,
    ) -> PreparedConversationContext | None:
        """Prepare the canonical Mongo-backed context for one engine."""
        if not await self.persist_request():
            return None

        chat_id = self.require_chat_id()
        current_message = self.current_message
        if current_message is None:
            raise RuntimeError("Current message was not persisted")

        await self._update_title(
            llm_title=None,
            current_symbol=self.request.current_symbol,
            stage="initial",
        )
        messages = await self.chat_service.get_chat_messages(
            chat_id,
            self.user_id,
        )
        symbol_instruction = ""
        symbol_source = None
        if include_symbol_context:
            symbol_instruction = await get_active_symbol_instruction(
                chat_id=chat_id,
                user_id=self.user_id,
                chat_service=self.chat_service,
                request_symbol=self.request.current_symbol,
            )
            symbol_source = (
                "request"
                if self.request.current_symbol
                else "chat_ui_state" if symbol_instruction else None
            )

        context_service = ConversationContextService(
            context_manager=self.context_manager,
            message_repo=self.message_repo,
        )
        self.prepared_context = await context_service.prepare(
            chat_id=chat_id,
            messages=messages,
            current_message=current_message,
            symbol_instruction=symbol_instruction,
            symbol_source=symbol_source,
        )
        return self.prepared_context

    async def complete(
        self,
        completion: ChatCompletion,
    ) -> AsyncGenerator[str, None]:
        """Persist completion and emit terminal state before post-run title I/O."""
        chat_id = self.require_chat_id()
        self.terminal_task = asyncio.create_task(
            self.chat_service.upsert_run_message(
                chat_id=chat_id,
                run_id=self.run_id,
                content=completion.content,
                metadata=MessageMetadata(
                    run_id=self.run_id,
                    run_status="completed",
                    model=completion.model,
                    tokens=completion.total_tokens,
                    trace_id=completion.trace_id,
                    input_tokens=completion.input_tokens,
                    output_tokens=completion.output_tokens,
                    raw_data=completion.raw_data,
                ),
            )
        )
        await asyncio.shield(self.terminal_task)

        if self.run_service is not None:
            try:
                completed_run = await self.run_service.complete(
                    self.run_id,
                    tool_calls=completion.tool_calls,
                    input_tokens=completion.input_tokens,
                    output_tokens=completion.output_tokens,
                )
            except Exception as exc:
                logger.exception(
                    "Failed to persist completed run transition",
                    run_id=self.run_id,
                )
                for event in await self._compensate_completion_failure(
                    completion,
                    exc,
                ):
                    yield event
                return
            if completed_run is not None:
                yield create_run_state_event(
                    self.run_id,
                    "completed",
                    completion.execution_mode,
                )

        if completion.update_final_title:
            await self._update_title(
                llm_title=completion.llm_title,
                current_symbol=None,
                stage="completed",
            )

        yield create_latency_event(
            "stream_complete",
            self.elapsed_ms(),
            trace_id=completion.trace_id,
            **completion.latency_metrics,
        )
        yield create_done_event(chat_id, **completion.done_data)

    async def fail(self, failure: ChatFailure) -> AsyncGenerator[str, None]:
        """Emit the legacy error shape and persist one failed run."""
        if failure.include_error_code:
            client_event = create_error_event(
                failure.client_message,
                failure.error_code,
            )
        else:
            client_event = format_sse_event(
                {
                    "type": "error",
                    "error": failure.client_message,
                }
            )

        yield client_event
        if self.run_service is not None:
            try:
                failed_run = await self.run_service.fail(
                    self.run_id,
                    error_code=failure.error_code,
                    error_message=failure.error_message,
                )
            except Exception:
                logger.exception(
                    "Failed to persist failed run transition",
                    run_id=self.run_id,
                    error_code=failure.error_code,
                )
                return
            if failed_run is not None:
                yield create_run_state_event(
                    self.run_id,
                    "failed",
                    failure.execution_mode,
                )

    async def clarify(
        self,
        clarification: ChatClarification,
    ) -> AsyncGenerator[str, None]:
        """Persist and emit clarification before the durable transition."""
        chat_id = self.require_chat_id()
        payload = clarification.payload
        await self.chat_service.add_message(
            chat_id=chat_id,
            user_id=self.user_id,
            role="assistant",
            content=clarification.content,
            source="llm",
            metadata={
                "run_id": self.run_id,
                "run_status": "waiting_for_input",
                "agent_type": clarification.agent_type,
                "raw_data": {
                    "clarification_required": {
                        "type": "clarification_required",
                        **payload,
                    },
                    "route_selected": self.route_metadata,
                },
            },
        )
        yield create_clarification_event(payload)
        if self.run_service is not None:
            try:
                waiting_run = await self.run_service.wait_for_input(
                    self.run_id,
                    metadata={
                        "clarification_type": payload.get("clarification_type"),
                        "reason_code": payload.get("reason_code"),
                    },
                )
            except Exception:
                logger.exception(
                    "Failed to persist waiting-for-input transition",
                    run_id=self.run_id,
                )
                async for event in self._compensate_clarification_failure(
                    clarification,
                    "waiting-for-input transition failed",
                ):
                    yield event
                return
            if waiting_run is not None:
                yield create_run_state_event(
                    self.run_id,
                    "waiting_for_input",
                    clarification.execution_mode,
                )
            else:
                async for event in self._compensate_clarification_failure(
                    clarification,
                    "waiting-for-input transition was rejected",
                ):
                    yield event
                return
        yield create_done_event(chat_id, clarification_required=True)

    async def cancel(
        self,
        *,
        active_task: asyncio.Task[Any] | None,
        agent_type: str,
        partial_content: str = "",
        extra_raw_data: dict[str, Any] | None = None,
        cancel_reason: str = "client_cancelled",
    ) -> None:
        """Cancel active work and persist the shared cancelled terminal state."""
        await cancel_and_await(active_task)
        await await_task_completion(self.terminal_task)
        await persist_cancelled_run(
            chat_service=self.chat_service,
            chat_id=self.chat_id,
            user_id=self.user_id,
            run_id=self.run_id,
            language=self.request.language,
            agent_type=agent_type,
            route_metadata=self.route_metadata,
            partial_content=partial_content,
            extra_raw_data=extra_raw_data,
            run_service=self.run_service,
            cancel_reason=cancel_reason,
        )

    async def _compensate_completion_failure(
        self,
        completion: ChatCompletion,
        error: Exception,
    ) -> list[str]:
        """Replace a completed message with a failed terminal record."""
        chat_id = self.require_chat_id()
        raw_data = {
            **(completion.raw_data or {}),
            "completion_persistence_error": str(error),
        }
        try:
            self.terminal_task = asyncio.create_task(
                self.chat_service.upsert_run_message(
                    chat_id=chat_id,
                    run_id=self.run_id,
                    content=completion.content,
                    metadata=MessageMetadata(
                        run_id=self.run_id,
                        run_status="failed",
                        model=completion.model,
                        tokens=completion.total_tokens,
                        trace_id=completion.trace_id,
                        input_tokens=completion.input_tokens,
                        output_tokens=completion.output_tokens,
                        raw_data=raw_data,
                    ),
                )
            )
            await asyncio.shield(self.terminal_task)
        except Exception:
            logger.exception(
                "Failed to compensate completed assistant message",
                run_id=self.run_id,
            )

        failure = ChatFailure(
            execution_mode=completion.execution_mode,
            error_code="RUN_COMPLETION_PERSISTENCE_ERROR",
            error_message=str(error),
            client_message=(
                "The response was generated, but its completion state "
                "could not be persisted."
            ),
        )
        return [event async for event in self.fail(failure)]

    async def _compensate_clarification_failure(
        self,
        clarification: ChatClarification,
        error_message: str,
    ) -> AsyncGenerator[str, None]:
        """Replace a waiting message when its run transition did not persist."""
        payload = clarification.payload
        try:
            self.terminal_task = asyncio.create_task(
                self.chat_service.upsert_run_message(
                    chat_id=self.require_chat_id(),
                    run_id=self.run_id,
                    content=clarification.content,
                    metadata=MessageMetadata(
                        run_id=self.run_id,
                        run_status="failed",
                        raw_data={
                            "agent_type": clarification.agent_type,
                            "failed_clarification": {
                                "type": "clarification_required",
                                **payload,
                            },
                            "route_selected": self.route_metadata,
                            "clarification_persistence_error": error_message,
                        },
                    ),
                )
            )
            await asyncio.shield(self.terminal_task)
        except Exception:
            logger.exception(
                "Failed to compensate clarification assistant message",
                run_id=self.run_id,
            )

        async for event in self.fail(
            ChatFailure(
                execution_mode=clarification.execution_mode,
                error_code="RUN_CLARIFICATION_PERSISTENCE_ERROR",
                error_message=error_message,
                client_message=(
                    "Clarification was generated, but its run state "
                    "could not be persisted."
                ),
            )
        ):
            yield event

    async def _update_title(
        self,
        *,
        llm_title: str | None,
        current_symbol: str | None,
        stage: str,
    ) -> None:
        try:
            await self.chat_service.update_title_if_new(
                chat_id=self.require_chat_id(),
                llm_title=llm_title,
                user_message=self.request.message,
                current_symbol=current_symbol,
            )
        except Exception:
            logger.warning(
                "Failed to update chat title",
                chat_id=self.chat_id,
                stage=stage,
                exc_info=True,
            )
