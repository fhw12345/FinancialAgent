from __future__ import annotations

import time
from typing import Any

from src.agent.llm_factory import resolve_route
from src.agent.prompt_registry import get_prompt

from .live_gateway import LiveModelGateway
from .live_schemas import (
    LiveEvaluationCase,
    LiveEvaluationRequest,
    LiveTargetResult,
)
from .model_budget import (
    EvaluationBudgetExceeded,
    EvaluationModelBudgetCallback,
)
from .pricing import build_model_usage
from .rubric import compose_evaluation_input
from .tool_evidence import (
    EvaluationToolTraceCallback,
    collect_tool_evidence,
)


class ProviderSmokeGateway(LiveModelGateway):
    def __init__(self, request: LiveEvaluationRequest, react_agent: Any) -> None:
        super().__init__(request)
        self.react_agent = react_agent

    async def _generate_react(
        self,
        case: LiveEvaluationCase,
        observed_flow: str,
        *,
        max_cost_usd: float,
    ) -> LiveTargetResult:
        tool_trace = EvaluationToolTraceCallback()
        route = resolve_route("react_agent")
        model_budget = EvaluationModelBudgetCallback(
            role="react_agent",
            provider=route.provider,
            model=route.model,
            max_cost_usd=max_cost_usd,
            max_output_tokens_per_call=case.max_target_output_tokens,
            pricing_overrides=self.request.pricing_overrides,
        )
        started = time.perf_counter()
        prompt_spec = get_prompt("financial-system")
        try:
            result = await self.react_agent.ainvoke(
                user_message=compose_evaluation_input(case),
                conversation_history=[],
                language=case.language,
                additional_callbacks=[tool_trace, model_budget],
            )
        except EvaluationBudgetExceeded as exc:
            return LiveTargetResult(
                observed_flow=observed_flow,
                final_answer="",
                prompt_versions={prompt_spec.prompt_id: prompt_spec.versioned_id},
                model_usages=model_budget.usages,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=str(exc),
                budget_exhausted=True,
            )
        duration_ms = (time.perf_counter() - started) * 1000
        messages = list(result.get("messages", []))
        result_error = str(result["error"]) if result.get("error") else None
        budget_exhausted = bool(
            result_error and "Insufficient target budget" in result_error
        )
        usage = build_model_usage(
            role="react_agent",
            provider=route.provider,
            model=route.model,
            input_tokens=int(result.get("input_tokens", 0) or 0),
            output_tokens=int(result.get("output_tokens", 0) or 0),
            duration_ms=duration_ms,
            overrides=self.request.pricing_overrides,
        )
        return LiveTargetResult(
            observed_flow=observed_flow,
            final_answer=str(result.get("final_answer", "")),
            tools=collect_tool_evidence(messages, tool_trace.completed),
            prompt_versions={prompt_spec.prompt_id: prompt_spec.versioned_id},
            model_usages=model_budget.usages if budget_exhausted else [usage],
            duration_ms=duration_ms,
            error=result_error,
            budget_exhausted=budget_exhausted,
        )
