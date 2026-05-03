"""
Context Window Manager for Portfolio Agent.

Implements sliding window + summary approach for managing long conversation histories.
When context exceeds threshold (75%), compacts history down to 25% by:
- Keeping HEAD (system prompt, tools)
- Keeping FILES (portfolio positions, watchlist)
- Compressing BODY (old analyses) → LLM-generated summary
- Keeping TAIL (last N exchanges)
"""

from datetime import datetime
from typing import Any

import structlog
import tiktoken

from src.core.utils.date_utils import utcnow

from ..core.config import Settings
from ..models.message import Message

logger = structlog.get_logger()


class ContextWindowManager:
    """Manages context window for portfolio agent with automatic summarization."""

    def __init__(self, settings: Settings):
        """
        Initialize context window manager.

        Args:
            settings: Application settings with context limits and thresholds
        """
        self.settings = settings
        self.context_limits = settings.llm_context_limits
        self.compact_threshold = settings.compact_threshold_ratio  # 0.5 = 50%
        self.compact_target = settings.compact_target_ratio  # 0.1 = 10%
        self.tail_keep = settings.tail_messages_keep  # 3 messages

        # Initialize tokenizer (using cl100k_base for GPT-4/Qwen compatibility)
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(
                "Failed to load tiktoken, using character approximation", error=str(e)
            )
            self.tokenizer = None

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Args:
            text: Input text

        Returns:
            Estimated token count

        Note:
            Uses tiktoken if available, otherwise approximates as chars/4.
            This is reusable across the application for token estimation.
        """
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        else:
            # Fallback: approximate as 1 token per 4 characters
            return len(text) // 4

    def calculate_message_tokens(self, message: Message) -> int:
        """
        Calculate tokens for a single message.

        Args:
            message: Message object

        Returns:
            Token count for message content
        """
        return self.estimate_tokens(message.content)

    def calculate_context_tokens(self, messages: list[Message]) -> int:
        """
        Calculate total tokens for a list of messages.

        Args:
            messages: List of message objects

        Returns:
            Sum of all message tokens
        """
        return sum(self.calculate_message_tokens(msg) for msg in messages)

    def should_compact(self, total_tokens: int, model: str = "qwen-plus") -> bool:
        """
        Check if context should be compacted.

        Args:
            total_tokens: Current total token count
            model: LLM model name to get limit for

        Returns:
            True if tokens exceed threshold (75% of limit)
        """
        limit = self.context_limits.get(model, 100_000)  # Default to 100K
        threshold = int(limit * self.compact_threshold)

        should_compact = total_tokens > threshold

        if should_compact:
            logger.info(
                "Context compaction needed",
                total_tokens=total_tokens,
                threshold=threshold,
                model=model,
                utilization_pct=round((total_tokens / limit) * 100, 1),
            )

        return should_compact

    def extract_context_structure(
        self, messages: list[Message]
    ) -> tuple[list[Message], list[Message], list[Message]]:
        """
        Extract HEAD, BODY, and TAIL from message history.

        Structure:
        - HEAD: System prompts (role='system'), tool definitions
        - BODY: Middle conversation history (to be summarized)
        - TAIL: Last N exchanges (kept as-is for continuity)

        Args:
            messages: Full message history

        Returns:
            Tuple of (head_messages, body_messages, tail_messages)
        """
        if not messages:
            return [], [], []

        # Extract HEAD: All system messages at the beginning
        head = []
        for msg in messages:
            if msg.role == "system":
                head.append(msg)
            else:
                break  # Stop at first non-system message

        # Extract TAIL: Last N exchanges
        tail_start_idx = max(len(head), len(messages) - self.tail_keep)
        tail = messages[tail_start_idx:]

        # BODY: Everything between HEAD and TAIL
        body = messages[len(head) : tail_start_idx]

        logger.debug(
            "Extracted context structure",
            head_count=len(head),
            body_count=len(body),
            tail_count=len(tail),
            total=len(messages),
        )

        return head, body, tail

    async def summarize_history(
        self,
        body_messages: list[Message],
        symbol: str | None = None,
        date_range: tuple[datetime, datetime] | None = None,
        llm_service: Any = None,  # Type hint as Any to avoid circular import
    ) -> str:
        """
        Summarize message history using LLM.

        Args:
            body_messages: Messages to summarize
            symbol: Optional symbol filter for context
            date_range: Optional date range for context
            llm_service: LLM service instance for generating summary

        Returns:
            Summary text (target: 10% of original tokens)
        """
        if not body_messages:
            return ""

        # Calculate current token count
        current_tokens = self.calculate_context_tokens(body_messages)
        target_tokens = int(current_tokens * self.compact_target)

        # Build summarization prompt
        context_info = []
        if symbol:
            context_info.append(f"Symbol: {symbol}")
        if date_range:
            start, end = date_range
            context_info.append(
                f"Date Range: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"
            )

        context_str = " | ".join(context_info) if context_info else "All analyses"

        # Extract message content
        history_text = "\n\n".join(
            [
                f"[{msg.role}] ({msg.timestamp if hasattr(msg, 'timestamp') else 'unknown'})\n{msg.content}"
                for msg in body_messages
            ]
        )

        summarization_prompt = f"""Summarize the following portfolio analysis history.

Context: {context_str}
Original length: {current_tokens} tokens
Target length: ~{target_tokens} tokens (25% of original)

Focus on:
1. Key trends and patterns observed across analyses
2. Repeated recommendations or consistent signals
3. Significant changes in sentiment or direction
4. Important risk factors or market conditions mentioned

History to summarize:
{history_text}

Provide a concise summary that captures the essential insights and patterns.
Format: Clear, structured summary with key points."""

        # Use LLM to generate summary
        if llm_service:
            try:
                from ..agent.llm_factory import get_llm

                # Use fast/cheap model for summarization (W8: routed via Maestro)
                llm = get_llm("summary", temperature=0.3, max_tokens=2048)

                # Invoke with simple prompt
                summary = await llm.ainvoke(
                    [{"role": "user", "content": summarization_prompt}]
                )

                summary_text = (
                    summary.content if hasattr(summary, "content") else str(summary)
                )

                logger.info(
                    "History summarized",
                    original_tokens=current_tokens,
                    summary_tokens=self.estimate_tokens(summary_text),
                    compression_ratio=round(
                        self.estimate_tokens(summary_text) / current_tokens, 3
                    ),
                    symbol=symbol,
                )

                return summary_text

            except Exception as e:
                logger.error(
                    "Summarization failed", error=str(e), error_type=type(e).__name__
                )
                # Fallback: Simple extraction of key points
                return self._fallback_summary(body_messages, symbol, date_range)
        else:
            logger.warning("No LLM service provided, using fallback summarization")
            return self._fallback_summary(body_messages, symbol, date_range)

    def _fallback_summary(
        self,
        messages: list[Message],
        symbol: str | None = None,
        date_range: tuple[datetime, datetime] | None = None,
    ) -> str:
        """
        Fallback summarization without LLM.

        Args:
            messages: Messages to summarize
            symbol: Symbol context
            date_range: Date range context

        Returns:
            Simple summary text
        """
        count = len(messages)
        context = f" for {symbol}" if symbol else ""
        date_str = ""
        if date_range:
            start, end = date_range
            date_str = (
                f" from {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"
            )

        return f"""Summary of {count} portfolio analyses{context}{date_str}.

Note: This is a simplified summary. Full analysis history has been compressed to save context tokens.
Key patterns and trends from the historical analyses are preserved in this summary."""

    def reconstruct_context(
        self, head: list[Message], summary_text: str, tail: list[Message]
    ) -> list[Message]:
        """
        Reconstruct compacted context: HEAD + [Summary Message] + TAIL.

        Args:
            head: System messages and tool definitions
            summary_text: Generated summary of body
            tail: Last N exchanges

        Returns:
            Compacted message list
        """
        # Create summary message (source='llm' because it's AI-generated summary)
        summary_message = Message(
            message_id=f"summary_{utcnow().strftime('%Y%m%d%H%M%S')}",
            chat_id="compacted_context",
            role="user",
            content=f"""Here is a summary of previous portfolio analyses:

{summary_text}

usage: continued""",
            source="llm",
            timestamp=utcnow().isoformat(),
        )

        # Reconstruct: HEAD + Summary + TAIL
        compacted = head + [summary_message] + tail

        logger.info(
            "Context reconstructed",
            original_structure=f"{len(head)} head + body + {len(tail)} tail",
            compacted_structure=f"{len(head)} head + 1 summary + {len(tail)} tail",
            total_messages=len(compacted),
        )

        return compacted
