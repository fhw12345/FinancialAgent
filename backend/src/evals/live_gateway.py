from __future__ import annotations

import json
import time
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from src.agent.flow_router import RouteClassification
from src.agent.llm_client import get_financial_agent_system_prompt
from src.agent.llm_factory import get_llm, resolve_route
from src.agent.prompt_registry import get_prompt, render_prompt
from src.agent.symbol_resolver import SymbolResolver
from src.core.config import Settings
from src.core.utils import extract_token_usage_from_messages, message_content_to_text

from .live_schemas import (
    LiveEvaluationCase,
    LiveEvaluationRequest,
    LiveTargetResult,
    ModelUsage,
    QualityJudgment,
    ToolEvidence,
)
from .model_budget import (
    EvaluationBudgetExceeded,
    EvaluationModelBudgetCallback,
)
from .pricing import build_model_usage
from .replay_tools import ReplaySymbolSearch, create_replay_tools
from .rubric import compose_evaluation_input
from .tool_evidence import (
    EvaluationToolTraceCallback,
    collect_tool_evidence,
    invoke_tool_with_evidence,
)


class EvaluationGatewayCallError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        usages: list[ModelUsage],
        prompt_versions: dict[str, str],
    ) -> None:
        super().__init__(message)
        self.usages = usages
        self.prompt_versions = prompt_versions


class EvaluationGateway(Protocol):
    def model_name(self, role: str) -> str: ...

    def model_route(self, role: str) -> str: ...

    async def classify(
        self,
        case: LiveEvaluationCase,
    ) -> tuple[str, ModelUsage, dict[str, str]]: ...

    async def generate(
        self,
        case: LiveEvaluationCase,
        observed_flow: str,
        *,
        max_cost_usd: float,
    ) -> LiveTargetResult: ...

    async def judge(
        self,
        case: LiveEvaluationCase,
        target: LiveTargetResult,
    ) -> tuple[QualityJudgment, ModelUsage, dict[str, str]]: ...


def _provider_reported_cost(message: Any) -> float | None:
    metadata = getattr(message, "response_metadata", None) or {}
    for key in ("cost_usd", "estimated_cost_usd", "billed_cost_usd"):
        value = metadata.get(key)
        if isinstance(value, (int, float)) and value >= 0:
            return float(value)
    return None


def _single_message_usage(
    *,
    role: str,
    message: Any,
    duration_ms: float,
    request: LiveEvaluationRequest,
) -> ModelUsage:
    route = resolve_route(role)
    input_tokens, output_tokens, _ = extract_token_usage_from_messages([message])
    return build_model_usage(
        role=role,
        provider=route.provider,
        model=route.model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=duration_ms,
        overrides=request.pricing_overrides,
        provider_reported_cost_usd=_provider_reported_cost(message),
    )


class LiveModelGateway:
    def __init__(self, request: LiveEvaluationRequest) -> None:
        self.request = request
        self.replay_tools = create_replay_tools()
        self.symbol_resolver = SymbolResolver(
            ReplaySymbolSearch(),
            settings=Settings(symbol_resolution_llm_enabled=False),
        )

    def model_name(self, role: str) -> str:
        return resolve_route(role).model

    def model_route(self, role: str) -> str:
        route = resolve_route(role)
        return f"{route.provider}:{route.model}"

    async def classify(
        self,
        case: LiveEvaluationCase,
    ) -> tuple[str, ModelUsage, dict[str, str]]:
        prompt_text = render_prompt(
            "router",
            current_symbol=case.current_symbol or "none",
            message=case.input[:2000],
        )
        started = time.perf_counter()
        structured = get_llm(
            "router",
            temperature=0,
            max_tokens=80,
            timeout=self.request.target_timeout_seconds,
        ).with_structured_output(RouteClassification, include_raw=True)
        response = await structured.ainvoke([HumanMessage(content=prompt_text)])
        duration_ms = (time.perf_counter() - started) * 1000
        if not isinstance(response, dict):
            raise TypeError("Router structured response must be a mapping")
        raw = response["raw"]
        usage = _single_message_usage(
            role="router",
            message=raw,
            duration_ms=duration_ms,
            request=self.request,
        )
        prompt_spec = get_prompt("router")
        prompt_versions = {prompt_spec.prompt_id: prompt_spec.versioned_id}
        try:
            parsed = response.get("parsed")
            if not isinstance(parsed, RouteClassification):
                parsed = RouteClassification.model_validate(parsed)
        except Exception as exc:
            raise EvaluationGatewayCallError(
                f"Invalid router structured output: {exc}",
                usages=[usage],
                prompt_versions=prompt_versions,
            ) from exc
        return (
            parsed.flow,
            usage,
            prompt_versions,
        )

    async def generate(
        self,
        case: LiveEvaluationCase,
        observed_flow: str,
        *,
        max_cost_usd: float,
    ) -> LiveTargetResult:
        if case.requires_clarification and case.current_symbol is None:
            resolution = await self.symbol_resolver.resolve(
                message=compose_evaluation_input(case),
                current_symbol=None,
            )
            if resolution.symbol is not None:
                return LiveTargetResult(
                    observed_flow=observed_flow,
                    final_answer="",
                    error=(
                        "clarification_safety_violation: external evidence "
                        f"selected {resolution.symbol}"
                    ),
                )
            return LiveTargetResult(
                observed_flow=observed_flow,
                final_answer=(
                    "Please clarify which company or provide a validated ticker "
                    "before I run financial research."
                ),
            )

        if observed_flow == "v2":
            return await self._generate_simple(case, observed_flow)
        if observed_flow == "v3":
            return await self._generate_react(
                case,
                observed_flow,
                max_cost_usd=max_cost_usd,
            )
        return LiveTargetResult(
            observed_flow=observed_flow,
            final_answer="Deep Research replay is not enabled in live suite 1.0.",
            error="unsupported_live_flow",
        )

    async def _generate_simple(
        self,
        case: LiveEvaluationCase,
        observed_flow: str,
    ) -> LiveTargetResult:
        prompt = get_financial_agent_system_prompt()
        started = time.perf_counter()
        response = await get_llm(
            "simple_chat",
            temperature=0,
            max_tokens=case.max_target_output_tokens,
            timeout=self.request.target_timeout_seconds,
        ).ainvoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=compose_evaluation_input(case)),
            ]
        )
        duration_ms = (time.perf_counter() - started) * 1000
        usage = _single_message_usage(
            role="simple_chat",
            message=response,
            duration_ms=duration_ms,
            request=self.request,
        )
        prompt_spec = get_prompt("financial-system")
        return LiveTargetResult(
            observed_flow=observed_flow,
            final_answer=message_content_to_text(response.content),
            prompt_versions={prompt_spec.prompt_id: prompt_spec.versioned_id},
            model_usages=[usage],
            duration_ms=duration_ms,
        )

    async def _generate_react(
        self,
        case: LiveEvaluationCase,
        observed_flow: str,
        *,
        max_cost_usd: float,
    ) -> LiveTargetResult:
        prompt = get_financial_agent_system_prompt()
        per_call_output_tokens = max(
            64,
            case.max_target_output_tokens // case.max_target_steps,
        )
        llm = get_llm(
            "react_agent",
            temperature=0,
            max_tokens=per_call_output_tokens,
            timeout=self.request.target_timeout_seconds,
        )
        graph = create_react_agent(llm, self.replay_tools, prompt=prompt)
        tool_trace = EvaluationToolTraceCallback()
        route = resolve_route("react_agent")
        model_budget = EvaluationModelBudgetCallback(
            role="react_agent",
            provider=route.provider,
            model=route.model,
            max_cost_usd=max_cost_usd,
            max_output_tokens_per_call=per_call_output_tokens,
            pricing_overrides=self.request.pricing_overrides,
        )
        started = time.perf_counter()
        prompt_spec = get_prompt("financial-system")
        try:
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=compose_evaluation_input(case))]},
                config={
                    "callbacks": [tool_trace, model_budget],
                    "recursion_limit": case.max_target_steps * 2 + 2,
                },
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
        answer = message_content_to_text(messages[-1].content) if messages else ""
        input_tokens, output_tokens, _ = extract_token_usage_from_messages(messages)
        usage = build_model_usage(
            role="react_agent",
            provider=route.provider,
            model=route.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
            overrides=self.request.pricing_overrides,
        )
        return LiveTargetResult(
            observed_flow=observed_flow,
            final_answer=answer,
            tools=collect_tool_evidence(messages, tool_trace.completed),
            prompt_versions={prompt_spec.prompt_id: prompt_spec.versioned_id},
            model_usages=[usage],
            duration_ms=duration_ms,
        )

    async def judge(
        self,
        case: LiveEvaluationCase,
        target: LiveTargetResult,
    ) -> tuple[QualityJudgment, ModelUsage, dict[str, str]]:
        prompt_spec = get_prompt("eval-judge")
        prompt = render_prompt(
            "eval-judge",
            case_contract=json.dumps(case.model_dump(), ensure_ascii=False, indent=2),
            tool_evidence=json.dumps(
                [tool.model_dump() for tool in target.tools],
                ensure_ascii=False,
                indent=2,
            ),
            candidate_answer=json.dumps(target.final_answer, ensure_ascii=False),
        )
        started = time.perf_counter()
        structured = get_llm(
            "eval_judge",
            temperature=0,
            max_tokens=case.max_judge_output_tokens,
            timeout=self.request.judge_timeout_seconds,
        ).with_structured_output(QualityJudgment, include_raw=True)
        response = await structured.ainvoke([HumanMessage(content=prompt)])
        duration_ms = (time.perf_counter() - started) * 1000
        if not isinstance(response, dict):
            raise TypeError("Judge structured response must be a mapping")
        usage = _single_message_usage(
            role="eval_judge",
            message=response["raw"],
            duration_ms=duration_ms,
            request=self.request,
        )
        prompt_versions = {prompt_spec.prompt_id: prompt_spec.versioned_id}
        try:
            parsed = response.get("parsed")
            if not isinstance(parsed, QualityJudgment):
                parsed = QualityJudgment.model_validate(parsed)
        except Exception as exc:
            raise EvaluationGatewayCallError(
                f"Invalid Judge structured output: {exc}",
                usages=[usage],
                prompt_versions=prompt_versions,
            ) from exc
        return parsed, usage, prompt_versions


class FakeLiveModelGateway:
    def __init__(self, request: LiveEvaluationRequest) -> None:
        self.request = request
        self.tools = {tool.name: tool for tool in create_replay_tools()}
        self.symbol_resolver = SymbolResolver(
            ReplaySymbolSearch(),
            settings=Settings(symbol_resolution_llm_enabled=False),
        )

    def model_name(self, role: str) -> str:
        return "e2e-model"

    def model_route(self, role: str) -> str:
        return f"fake:{role}:e2e-model"

    def _usage(self, role: str, input_tokens: int, output_tokens: int) -> ModelUsage:
        return build_model_usage(
            role=role,
            provider="anthropic",
            model="e2e-model",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=5,
            overrides=self.request.pricing_overrides,
        )

    async def classify(
        self,
        case: LiveEvaluationCase,
    ) -> tuple[str, ModelUsage, dict[str, str]]:
        prompt = get_prompt("router")
        return (
            case.expected_flow,
            self._usage("router", 20, 5),
            {prompt.prompt_id: prompt.versioned_id},
        )

    async def generate(
        self,
        case: LiveEvaluationCase,
        observed_flow: str,
        *,
        max_cost_usd: float,
    ) -> LiveTargetResult:
        del max_cost_usd
        if case.requires_clarification:
            resolution = await self.symbol_resolver.resolve(
                message=compose_evaluation_input(case),
                current_symbol=case.current_symbol,
            )
            if resolution.symbol is not None:
                return LiveTargetResult(
                    observed_flow=observed_flow,
                    final_answer="",
                    error=(
                        "clarification_safety_violation: external evidence "
                        f"selected {resolution.symbol}"
                    ),
                )
            answer = "Please clarify which company or provide a ticker."
            evidence: list[ToolEvidence] = []
        elif not case.required_tools:
            answer = (
                "Diversification spreads exposure across assets and reduces the "
                "impact of a single investment loss."
                if case.language == "en"
                else "自由现金流是企业经营现金流扣除资本支出后的剩余现金。"
            )
            evidence = []
        else:
            evidence = []
            for tool_name in case.required_tools:
                tool = self.tools[tool_name]
                args: dict[str, object] = {"symbol": case.current_symbol or "AAPL"}
                evidence.append(await invoke_tool_with_evidence(tool, args))
            answer = " ".join(tool.output for tool in evidence)
        prompt_versions = {}
        model_usages = []
        if not case.requires_clarification:
            prompt = get_prompt("financial-system")
            prompt_versions[prompt.prompt_id] = prompt.versioned_id
            target_role = "simple_chat" if observed_flow == "v2" else "react_agent"
            model_usages.append(self._usage(target_role, 80, 40))
        return LiveTargetResult(
            observed_flow=observed_flow,
            final_answer=answer,
            tools=evidence,
            prompt_versions=prompt_versions,
            model_usages=model_usages,
            duration_ms=5,
        )

    async def judge(
        self,
        case: LiveEvaluationCase,
        target: LiveTargetResult,
    ) -> tuple[QualityJudgment, ModelUsage, dict[str, str]]:
        prompt = get_prompt("eval-judge")
        judgment = QualityJudgment(
            factual_grounding=1,
            required_fact_coverage=1,
            source_consistency=1,
            relevance=1,
            completeness=1,
            uncertainty_disclosure=1,
            contradiction_handling=1,
            financial_risk_language=1,
            unsupported_certainty=1,
            overall_score=1,
        )
        return (
            judgment,
            self._usage("eval_judge", 100, 30),
            {prompt.prompt_id: prompt.versioned_id},
        )
