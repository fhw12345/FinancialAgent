from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

LiveEvaluationLane = Literal["replay_live", "provider_smoke", "fake_live"]
LiveEvaluationStatus = Literal[
    "running",
    "completed",
    "failed",
    "budget_exhausted",
]
LiveCaseStatus = Literal["completed", "failed", "skipped", "budget_exhausted"]
CostSource = Literal[
    "catalog_estimate",
    "override_estimate",
    "provider_reported",
]


class ModelPricingOverride(BaseModel):
    input_per_million_usd: float = Field(gt=0)
    output_per_million_usd: float = Field(gt=0)


class LiveEvaluationRequest(BaseModel):
    lane: LiveEvaluationLane = "replay_live"
    enabled: bool = False
    max_cost_usd: float = Field(default=0.25, gt=0, le=25)
    case_limit: int = Field(default=8, ge=1, le=20)
    target_timeout_seconds: float = Field(default=120, ge=5, le=300)
    judge_timeout_seconds: float = Field(default=60, ge=5, le=180)
    pricing_overrides: dict[str, ModelPricingOverride] = Field(default_factory=dict)


class LiveEvaluationCase(BaseModel):
    case_id: str
    language: Literal["en", "zh-CN"]
    input: str
    current_symbol: str | None = None
    untrusted_context: str | None = None
    expected_flow: Literal["v2", "v3", "v4-deep"]
    required_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    required_facts: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    require_source_evidence: bool = False
    requires_clarification: bool = False
    critical: bool = True
    max_target_input_tokens: int = Field(default=5000, ge=100)
    max_target_output_tokens: int = Field(default=800, ge=100, le=4000)
    max_target_steps: int = Field(default=4, ge=1, le=8)
    max_judge_input_tokens: int = Field(default=6000, ge=100)
    max_judge_output_tokens: int = Field(default=700, ge=100, le=2000)
    max_latency_ms: float = Field(default=120_000, gt=0)
    max_cost_usd: float = Field(default=0.15, gt=0)
    minimum_deterministic_score: float = Field(default=0.9, ge=0, le=1)
    minimum_judge_score: float = Field(default=0.8, ge=0, le=1)


class ToolEvidence(BaseModel):
    tool_name: str
    arguments: dict[str, object] = Field(default_factory=dict)
    output: str = ""
    source_id: str | None = None
    provider: str | None = None
    duration_ms: float = Field(default=0.0, ge=0)
    success: bool = True


class ModelUsage(BaseModel):
    role: str
    provider: str
    model: str
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)
    cost_source: CostSource = "catalog_estimate"
    duration_ms: float = Field(default=0.0, ge=0)


class RubricCriterion(BaseModel):
    criterion: str
    passed: bool
    score: float = Field(ge=0, le=1)
    evidence: str


class DeterministicRubricResult(BaseModel):
    score: float = Field(ge=0, le=1)
    criteria: list[RubricCriterion]
    required_tool_recall: float = Field(ge=0, le=1)
    tool_precision: float = Field(ge=0, le=1)
    required_fact_coverage: float = Field(ge=0, le=1)
    unsupported_claim_rate: float = Field(ge=0, le=1)


class JudgeFailure(BaseModel):
    criterion: str
    quote: str
    reason: str


class QualityJudgment(BaseModel):
    factual_grounding: float = Field(ge=0, le=1)
    required_fact_coverage: float = Field(ge=0, le=1)
    source_consistency: float = Field(ge=0, le=1)
    relevance: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    uncertainty_disclosure: float = Field(ge=0, le=1)
    contradiction_handling: float = Field(ge=0, le=1)
    financial_risk_language: float = Field(ge=0, le=1)
    unsupported_certainty: float = Field(ge=0, le=1)
    overall_score: float = Field(ge=0, le=1)
    failures: list[JudgeFailure] = Field(default_factory=list)


class LiveTargetResult(BaseModel):
    observed_flow: str
    final_answer: str
    tools: list[ToolEvidence] = Field(default_factory=list)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    model_usages: list[ModelUsage] = Field(default_factory=list)
    duration_ms: float = 0.0
    error: str | None = None
    budget_exhausted: bool = False


class LiveCaseResult(BaseModel):
    case_id: str
    status: LiveCaseStatus
    passed: bool
    critical: bool
    observed_flow: str | None = None
    expected_flow: str
    final_answer: str = ""
    tools: list[ToolEvidence] = Field(default_factory=list)
    deterministic_rubric: DeterministicRubricResult | None = None
    judge: QualityJudgment | None = None
    model_usages: list[ModelUsage] = Field(default_factory=list)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    duration_ms: float = 0.0
    cost_usd: float = 0.0
    failures: list[str] = Field(default_factory=list)


class LiveEvaluationMetrics(BaseModel):
    case_pass_rate: float = 0.0
    critical_case_failures: int = 0
    tool_recall: float = 0.0
    tool_precision: float = 0.0
    deterministic_quality: float = 0.0
    judge_quality: float = 0.0
    required_fact_coverage: float = 0.0
    unsupported_claim_rate: float = 0.0
    p95_latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class LiveMetricComparison(BaseModel):
    baseline: float
    current: float
    delta: float
    allowed_current: float
    passed: bool
    lower_is_better: bool = False


class LiveEvaluationComparison(BaseModel):
    baseline_run_id: str
    current_run_id: str
    metrics: dict[str, LiveMetricComparison]
    regressed_case_ids: list[str] = Field(default_factory=list)
    improved_case_ids: list[str] = Field(default_factory=list)
    regression_gate_passed: bool


class LiveEvaluationReport(BaseModel):
    run_id: str
    suite_version: str = "live-1.0"
    lane: LiveEvaluationLane
    status: LiveEvaluationStatus
    created_at: datetime
    completed_at: datetime | None = None
    max_cost_usd: float
    metrics: LiveEvaluationMetrics
    gates_passed: bool
    budget_exhausted: bool = False
    pricing_catalog_version: str = "unknown"
    configured_prompt_versions: dict[str, str] = Field(default_factory=dict)
    used_prompt_versions: dict[str, str] = Field(default_factory=dict)
    model_routes: dict[str, str] = Field(default_factory=dict)
    results: list[LiveCaseResult] = Field(default_factory=list)
    comparison: LiveEvaluationComparison | None = None
    error: str | None = None


class EvaluationRunSummary(BaseModel):
    run_id: str
    suite_version: str
    lane: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    gates_passed: bool
    case_pass_rate: float
    estimated_cost_usd: float


class LiveEvaluationCapabilities(BaseModel):
    fake_live_available: bool
    provider_smoke_available: bool
