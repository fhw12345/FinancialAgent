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
from typing import Any, cast

import structlog

from ..core.localization import DEFAULT_LANGUAGE, SupportedLanguage
from ..core.utils import message_content_to_text
from ..models.symbol_resolution import SymbolResolution
from ..services.symbol_search_service import symbol_comparison_key
from .deep_react_agent import DeepReActAgent
from .deep_research_context import DeepResearchContext
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
        conversation_history: list[dict[str, str]] | None = None,
    ) -> SymbolResolution:
        """Resolve and validate the requested symbol before research starts."""
        resolution = await self.symbol_resolver.resolve(
            message=user_message,
            current_symbol=current_symbol,
        )
        prompt_versions = dict(resolution.prompt_versions)
        research_context = DeepResearchContext.from_history(
            current_request=user_message,
            conversation_history=conversation_history,
        )
        if (
            resolution.status == "unresolved"
            and resolution.reason_code == "symbol_missing"
            and current_symbol is None
            and research_context.allows_symbol_reuse
        ):
            historical_resolutions: list[SymbolResolution] = []
            for historical_symbol in research_context.symbol_candidates:
                historical_resolution = await self.symbol_resolver.resolve(
                    message=historical_symbol,
                    current_symbol=None,
                )
                prompt_versions.update(historical_resolution.prompt_versions)
                if historical_resolution.status == "resolved":
                    historical_resolutions.append(historical_resolution)
            if len(historical_resolutions) == 1:
                return cast(
                    SymbolResolution,
                    historical_resolutions[0].model_copy(
                        update={"prompt_versions": prompt_versions}
                    ),
                )
            if len(historical_resolutions) > 1:
                return SymbolResolution(
                    status="ambiguous",
                    source="explicit_ticker",
                    reason_code="ambiguous_historical_symbol",
                    confidence=max(item.confidence for item in historical_resolutions),
                    candidates=[
                        item.candidates[0]
                        for item in historical_resolutions
                        if item.candidates
                    ][:5],
                    prompt_versions=prompt_versions,
                )
        return cast(
            SymbolResolution,
            resolution.model_copy(update={"prompt_versions": prompt_versions}),
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
        1. Explicit ticker intent in the current message (instant)
        2. current_symbol from frontend UI state (instant)
        3. LLM extraction for company names in any language (~1s)

        Args:
            user_message: User's query (e.g., "Analyze TSLA")
            conversation_history: Mongo-authoritative prior messages
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
                conversation_history=conversation_history,
            )
            if resolution.status != "resolved" or resolution.symbol is None:
                raise ValueError("Deep Agent requires a resolved symbol")
            symbol = resolution.symbol

        research_context = DeepResearchContext.from_history(
            current_request=user_message,
            conversation_history=conversation_history,
        )
        history_target_matches = (
            research_context.confirmed_symbol is not None
            and symbol_comparison_key(research_context.confirmed_symbol)
            == symbol_comparison_key(symbol)
        )
        if conversation_history and not history_target_matches:
            research_context = research_context.for_new_symbol()

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
                research_context=research_context,
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
                "research_context": research_context.metadata(symbol=symbol),
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
