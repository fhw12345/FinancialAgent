from __future__ import annotations

from .live_gateway import EvaluationGateway
from .live_schemas import (
    LiveEvaluationCase,
    LiveEvaluationRequest,
    ModelUsage,
    QualityJudgment,
)
from .pricing import estimate_max_call_cost

ROUTER_MAX_INPUT_TOKENS = 2500
ROUTER_MAX_OUTPUT_TOKENS = 80
JUDGE_SCORE_FIELDS = (
    "factual_grounding",
    "required_fact_coverage",
    "source_consistency",
    "relevance",
    "completeness",
    "uncertainty_disclosure",
    "contradiction_handling",
    "financial_risk_language",
    "unsupported_certainty",
)


def call_reservation(
    gateway: EvaluationGateway,
    request: LiveEvaluationRequest,
    *,
    role: str,
    max_input_tokens: int,
    max_output_tokens: int,
) -> float:
    return estimate_max_call_cost(
        model=gateway.model_name(role),
        max_input_tokens=max_input_tokens,
        max_output_tokens=max_output_tokens,
        overrides=request.pricing_overrides,
    )


def case_reservation(
    gateway: EvaluationGateway,
    request: LiveEvaluationRequest,
    case: LiveEvaluationCase,
) -> float:
    total = call_reservation(
        gateway,
        request,
        role="router",
        max_input_tokens=ROUTER_MAX_INPUT_TOKENS,
        max_output_tokens=ROUTER_MAX_OUTPUT_TOKENS,
    )
    if not case.requires_clarification:
        target_role = "simple_chat" if case.expected_flow == "v2" else "react_agent"
        total += call_reservation(
            gateway,
            request,
            role=target_role,
            max_input_tokens=case.max_target_input_tokens,
            max_output_tokens=case.max_target_output_tokens,
        )
    total += call_reservation(
        gateway,
        request,
        role="eval_judge",
        max_input_tokens=case.max_judge_input_tokens,
        max_output_tokens=case.max_judge_output_tokens,
    )
    return total


def usage_totals(usages: list[ModelUsage]) -> tuple[int, int]:
    return (
        sum(usage.input_tokens for usage in usages),
        sum(usage.output_tokens for usage in usages),
    )


def judge_failures(
    judgment: QualityJudgment,
    *,
    answer: str,
    minimum_score: float,
) -> list[str]:
    failures = [
        f"Judge {failure.criterion}: {failure.reason} " f"(quote: {failure.quote!r})"
        for failure in judgment.failures
    ]
    recorded = {failure.criterion for failure in judgment.failures}
    for field in JUDGE_SCORE_FIELDS:
        score = float(getattr(judgment, field))
        if score < minimum_score and field not in recorded:
            failures.append(
                f"Judge criterion {field} scored {score:.3f} without evidence"
            )
    for failure in judgment.failures:
        quote = failure.quote.strip()
        if not quote or quote not in answer:
            failures.append(
                f"Judge evidence for {failure.criterion} is not an exact answer quote"
            )
    return failures
