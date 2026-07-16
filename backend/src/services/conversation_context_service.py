"""Mongo-authoritative conversation context preparation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import structlog

from ..database.repositories.message_repository import MessageRepository
from ..models.message import Message, MessageCreate, MessageMetadata
from .context_window_manager import ContextWindowManager

logger = structlog.get_logger()


@dataclass(frozen=True)
class PreparedConversationContext:
    """Canonical context for one stateless conversational invocation."""

    history: list[dict[str, str]]
    current_message: str
    persisted_message_count: int
    history_message_count: int
    estimated_tokens: int
    compaction_applied: bool
    summary_used: bool
    symbol_source: str | None

    def complete_history(self) -> list[dict[str, str]]:
        """Return prior history plus the current user turn for direct chat."""
        return [
            *self.history,
            {"role": "user", "content": self.current_message},
        ]


class ConversationContextService:
    """Build token-bounded context exclusively from persisted Mongo messages."""

    def __init__(
        self,
        context_manager: ContextWindowManager,
        message_repo: MessageRepository,
    ) -> None:
        self._context_manager = context_manager
        self._message_repo = message_repo

    async def prepare(
        self,
        *,
        chat_id: str,
        messages: list[Message],
        current_message: Message,
        symbol_instruction: str = "",
        symbol_source: str | None = None,
    ) -> PreparedConversationContext:
        """Prepare prior history and the current enriched user turn."""
        prior_messages = [
            message
            for message in messages
            if message.message_id != current_message.message_id
        ]

        effective_messages, compacted = await self._compact_if_needed(
            chat_id=chat_id,
            messages=prior_messages,
        )
        history = [
            {"role": message.role, "content": message.content}
            for message in effective_messages
            if message.role in ("user", "assistant")
        ]
        enriched_current = current_message.content + symbol_instruction
        estimated_tokens = self._context_manager.calculate_context_tokens(
            effective_messages
        ) + self._context_manager.estimate_tokens(enriched_current)
        summary_used = any(
            message.metadata.is_summary for message in effective_messages
        )

        prepared = PreparedConversationContext(
            history=history,
            current_message=enriched_current,
            persisted_message_count=len(messages),
            history_message_count=len(history),
            estimated_tokens=estimated_tokens,
            compaction_applied=compacted,
            summary_used=summary_used,
            symbol_source=symbol_source,
        )
        logger.info(
            "conversation_context_prepared",
            chat_id=chat_id,
            context_source="mongodb",
            current_message_id=current_message.message_id,
            persisted_message_count=prepared.persisted_message_count,
            history_message_count=prepared.history_message_count,
            estimated_context_tokens=prepared.estimated_tokens,
            compaction_applied=prepared.compaction_applied,
            summary_used=prepared.summary_used,
            symbol_source=prepared.symbol_source,
        )
        return prepared

    async def _compact_if_needed(
        self,
        *,
        chat_id: str,
        messages: list[Message],
    ) -> tuple[list[Message], bool]:
        if not messages:
            return [], False

        total_tokens = self._context_manager.calculate_context_tokens(messages)
        if not self._context_manager.should_compact(total_tokens):
            return messages, False

        head, body, tail = self._context_manager.extract_context_structure(messages)
        if not body:
            return messages, False

        summary_text = await self._context_manager.summarize_history(
            body_messages=body,
            symbol=None,
            llm_service=True,
        )
        if not summary_text:
            raise RuntimeError("Conversation compaction produced no summary")

        summary_timestamp = body[-1].timestamp
        if tail:
            summary_timestamp = tail[0].timestamp - timedelta(microseconds=1)

        summary_message = await self._message_repo.create(
            MessageCreate(
                chat_id=chat_id,
                role="assistant",
                content=f"## Previous Conversation Summary\n\n{summary_text}",
                source="llm",
                metadata=MessageMetadata(
                    is_summary=True,
                    summarized_message_count=len(body),
                ),
                timestamp=summary_timestamp,
            )
        )
        deleted_count = await self._message_repo.delete_messages_by_ids(
            chat_id=chat_id,
            message_ids=[message.message_id for message in body],
        )
        if deleted_count != len(body):
            logger.warning(
                "conversation_compaction_delete_count_mismatch",
                chat_id=chat_id,
                expected=len(body),
                deleted=deleted_count,
            )

        logger.info(
            "conversation_context_compacted",
            chat_id=chat_id,
            original_tokens=total_tokens,
            summarized_message_count=len(body),
            deleted_message_count=deleted_count,
            retained_head_count=len(head),
            retained_tail_count=len(tail),
            summary_message_id=summary_message.message_id,
        )
        return [*head, summary_message, *tail], True
