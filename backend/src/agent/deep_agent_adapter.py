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

import re
import time
import uuid
from collections.abc import Callable
from typing import Any

import structlog
from langchain_core.messages import HumanMessage

from ..core.localization import DEFAULT_LANGUAGE, SupportedLanguage
from .deep_react_agent import DeepReActAgent

logger = structlog.get_logger()

# Regex: explicit all-caps ticker (1-5 chars, word boundary)
_TICKER_PATTERN = re.compile(r"\b([A-Z]{1,5})\b")

# Minimal set for instant regex match — only tickers that are also
# common English words (V, F, MA) or have dots (BRK.B) where regex alone
# might miss. The LLM fallback handles everything else.
_FAST_TICKERS: set[str] = {
    "AAPL",
    "MSFT",
    "GOOGL",
    "GOOG",
    "AMZN",
    "NVDA",
    "META",
    "TSLA",
    "NFLX",
    "AMD",
    "INTC",
    "COIN",
    "PLTR",
    "UBER",
    "SHOP",
    "SPOT",
    "BABA",
    "PDD",
    "NIO",
    "XPEV",
    "RIVN",
    "LCID",
    "SMCI",
    "ARM",
    "SOFI",
    "HOOD",
    "PYPL",
    "ABNB",
    "SNAP",
    "RBLX",
    "MSTR",
}

# Words to NEVER treat as tickers (common English/Chinese false positives)
_STOP_WORDS: set[str] = {
    "FOR",
    "AND",
    "NOT",
    "THE",
    "BUT",
    "ALL",
    "ARE",
    "CAN",
    "HAS",
    "HER",
    "HIS",
    "HOW",
    "ITS",
    "LET",
    "MAY",
    "NEW",
    "NOW",
    "OLD",
    "OUR",
    "OUT",
    "OWN",
    "SAY",
    "SHE",
    "TOO",
    "USE",
    "WAY",
    "WHO",
    "BOY",
    "DID",
    "GET",
    "HIM",
    "HIT",
    "LOW",
    "MAN",
    "RUN",
    "SET",
    "TOP",
    "TWO",
    "WHY",
    "BIG",
    "TRY",
    "ASK",
    "BUY",
    "CEO",
}

_SYMBOL_EXTRACTION_PROMPT = """Extract the stock ticker symbol from this user message.

Rules:
- Return ONLY the US stock ticker symbol (e.g., AAPL, TSLA, COIN)
- If the message mentions a company name (in any language), return its ticker
- If the message mentions multiple companies, return the PRIMARY one being discussed
- If you cannot identify any stock/company, return "UNKNOWN"
- Do NOT return anything else — just the ticker or UNKNOWN

Message: {message}

Ticker:"""


class DeepAgentAdapter:
    """Adapts DeepReActAgent to match FinancialAnalysisReActAgent.ainvoke() interface.

    Enables the deep hierarchical agent to be used via the same streaming
    handler pipeline as the standard ReAct agent.
    """

    def __init__(self, deep_agent: DeepReActAgent) -> None:
        self.deep_agent = deep_agent

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

        # Symbol resolution: frontend state → regex → LLM
        symbol = current_symbol or self._extract_symbol_fast(user_message)
        if not symbol:
            symbol = await self._extract_symbol_llm(user_message)

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
            final_answer = result.get("research_report", "")
            if not final_answer:
                messages = result.get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    final_answer = (
                        last_msg.content
                        if hasattr(last_msg, "content")
                        else str(last_msg)
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

    @staticmethod
    def _extract_symbol_fast(message: str) -> str | None:
        """Fast regex extraction for explicit ticker symbols.

        Returns None if no recognized ticker found — caller should
        fall back to LLM extraction.
        """
        candidates = _TICKER_PATTERN.findall(message)
        for candidate in candidates:
            if candidate in _STOP_WORDS:
                continue
            if candidate in _FAST_TICKERS:
                return candidate
            # Accept any 2-5 char all-caps word that's not a stop word
            # (likely a ticker the user typed explicitly)
            if len(candidate) >= 2:
                return candidate
        return None

    async def _extract_symbol_llm(self, message: str) -> str:
        """Use LLM to extract ticker from company names in any language.

        Single lightweight call (~1s). Falls back to AAPL only if LLM
        returns UNKNOWN or fails entirely.
        """
        try:
            prompt = _SYMBOL_EXTRACTION_PROMPT.format(message=message[:200])
            response = await self.deep_agent.llm.ainvoke(
                [HumanMessage(content=prompt)],
            )
            content = response.content
            raw = (
                (content if isinstance(content, str) else str(content)).strip().upper()
            )
            # Extract just the ticker — LLM may return extra text
            match = re.match(r"^([A-Z]{1,5})$", raw)
            if match and match.group(1) != "UNKNOWN":
                symbol = match.group(1)
                logger.info(
                    "LLM extracted symbol from message",
                    symbol=symbol,
                    message_preview=message[:80],
                )
                return symbol

            logger.warning(
                "LLM could not extract symbol, defaulting to AAPL",
                llm_response=raw[:50],
                message_preview=message[:80],
            )
            return "AAPL"
        except Exception:
            logger.warning(
                "LLM symbol extraction failed, defaulting to AAPL",
                message_preview=message[:80],
                exc_info=True,
            )
            return "AAPL"
