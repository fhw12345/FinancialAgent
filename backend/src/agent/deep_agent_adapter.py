"""
Adapter for DeepReActAgent to match the ainvoke() interface.

Wraps DeepReActAgent.analyze() to return results in the same format
as FinancialAnalysisReActAgent.ainvoke(), enabling side-by-side usage
via agent_version="v4-deep" in the chat API.

The adapter handles:
- Symbol extraction from free-text user messages (LLM-powered)
- Interface translation (analyze → ainvoke format)
- Token usage extraction from sub-agent messages
- Timing and trace ID generation
"""

import time
import uuid
from collections.abc import Callable
from typing import Any

import structlog

from ..core.localization import DEFAULT_LANGUAGE, SupportedLanguage
from ..core.utils import message_content_to_text
from ..models.symbol_resolution import SymbolResolution
from .deep_react_agent import DeepReActAgent
from .symbol_resolver import SymbolResolver

logger = structlog.get_logger()


class DeepAgentAdapter:
    """Adapts DeepReActAgent to match FinancialAnalysisReActAgent.ainvoke() interface.

    Enables the deep hierarchical agent to be used via the same streaming
    handler pipeline as the standard ReAct agent.
    """

    def __init__(
        self,
        deep_agent: DeepReActAgent,
        symbol_resolver: SymbolResolver,
    ) -> None:
        self.deep_agent = deep_agent
        self.symbol_resolver = symbol_resolver

    async def resolve_symbol(
        self,
        *,
        user_message: str,
        current_symbol: str | None,
    ) -> SymbolResolution:
        """Resolve and validate the requested symbol before research starts."""
        return await self.symbol_resolver.resolve(
            message=user_message,
            current_symbol=current_symbol,
        )

    async def ainvoke(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        debug: bool = False,
        additional_callbacks: list[Any] | None = None,
        language: SupportedLanguage = DEFAULT_LANGUAGE,
        user_id: str = "anonymous",
        on_event: Callable[[dict[str, Any]], None] | None = None,
        current_symbol: str | None = None,
        resolved_symbol: str | None = None,
    ) -> dict[str, Any]:
        """Invoke deep agent with ainvoke-compatible interface.

        Symbol resolution priority:
        1. current_symbol from frontend UI state (instant)
        2. Regex match for explicit tickers in message (instant)
        3. LLM extraction for company names in any language (~1s)

        Args:
            user_message: User's query (e.g., "Analyze TSLA")
            conversation_history: Previous messages (logged, not forwarded to deep agent)
            debug: Enable debug logging
            additional_callbacks: Extra callbacks (not yet supported)
            language: Response language
            user_id: Authenticated user ID for session tracking
            on_event: Optional callback for streaming lifecycle events
            current_symbol: Symbol from frontend UI state (primary source)

        Returns:
            Dict matching FinancialAnalysisReActAgent.ainvoke() return format
        """
        trace_id = f"deep_{uuid.uuid4().hex[:12]}"
        start_time = time.perf_counter()

        symbol = resolved_symbol
        if symbol is None:
            resolution = await self.resolve_symbol(
                user_message=user_message,
                current_symbol=current_symbol,
            )
            if resolution.status != "resolved" or resolution.symbol is None:
                raise ValueError("Deep Agent requires a resolved symbol")
            symbol = resolution.symbol

        if conversation_history:
            logger.info(
                "DeepAgentAdapter received conversation history (not forwarded to deep agent)",
                history_length=len(conversation_history),
            )

        logger.info(
            "DeepAgentAdapter invocation started",
            trace_id=trace_id,
            symbol=symbol,
            user_id=user_id,
            user_message_preview=user_message[:100],
        )

        try:
            # Run deep analysis with optional event streaming
            result = await self.deep_agent.analyze(
                symbol=symbol,
                user_id=user_id,
                enable_debate=True,
                on_event=on_event,
                user_message=user_message,
            )

            # Extract final answer from research report or last message
            final_answer = message_content_to_text(result.get("research_report", ""))
            if not final_answer:
                messages = result.get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    final_answer = message_content_to_text(
                        last_msg.content if hasattr(last_msg, "content") else last_msg
                    )

            # Token usage already populated by analyze() — use directly
            all_messages = result.get("messages", [])
            tool_messages = [
                msg for msg in all_messages if msg.__class__.__name__ == "ToolMessage"
            ]

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            logger.info(
                "DeepAgentAdapter invocation completed",
                trace_id=trace_id,
                symbol=symbol,
                tool_executions=len(tool_messages),
                debate_rounds=result.get("round_count", 0),
                duration_ms=duration_ms,
            )

            return {
                "trace_id": trace_id,
                "messages": all_messages,
                "final_answer": final_answer,
                "tool_executions": len(tool_messages),
                "input_tokens": result.get("input_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
                "total_tokens": result.get("total_tokens", 0),
                "agent_duration_ms": duration_ms,
            }

        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error(
                "DeepAgentAdapter invocation failed",
                trace_id=trace_id,
                symbol=symbol,
                error=str(e),
                error_type=type(e).__name__,
            )
            return {
                "trace_id": trace_id,
                "messages": [],
                "final_answer": f"Deep analysis failed: {e!s}",
                "error": str(e),
                "tool_executions": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "agent_duration_ms": duration_ms,
            }
