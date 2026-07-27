"""Streaming LLM client routed through Agent Maestro."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..core.localization import (
    DEFAULT_LANGUAGE,
    SupportedLanguage,
    get_language_instruction,
)
from ..core.utils import message_content_to_text
from .llm_factory import get_llm, resolve_route
from .prompt_registry import get_prompt, render_prompt

logger = structlog.get_logger()


@dataclass
class TokenUsage:
    """Token usage information from LLM API."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


class StreamingLLMClient:
    """Streaming client for the configured ``simple_chat`` provider."""

    def __init__(self) -> None:
        self._role = "simple_chat"
        route = resolve_route(self._role)
        self.chat = get_llm(self._role, streaming=True)
        logger.info(
            "Streaming LLM client initialized",
            provider=route.provider,
            role=self._role,
            resolved_model=route.model,
            base_url=route.base_url,
        )
        self.last_token_usage: TokenUsage | None = None

    def _convert_to_langchain_messages(
        self, messages: list[dict[str, str]]
    ) -> list[SystemMessage | HumanMessage | AIMessage]:
        lc_messages: list[SystemMessage | HumanMessage | AIMessage] = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                logger.warning("Unknown message role", role=role)
        return lc_messages

    async def astream_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 3000,
    ) -> AsyncGenerator[str, None]:
        """Stream chat completion through the configured provider."""
        lc_messages = self._convert_to_langchain_messages(messages)
        logger.info(
            "Streaming chat",
            role=self._role,
            message_count=len(messages),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        chat = self.chat.bind(temperature=temperature, max_tokens=max_tokens)
        try:
            input_tokens = 0
            output_tokens = 0
            async for chunk in chat.astream(lc_messages):
                if chunk.content:
                    text = message_content_to_text(chunk.content)
                    yield text
                # Anthropic usage metadata appears on chunks
                usage = getattr(chunk, "usage_metadata", None) or {}
                if usage:
                    input_tokens = usage.get("input_tokens", input_tokens)
                    output_tokens = usage.get("output_tokens", output_tokens)
            self.last_token_usage = TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            )
        except Exception as e:
            logger.error(
                "Streaming chat failed",
                error=str(e),
                role=self._role,
                error_type=type(e).__name__,
            )
            raise

    def get_last_token_usage(self) -> TokenUsage | None:
        return self.last_token_usage


# Default system prompt for financial analysis
# Note: Use get_financial_agent_system_prompt() to get prompt with current date
FINANCIAL_AGENT_SYSTEM_PROMPT_TEMPLATE = get_prompt("financial-system").template


def get_financial_agent_system_prompt() -> str:
    """Get the financial agent system prompt with current date injected."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Shanghai"))
    current_date = today.strftime("%Y-%m-%d")
    six_months_ago = (today - timedelta(days=180)).strftime("%Y-%m-%d")
    return render_prompt(
        "financial-system",
        current_date=current_date,
        six_months_ago=six_months_ago,
    )


# Backward compatibility alias
FINANCIAL_AGENT_SYSTEM_PROMPT = get_financial_agent_system_prompt()


def get_system_prompt_with_language(
    language: SupportedLanguage = DEFAULT_LANGUAGE,
) -> str:
    """Get the financial agent system prompt with language instruction appended."""
    return get_financial_agent_system_prompt() + get_language_instruction(language)
