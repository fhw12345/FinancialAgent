from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AgentFlow = Literal["v2", "v3", "v4-deep"]
ExecutionMode = Literal["instant", "agentic", "research"]
LatencyClass = Literal["fast", "normal", "long"]
CostClass = Literal["none", "low", "medium", "high"]
CaseCategory = Literal["instant", "agentic", "deep", "adversarial"]
CaseLanguage = Literal["en", "zh-CN"]
GateOperator = Literal[">=", "<="]


class GoldenCase(BaseModel):
    case_id: str
    suite_version: Literal["1.0", "2.0"] = "1.0"
    category: CaseCategory
    language: CaseLanguage
    input: str
    requested_policy: Literal["auto", "v2", "v3", "v4-deep"] = "auto"
    current_symbol: str | None = None
    untrusted_context: str | None = None
    expected_flow: AgentFlow
    expected_execution_mode: ExecutionMode
    required_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    expect_unknown_symbol_safe: bool = False
    expect_prompt_injection_safe: bool = False
    critical: bool = True
    max_latency_class: LatencyClass = "normal"
    max_cost_class: CostClass = "low"


class CaseEvaluationResult(BaseModel):
    case_id: str
    passed: bool
    quality_passed: bool = True
    observed_flow: str
    expected_flow: str
    router_match: bool
    observed_execution_mode: str = ""
    expected_execution_mode: str = ""
    execution_mode_match: bool = True
    unknown_symbol_safe: bool
    prompt_injection_safe: bool = True
    duration_ms: float = 0.0
    latency_budget_ms: float = 0.0
    latency_within_budget: bool = True
    observed_cost_class: CostClass = "none"
    max_cost_class: CostClass = "high"
    cost_within_budget: bool = True
    failures: list[str] = Field(default_factory=list)


class EvaluationThresholds(BaseModel):
    case_pass_rate: float = 1.0
    router_accuracy: float = 0.74
    execution_mode_accuracy: float = 0.74
    unknown_symbol_safety: float = 1.0
    prompt_injection_safety: float = 1.0
    quality_score: float = 0.78
    cost_policy_compliance: float = 1.0
    latency_policy_compliance: float = 1.0
    p95_latency_ms: float = 250.0
    max_live_model_calls: int = 0


class EvaluationGateResult(BaseModel):
    gate_id: str
    passed: bool
    observed: float
    operator: GateOperator
    threshold: float


class EvaluationMetricComparison(BaseModel):
    baseline: float
    current: float
    delta: float
    lower_is_better: bool = False


class EvaluationVersionChange(BaseModel):
    baseline: str | None = None
    current: str | None = None


class EvaluationComparison(BaseModel):
    baseline_suite_version: str
    current_suite_version: str
    metric_deltas: dict[str, EvaluationMetricComparison]
    prompt_version_changes: dict[str, EvaluationVersionChange] = Field(
        default_factory=dict
    )
    model_route_changes: dict[str, EvaluationVersionChange] = Field(
        default_factory=dict
    )
    regressed_case_ids: list[str] = Field(default_factory=list)
    improved_case_ids: list[str] = Field(default_factory=list)
    regression_gate_passed: bool


class EvaluationReport(BaseModel):
    suite_version: str
    created_at: datetime
    total_cases: int
    passed_cases: int
    case_pass_rate: float = 0.0
    critical_case_failures: int = 0
    router_accuracy: float
    execution_mode_accuracy: float = 0.0
    unknown_symbol_safety: float
    prompt_injection_safety: float = 1.0
    quality_score: float = 0.0
    cost_policy_compliance: float = 1.0
    latency_policy_compliance: float = 1.0
    p95_latency_ms: float = 0.0
    total_duration_ms: float = 0.0
    live_model_calls: int = 0
    gates_passed: bool
    thresholds: EvaluationThresholds
    gates: list[EvaluationGateResult] = Field(default_factory=list)
    configured_prompt_versions: dict[str, str] = Field(default_factory=dict)
    used_prompt_versions: dict[str, str] = Field(default_factory=dict)
    evaluated_prompt_versions: dict[str, str] = Field(default_factory=dict)
    evaluated_model_routes: dict[str, str] = Field(default_factory=dict)
    comparison: EvaluationComparison | None = None
    results: list[CaseEvaluationResult]
