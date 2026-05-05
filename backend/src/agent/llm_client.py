"""
LLM client wrapper - all calls now route through Agent Maestro (W8).

Historically this wrapped ChatTongyi/DashScope. After W8, all LLM traffic
goes through the Maestro gateway via langchain_anthropic.ChatAnthropic.
The class names (DashScopeClient, VisionClient) are preserved so existing
callers keep working without churn; internally they use llm_factory.get_llm.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..core.config import Settings
from ..core.localization import (
    DEFAULT_LANGUAGE,
    SupportedLanguage,
    get_language_instruction,
)
from .llm_factory import get_llm, resolve_model

logger = structlog.get_logger()


@dataclass
class TokenUsage:
    """Token usage information from LLM API."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


# Map legacy/qwen model strings -> Maestro role keys. Anything unknown
# falls back to "simple_chat".
_LEGACY_MODEL_TO_ROLE: dict[str, str] = {
    "qwen-plus": "simple_chat",
    "qwen-plus-latest": "simple_chat",
    "qwen-max": "react_agent",
    "qwen-max-latest": "react_agent",
    "qwen-turbo": "summary",
    "qwen-turbo-latest": "summary",
    "qwen-flash": "summary",
    "qwen-vl-max": "simple_chat",
    "deepseek-v3": "react_agent",
    "deepseek-v3.2-exp": "react_agent",
    "deepseek-chat": "react_agent",
}


def _model_to_role(model: str) -> str:
    return _LEGACY_MODEL_TO_ROLE.get(model, "simple_chat")


class DashScopeClient:
    """
    Backward-compatible LLM client - now routes through Agent Maestro.

    The legacy `model` argument is mapped to a Maestro role key so existing
    call sites (chat_agent, context_window_manager) keep working unchanged.
    """

    def __init__(self, settings: Settings, model: str = "qwen-plus"):
        self.model = model
        self.settings = settings
        self._role = _model_to_role(model)
        # streaming=True for astream_chat path
        self.chat = get_llm(self._role, streaming=True)
        logger.info(
            "Maestro LLM client initialized",
            legacy_model=model,
            role=self._role,
            resolved_model=resolve_model(self._role),
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
        thinking_enabled: bool = False,  # noqa: ARG002 - kept for API compat
    ) -> AsyncGenerator[str, None]:
        """Stream chat completion through Maestro."""
        lc_messages = self._convert_to_langchain_messages(messages)
        logger.info(
            "Streaming chat via Maestro",
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
                    text = (
                        chunk.content
                        if isinstance(chunk.content, str)
                        else str(chunk.content)
                    )
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
                "Maestro streaming chat failed",
                error=str(e),
                role=self._role,
                error_type=type(e).__name__,
            )
            raise

    def get_last_token_usage(self) -> TokenUsage | None:
        return self.last_token_usage


class VisionClient:
    """Vision-capable LLM client routed through Maestro (Claude vision)."""

    def __init__(self, settings: Settings, model: str = "qwen-vl-max"):
        self.model = model
        self.settings = settings
        # Use simple_chat role for vision (Claude haiku/sonnet support vision natively)
        self.chat = get_llm("simple_chat")
        logger.info("VisionClient initialized via Maestro", legacy_model=model)

    async def analyze_image(self, image_base64: str, prompt: str) -> str:
        """Analyze image with Claude vision via Maestro."""
        content: list[dict[str, Any]] = [
            {"type": "text", "text": prompt},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_base64,
                },
            },
        ]
        messages = [HumanMessage(content=content)]
        try:
            response = await self.chat.ainvoke(messages)
            return str(response.content) if response.content else ""
        except Exception as e:
            logger.error(
                "Vision analysis failed", error=str(e), error_type=type(e).__name__
            )
            raise


# Default system prompt for financial analysis
# Note: Use get_financial_agent_system_prompt() to get prompt with current date
FINANCIAL_AGENT_SYSTEM_PROMPT_TEMPLATE = """You are a senior financial analyst with 15+ years of Wall Street experience, conversing naturally with retail investors who value clarity and actionable insights.

**CRITICAL - Current Date: {current_date}**
Use this date as reference for all time-based queries (e.g., "past 6 months" = {six_months_ago} to {current_date}).

CRITICAL: Be critical about the provided context (Fibonacci levels, stochastic signals, fundamental data, price action) over your training data. The context contains real-time market analysis.

Tool Selection Strategy - CRITICAL:
**Start Broad -> Go Deep**: Build context before diving into details
- **Phase 1 (Overview)**: search_ticker, get_company_overview, get_market_movers
- **Phase 2 (Sentiment)**: get_news_sentiment
- **Phase 3 (Deep-Dive)**: get_financial_statements (cash_flow/balance_sheet), fibonacci_analysis_tool, stochastic_analysis_tool

**Execution Rules**:
- **Limit**: Call MAXIMUM 3 tools per reasoning iteration
- **Sequential**: Reason about results before calling next tool batch
- **Purpose-Driven**: Only call tools you need - don't call all tools at once
- **Smart Reasoning**: If overview + sentiment give clear answer, STOP there (no need for financials)

Response Style - Adapt to Context:
- Conclusion first
- Cite specific numbers, explain technical terms
- Honest risks
- Target 500-1000 tokens (hard limit: 3000 tokens)

You MUST:
- Base analysis on provided context data
- Explain technical terms when first introduced
- Reference exact price levels from context

You MUST NOT:
- Call all tools at once
- Use jargon without explanation
- Make vague statements without supporting data
- Exceed 3000 tokens
"""


def get_financial_agent_system_prompt() -> str:
    """Get the financial agent system prompt with current date injected."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Shanghai"))
    current_date = today.strftime("%Y-%m-%d")
    six_months_ago = (today - timedelta(days=180)).strftime("%Y-%m-%d")
    return FINANCIAL_AGENT_SYSTEM_PROMPT_TEMPLATE.format(
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
