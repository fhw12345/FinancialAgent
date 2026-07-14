"""
Context window management for watchlist analysis.

Handles conversation history preparation and context compaction.
"""

import structlog

from ...database.repositories.message_repository import MessageRepository
from ...models.message import MessageCreate, MessageMetadata
from ..context_window_manager import ContextWindowManager

logger = structlog.get_logger()


class ContextHandler:
    """Manages conversation context for symbol analysis."""

    def __init__(
        self,
        message_repo: MessageRepository,
        context_manager: ContextWindowManager,
        settings,
        agent,
    ):
        """
        Initialize context handler.

        Args:
            message_repo: Repository for message operations
            context_manager: Context window manager
            settings: Application settings
            agent: LLM agent for summarization
        """
        self.message_repo = message_repo
        self.context_manager = context_manager
        self.settings = settings
        self.agent = agent

    async def prepare_conversation_history(
        self, historical_messages, chat_id: str, symbol: str
    ) -> list:
        """
        Prepare conversation history with context management.

        Args:
            historical_messages: List of historical messages
            chat_id: Chat ID for the symbol
            symbol: Stock symbol

        Returns:
            List of conversation history dicts
        """
        conversation_history = []

        if historical_messages:
            # Calculate total tokens
            total_tokens = self.context_manager.calculate_context_tokens(
                historical_messages
            )

            # Check if compaction is needed (> 50% of context limit)
            should_compact = self.context_manager.should_compact(total_tokens)

            if should_compact:
                logger.info(
                    "Context compaction triggered",
                    symbol=symbol,
                    total_tokens=total_tokens,
                    message_count=len(historical_messages),
                )

                # Extract HEAD, BODY, TAIL structure
                head, body, tail = self.context_manager.extract_context_structure(
                    historical_messages
                )

                # Summarize BODY using LLM
                summary_text = await self.context_manager.summarize_history(
                    body_messages=body,
                    symbol=symbol,
                    llm_service=self.agent,  # Use the agent's LLM for summarization
                )

                # Persist summary message to database
                if summary_text and body:
                    await self._persist_summary(
                        chat_id, symbol, summary_text, len(body)
                    )

                # Reconstruct compacted context
                compacted_messages = self.context_manager.reconstruct_context(
                    head=head, summary_text=summary_text, tail=tail
                )

                # Convert to conversation_history format
                for msg in compacted_messages:
                    conversation_history.append(
                        {"role": msg.role, "content": msg.content}
                    )

                logger.info(
                    "Context compacted successfully",
                    symbol=symbol,
                    original_count=len(historical_messages),
                    compacted_count=len(compacted_messages),
                    compression_ratio=round(
                        len(compacted_messages) / len(historical_messages), 3
                    ),
                )
            else:
                # No compaction needed - use full history
                for msg in historical_messages:
                    conversation_history.append(
                        {"role": msg.role, "content": msg.content}
                    )

                logger.info(
                    "Using full conversation history",
                    symbol=symbol,
                    total_tokens=total_tokens,
                    message_count=len(historical_messages),
                )

        return conversation_history

    async def _persist_summary(
        self, chat_id: str, symbol: str, summary_text: str, body_count: int
    ):
        """
        Persist summary message and delete old messages.

        Args:
            chat_id: Chat ID for the symbol
            symbol: Stock symbol
            summary_text: Summary text to persist
            body_count: Number of messages summarized
        """
        summary_metadata = MessageMetadata(
            symbol=symbol,
            is_summary=True,
            summarized_message_count=body_count,
        )
        summary_message_create = MessageCreate(
            chat_id=chat_id,
            role="assistant",
            content=f"## 📋 Analysis History Summary\n\n{summary_text}",
            source="llm",
            metadata=summary_metadata,
        )
        await self.message_repo.create(summary_message_create)

        # Delete old messages, keeping last N (tail_messages_keep)
        keep_count = self.settings.tail_messages_keep
        deleted_count = await self.message_repo.delete_old_messages_keep_recent(
            chat_id=chat_id,
            keep_count=keep_count,
            exclude_summaries=True,
        )

        logger.info(
            "Compaction persisted and old messages deleted",
            symbol=symbol,
            summarized_count=body_count,
            deleted_count=deleted_count,
            kept_count=keep_count,
        )
