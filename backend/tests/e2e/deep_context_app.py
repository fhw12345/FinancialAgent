"""FastAPI app with deterministic Deep execution for UAW-003 browser tests."""

from __future__ import annotations

from typing import Any

from src.agent.deep_research_context import DeepResearchContext
from src.agent.symbol_tokens import extract_explicit_symbols
from src.api.dependencies.chat_deps import get_deep_agent
from src.main import app
from src.models.symbol_resolution import SymbolCandidate, SymbolResolution


class DeterministicDeepAdapter:
    """Echo structured context while preserving the real chat pipeline."""

    async def resolve_symbol(
        self,
        *,
        user_message: str,
        current_symbol: str | None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> SymbolResolution:
        context = DeepResearchContext.from_history(
            current_request=user_message,
            conversation_history=conversation_history,
        )
        explicit_symbols = extract_explicit_symbols(user_message)
        explicit = explicit_symbols[-1] if explicit_symbols else None
        symbol = explicit or current_symbol or context.confirmed_symbol
        if symbol is None:
            return SymbolResolution(
                status="unresolved",
                source="llm_assisted",
                reason_code="symbol_missing",
            )
        candidate = SymbolCandidate(
            symbol=symbol,
            name="SK hynix" if symbol == "SKHY" else symbol,
            confidence=1.0,
            match_type="exact_symbol",
        )
        return SymbolResolution(
            status="resolved",
            source="ui_context",
            reason_code="resolved_ui_symbol",
            symbol=symbol,
            company_name=candidate.name,
            confidence=1.0,
            candidates=[candidate],
        )

    async def ainvoke(
        self,
        *,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        resolved_symbol: str | None = None,
        current_symbol: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        symbol = resolved_symbol or current_symbol or "UNKNOWN"
        context = DeepResearchContext.from_history(
            current_request=user_message,
            conversation_history=conversation_history,
        )
        metadata = context.metadata(symbol=symbol)
        constraints = ", ".join(context.constraints) or "none"
        previous = context.previous_assistant_report

        if previous:
            final_answer = (
                f"Follow-up Deep Research for {symbol}. "
                f"Previous thesis retained: {previous[:180]} "
                f"Horizon: {context.investment_horizon or 'not specified'}. "
                f"Risk tolerance: {context.risk_tolerance or 'not specified'}. "
                f"Constraints: {constraints}. "
                f"Context metadata: turns={len(context.relevant_turns)}, "
                f"previous_report=true, truncated={str(context.truncated).lower()}."
            )
        else:
            final_answer = (
                f"Baseline Deep Research for {symbol}. "
                "Thesis: bullish HBM demand with valuation risk. "
                f"Horizon: {context.investment_horizon or 'not specified'}. "
                f"Risk tolerance: {context.risk_tolerance or 'not specified'}. "
                f"Constraints: {constraints}. "
                "Context metadata: turns=0, previous_report=false, truncated=false."
            )

        return {
            "trace_id": "deep_e2e_context",
            "messages": [],
            "final_answer": final_answer,
            "tool_executions": 0,
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
            "research_context": metadata,
        }


_adapter = DeterministicDeepAdapter()
app.dependency_overrides[get_deep_agent] = lambda: _adapter
