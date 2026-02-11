"""
LangChain-based LLM client wrapper for Qwen and DeepSeek models.

Uses ChatTongyi (langchain-community) for ALL models via Alibaba Cloud DashScope:
- Qwen models: qwen-plus, qwen3-max
- DeepSeek models: deepseek-v3, deepseek-v3.2-exp (available on DashScope)
"""

from collections.abc import AsyncGenerator
from dataclasses import dataclass

import structlog
from langchain_community.chat_models import ChatTongyi
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..core.config import Settings
from ..core.localization import (
    DEFAULT_LANGUAGE,
    SupportedLanguage,
    get_language_instruction,
)

logger = structlog.get_logger()


@dataclass
class TokenUsage:
    """Token usage information from LLM API."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


class DashScopeClient:
    """
    LangChain-based client for Qwen and DeepSeek models via DashScope.

    Supports multi-turn conversations with model selection and thinking mode.
    Uses ChatTongyi for ALL models (Qwen + DeepSeek) through Alibaba Cloud DashScope API.
    """

    def __init__(self, settings: Settings, model: str = "qwen-plus"):
        """
        Initialize LangChain chat model client.

        Args:
            settings: Application settings with API keys
            model: Model ID (qwen-plus, qwen3-max, deepseek-v3, deepseek-v3.2-exp)
                   All models available through DashScope API
        """
        self.model = model
        self.settings = settings

        # Use ChatTongyi for ALL models - they're all available via DashScope
        # This includes: qwen-plus, qwen3-max, deepseek-v3, deepseek-v3.2-exp
        # Note: temperature, max_tokens, enable_thinking are passed per-request via bind()
        self.chat = ChatTongyi(  # type: ignore[call-arg]  # LangChain stubs incomplete
            model_name=model,
            dashscope_api_key=settings.dashscope_api_key,
            streaming=True,
            model_kwargs={
                "result_format": "message"  # Required for thinking mode support
            },
        )
        logger.info("ChatTongyi client initialized", model=model)

        # Track last token usage for retrieval after streaming
        self.last_token_usage: TokenUsage | None = None

    def _convert_to_langchain_messages(
        self, messages: list[dict[str, str]]
    ) -> list[SystemMessage | HumanMessage | AIMessage]:
        """
        Convert dict messages to LangChain message objects.

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            List of LangChain message objects
        """
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
        thinking_enabled: bool = False,
    ) -> AsyncGenerator[str, None]:
        """
        Async generator for streaming chat completion with LangChain.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens in response (default: 3000)
            thinking_enabled: Enable thinking mode (extracted from reasoning_content)

        Yields:
            str: Response content chunks as they arrive
                 Reasoning content wrapped in <thinking> tags
        """
        try:
            # Convert dict messages to LangChain format
            lc_messages = self._convert_to_langchain_messages(messages)

            logger.info(
                "Streaming chat with LangChain",
                model=self.model,
                thinking_enabled=thinking_enabled,
                message_count=len(messages),
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # Track if we've logged response structure and thinking state
            logged_structure = False
            thinking_started = False

            # Bind dynamic parameters (temperature, max_tokens, enable_thinking)
            # The bind() method passes parameters to DashScope API
            chat_with_params = self.chat.bind(
                temperature=temperature,
                max_tokens=max_tokens,
                enable_thinking=thinking_enabled,  # Pass to DashScope API
            )

            # Stream response from chat model
            async for chunk in chat_with_params.astream(lc_messages):
                # Log structure once for debugging
                if thinking_enabled and not logged_structure:
                    logger.info(
                        "LangChain streaming response structure (first chunk)",
                        has_reasoning_content="reasoning_content"
                        in chunk.additional_kwargs,
                        has_content=bool(chunk.content),
                        additional_kwargs_keys=list(chunk.additional_kwargs.keys()),
                    )
                    logged_structure = True

                # Extract reasoning_content (thinking mode) from additional_kwargs
                reasoning = chunk.additional_kwargs.get("reasoning_content", "")
                if reasoning:
                    # Send opening tag only once at the start of thinking
                    if not thinking_started:
                        yield "<thinking>"
                        thinking_started = True
                        logger.debug("Thinking mode started")

                    # Stream reasoning content without tags
                    yield reasoning

                # Yield regular content
                if chunk.content:
                    # Close thinking tag if we were in thinking mode
                    if thinking_started:
                        yield "</thinking>"
                        thinking_started = False
                        logger.debug("Thinking mode ended")

                    yield chunk.content  # type: ignore[misc]  # LangChain chunk.content can be list

                # Extract token usage from final chunk
                if chunk.response_metadata.get("finish_reason") == "stop":
                    token_usage = chunk.response_metadata.get("token_usage", {})
                    if token_usage:
                        self.last_token_usage = TokenUsage(
                            input_tokens=token_usage.get("input_tokens", 0),
                            output_tokens=token_usage.get("output_tokens", 0),
                            total_tokens=token_usage.get("total_tokens", 0),
                        )
                        logger.info(
                            "LangChain streaming completed",
                            input_tokens=self.last_token_usage.input_tokens,
                            output_tokens=self.last_token_usage.output_tokens,
                            total_tokens=self.last_token_usage.total_tokens,
                        )
                    else:
                        logger.warning(
                            "Token usage not available in final chunk",
                            response_metadata=chunk.response_metadata,
                        )

        except (ValueError, KeyError, AttributeError) as e:
            logger.error(
                "LangChain streaming chat failed - data error",
                error=str(e),
                model=self.model,
                error_type=type(e).__name__,
            )
            raise
        except Exception as e:
            logger.error(
                "LangChain streaming chat failed - unexpected error",
                error=str(e),
                model=self.model,
                error_type=type(e).__name__,
            )
            raise

    def get_last_token_usage(self) -> TokenUsage | None:
        """
        Get token usage from the last streaming/chat operation.

        Returns:
            TokenUsage if available, None otherwise
        """
        return self.last_token_usage


class VisionClient:
    """
    Vision model client for chart/image analysis.

    Uses Qwen-VL (qwen-vl-max) for multimodal image understanding.
    Designed for analyzing charts, patterns, and visual artifacts.
    """

    def __init__(self, settings: Settings, model: str = "qwen-vl-max"):
        """
        Initialize vision model client.

        Args:
            settings: Application settings with API keys
            model: Vision model ID (default: qwen-vl-max)
        """
        self.model = model
        self.settings = settings

        self.chat = ChatTongyi(  # type: ignore[call-arg]
            model_name=model,
            dashscope_api_key=settings.dashscope_api_key,
            model_kwargs={"result_format": "message"},
        )
        logger.info("VisionClient initialized", model=model)

    async def analyze_image(
        self,
        image_base64: str,
        prompt: str,
    ) -> str:
        """
        Analyze image with vision model.

        Args:
            image_base64: Base64-encoded image (without data:image/png;base64, prefix)
            prompt: Analysis prompt describing what to look for

        Returns:
            Vision model analysis as string
        """
        # Build multimodal content blocks for Qwen-VL
        content: list[dict[str, str | dict[str, str]]] = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_base64}"},
            },
        ]

        messages = [HumanMessage(content=content)]  # type: ignore[arg-type]

        logger.info(
            "Analyzing image with vision model",
            model=self.model,
            prompt_preview=prompt[:100],
        )

        try:
            response = await self.chat.ainvoke(messages)
            return str(response.content) if response.content else ""
        except Exception as e:
            logger.error(
                "Vision analysis failed",
                model=self.model,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise


# Default system prompt for financial analysis
# Note: Use get_financial_agent_system_prompt() to get prompt with current date
FINANCIAL_AGENT_SYSTEM_PROMPT_TEMPLATE = """You are a senior financial analyst with 15+ years of Wall Street experience, conversing naturally with retail investors who value clarity and actionable insights.

**CRITICAL - Current Date: {current_date}**
Use this date as reference for all time-based queries (e.g., "past 6 months" = {six_months_ago} to {current_date}).

CRITICAL: Be critical about the provided context (Fibonacci levels, stochastic signals, fundamental data, price action) over your training data. The context contains real-time market analysis.

Tool Selection Strategy - CRITICAL:
**Start Broad → Go Deep**: Build context before diving into details
- **Phase 1 (Overview)**: search_ticker, get_company_overview, get_market_movers
- **Phase 2 (Sentiment)**: get_news_sentiment
- **Phase 3 (Deep-Dive)**: get_financial_statements (cash_flow/balance_sheet), fibonacci_analysis_tool, stochastic_analysis_tool

**Execution Rules**:
- **Limit**: Call MAXIMUM 3 tools per reasoning iteration
- **Sequential**: Reason about results before calling next tool batch
- **Purpose-Driven**: Only call tools you need - don't call all tools at once
- **Smart Reasoning**: If overview + sentiment give clear answer, STOP there (no need for financials)

**Example Flow**:
User: "Analyze TSLA"
Step 1: Call get_company_overview, get_news_sentiment, get_market_movers (3 tools)
Step 2: Review results - if fundamentals strong + positive sentiment → can provide recommendation
Step 3: IF deeper financial health needed → call get_financial_statements(cash_flow)
Step 4: Synthesize final answer

User: "What's the market doing today?"
Step 1: Call get_market_movers (1 tool) - sufficient for overview
Step 2: Analyze and respond - no additional tools needed

**DELEGATION TO SUBAGENTS** (Advanced Pattern):
For complex analysis requiring deep research, use the task() tool to delegate:
- task("general-purpose", "your detailed task description")

The subagent has access to all your tools and returns ONLY a concise summary.

**WHEN TO DELEGATE:**
- Complex multi-step analysis (technical + fundamental combined)
- Tasks requiring extensive data gathering across multiple tools
- Getting balanced perspectives (analyst vs debater viewpoints)

**DUAL-AGENT PATTERN for investment decisions:**
1. task("general-purpose", "As a bullish analyst, make the data-driven case for [SYMBOL]. Include technical setup, fundamentals, and catalysts.")
2. task("general-purpose", "As a critical analyst, challenge the bull case for [SYMBOL]. Find risks, counter-evidence, and what could go wrong.")
3. Then synthesize both perspectives into a balanced recommendation.

**KEY BENEFIT:** Subagent work stays in isolated context - doesn't pollute your main conversation.

**VISUALIZATION SKILL:**
Use `generate_ohlc_chart(symbol, days)` to visualize price action and get structured metadata:
- Generates candlestick chart with SMA, Bollinger Bands, Fibonacci levels
- Returns: image path + technical indicators (RSI, trend, support/resistance)
- Use the METADATA for reasoning (free) - no need to "see" the chart

**For Visual Pattern Recognition** (expensive - use sparingly):
If you need to identify visual patterns (head & shoulders, triangles, flags):
1. First call generate_ohlc_chart() to get the base64 image data
2. Then: task("visual-analysis", "Identify chart patterns", image_base64=chart_data)
This uses qwen-vl-max vision model - only use when visual patterns are specifically requested.

Response Style - Adapt to Context:

**For Initial Analysis Requests:**
Structure your response logically with clear sections covering:
- Conclusion first (what's the bottom line?)
- Evidence from the data (cite specific numbers, explain technical terms)
- Actionable insights (what should investors do and why)
- Honest risks (what could invalidate this view)

**For Follow-Up Questions:**
- Be conversational and natural - no rigid formatting
- Match the tone and style established in the conversation history
- Reference previous analysis when relevant
- Keep the same formatting approach (tables, bullets, emphasis) as prior messages
- Answer directly without unnecessary structure

Writing Principles:
- **High signal-to-noise ratio**: Every sentence adds value
- **Explain like teaching a smart friend**: Assume curiosity, not expertise
- **Show your work**: Don't just state conclusions, explain reasoning
- **Use analogies** when helpful to connect abstract concepts
- **Confidence calibration**: Strong signals = strong language, weak signals = appropriate hedging
- **Target 500-1000 tokens** (hard limit: 3000 tokens)

You MUST:
- Base analysis on provided context data (Fibonacci, stochastic, support/resistance, etc.)
- Explain technical terms when first introduced
- Reference exact price levels from context (ONLY cite specific dates if tool output contains them)
- Use get_historical_prices tool when users ask about specific dates or price history
- Maintain formatting consistency with conversation history
- Keep responses concise with high information density
- Follow strategic tool calling pattern (broad → deep, max 3 per iteration)

You MUST NOT:
- Call all tools at once (wastes time and confuses user)
- Force rigid structure on follow-up questions
- Use jargon without explanation
- Make vague statements without supporting data
- Ignore or contradict provided analysis
- Include generic disclaimers (professional judgment is implied)
- Exceed 3000 tokens
- Fabricate or guess historical prices/dates not provided by tools (use get_historical_prices to verify)
"""


def get_financial_agent_system_prompt() -> str:
    """
    Get the financial agent system prompt with current date injected.

    The current date is critical for the LLM to correctly interpret
    relative time references like "past 6 months" or "last quarter".

    Returns:
        System prompt with current date context
    """
    from datetime import datetime, timedelta

    current_date = datetime.now().strftime("%Y-%m-%d")
    six_months_ago = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

    return FINANCIAL_AGENT_SYSTEM_PROMPT_TEMPLATE.format(
        current_date=current_date,
        six_months_ago=six_months_ago,
    )


# Backward compatibility alias (deprecated - use get_financial_agent_system_prompt())
FINANCIAL_AGENT_SYSTEM_PROMPT = get_financial_agent_system_prompt()


def get_system_prompt_with_language(
    language: SupportedLanguage = DEFAULT_LANGUAGE,
) -> str:
    """
    Get the financial agent system prompt with language instruction appended.

    Args:
        language: Target response language ("zh-CN" or "en")

    Returns:
        Complete system prompt with language requirement
    """
    return get_financial_agent_system_prompt() + get_language_instruction(language)
