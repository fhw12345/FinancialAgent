from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GoldenCase(BaseModel):
    case_id: str
    suite_version: Literal["1.0"] = "1.0"
    category: Literal["instant", "agentic", "deep", "adversarial"]
    language: Literal["en", "zh-CN"]
    input: str
    requested_policy: Literal["auto", "v2", "v3", "v4-deep"] = "auto"
    current_symbol: str | None = None
    expected_flow: Literal["v2", "v3", "v4-deep"]
    expected_execution_mode: Literal["instant", "agentic", "research"]
    required_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    expect_unknown_symbol_safe: bool = False
    max_latency_class: Literal["fast", "normal", "long"] = "normal"
    max_cost_class: Literal["none", "low", "medium", "high"] = "low"


class CaseEvaluationResult(BaseModel):
    case_id: str
    passed: bool
    observed_flow: str
    expected_flow: str
    router_match: bool
    unknown_symbol_safe: bool
    failures: list[str] = Field(default_factory=list)


class EvaluationThresholds(BaseModel):
    router_accuracy: float = 0.74
    unknown_symbol_safety: float = 1.0


class EvaluationReport(BaseModel):
    suite_version: str
    created_at: datetime
    total_cases: int
    passed_cases: int
    router_accuracy: float
    unknown_symbol_safety: float
    gates_passed: bool
    thresholds: EvaluationThresholds
    evaluated_prompt_versions: dict[str, str]
    results: list[CaseEvaluationResult]
