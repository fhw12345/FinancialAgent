"""Simple multi-turn chat agent for financial analysis."""

from collections.abc import AsyncGenerator

import structlog

from ..core.config import Settings
from .llm_client import FINANCIAL_AGENT_SYSTEM_PROMPT, StreamingLLMClient, TokenUsage

logger = structlog.get_logger()


class ChatAgent:
    """
    Conversational agent for financial analysis.

    Lightweight wrapper around the configured simple-chat provider.
    Message history managed by MongoDB, not in-memory sessions.
    """

    def __init__(self, settings: Settings):
        """
        Initialize chat agent.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.system_prompt = FINANCIAL_AGENT_SYSTEM_PROMPT
        self.client = StreamingLLMClient()

        logger.info("ChatAgent initialized")

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 3000,
    ) -> AsyncGenerator[str, None]:
        """
        Stream LLM response for conversation history.

        Args:
            messages: Conversation history (without system prompt)
                     Format: [{"role": "user", "content": "..."}, ...]
            max_tokens: Maximum output tokens

        Yields:
            str: Response content chunks as they arrive
        """
        # Prepare messages with system prompt
        conversation_history = [
            {"role": "system", "content": self.system_prompt}
        ] + messages

        logger.info(
            "Streaming chat to LLM",
            max_tokens=max_tokens,
            message_count=len(messages),
            total_with_system=len(conversation_history),
        )

        async for chunk in self.client.astream_chat(
            messages=conversation_history,
            temperature=0.7,
            max_tokens=max_tokens,
        ):
            yield chunk

        logger.info("Streaming chat completed")

    def get_last_token_usage(self) -> TokenUsage | None:
        """Get token usage from the last chat operation."""
        return self.client.get_last_token_usage()
