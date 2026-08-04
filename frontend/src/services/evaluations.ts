import { apiClient } from "./api";

export interface EvaluationGate {
  gate_id: string;
  passed: boolean;
  observed: number;
  operator: ">=" | "<=";
  threshold: number;
}

export interface EvaluationCaseResult {
  case_id: string;
  passed: boolean;
  observed_flow: string;
  expected_flow: string;
  duration_ms: number;
  failures: string[];
}

export interface EvaluationReport {
  suite_version: string;
  created_at: string;
  total_cases: number;
  passed_cases: number;
  case_pass_rate: number;
  critical_case_failures: number;
  router_accuracy: number;
  execution_mode_accuracy: number;
  unknown_symbol_safety: number;
  prompt_injection_safety: number;
  quality_score: number;
  cost_policy_compliance: number;
  latency_policy_compliance: number;
  p95_latency_ms: number;
  total_duration_ms: number;
  live_model_calls: number;
  gates_passed: boolean;
  gates: EvaluationGate[];
  configured_prompt_versions: Record<string, string>;
  used_prompt_versions: Record<string, string>;
  evaluated_model_routes: Record<string, string>;
  results: EvaluationCaseResult[];
}

export type LiveEvaluationLane =
  | "replay_live"
  | "provider_smoke"
  | "fake_live";

export interface LiveEvaluationRequest {
  lane: LiveEvaluationLane;
  enabled: boolean;
  max_cost_usd: number;
  case_limit: number;
}

export interface EvaluationRunSummary {
  run_id: string;
  suite_version: string;
  lane: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  gates_passed: boolean;
  case_pass_rate: number;
  estimated_cost_usd: number;
}

export interface LiveEvaluationCapabilities {
  fake_live_available: boolean;
  provider_smoke_available: boolean;
}

export interface ToolEvidence {
  tool_name: string;
  arguments: Record<string, unknown>;
  output: string;
  source_id: string | null;
  provider: string | null;
  duration_ms: number;
  success: boolean;
}

export interface ModelUsage {
  role: string;
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  cost_source: string;
  duration_ms: number;
}

export interface RubricCriterion {
  criterion: string;
  passed: boolean;
  score: number;
  evidence: string;
}

export interface LiveCaseResult {
  case_id: string;
  status: string;
  passed: boolean;
  critical: boolean;
  observed_flow: string | null;
  expected_flow: string;
  final_answer: string;
  tools: ToolEvidence[];
  deterministic_rubric: {
    score: number;
    criteria: RubricCriterion[];
    required_tool_recall: number;
    tool_precision: number;
    required_fact_coverage: number;
    unsupported_claim_rate: number;
  } | null;
  judge: {
    overall_score: number;
    failures: Array<{ criterion: string; quote: string; reason: string }>;
  } | null;
  model_usages: ModelUsage[];
  prompt_versions: Record<string, string>;
  duration_ms: number;
  cost_usd: number;
  failures: string[];
}

export interface LiveEvaluationReport {
  run_id: string;
  suite_version: string;
  lane: LiveEvaluationLane;
  status: "running" | "completed" | "failed" | "budget_exhausted";
  created_at: string;
  completed_at: string | null;
  max_cost_usd: number;
  metrics: {
    case_pass_rate: number;
    critical_case_failures: number;
    tool_recall: number;
    tool_precision: number;
    deterministic_quality: number;
    judge_quality: number;
    required_fact_coverage: number;
    unsupported_claim_rate: number;
    p95_latency_ms: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost_usd: number;
  };
  gates_passed: boolean;
  budget_exhausted: boolean;
  pricing_catalog_version: string;
  configured_prompt_versions: Record<string, string>;
  used_prompt_versions: Record<string, string>;
  model_routes: Record<string, string>;
  results: LiveCaseResult[];
  error: string | null;
}

export async function runEvaluation(
  suite = "2.0",
): Promise<EvaluationReport> {
  const { data } = await apiClient.post<EvaluationReport>(
    "/api/admin/evaluations/run",
    undefined,
    { params: { suite } },
  );
  return data;
}

export async function startLiveEvaluation(
  request: LiveEvaluationRequest,
): Promise<EvaluationRunSummary> {
  const { data } = await apiClient.post<EvaluationRunSummary>(
    "/api/admin/evaluations/live/runs",
    request,
  );
  return data;
}

export async function getLiveEvaluationCapabilities(): Promise<LiveEvaluationCapabilities> {
  const { data } = await apiClient.get<LiveEvaluationCapabilities>(
    "/api/admin/evaluations/live/capabilities",
  );
  return data;
}

export async function getLiveEvaluation(
  runId: string,
  signal?: AbortSignal,
): Promise<LiveEvaluationReport> {
  const { data } = await apiClient.get<LiveEvaluationReport>(
    `/api/admin/evaluations/live/runs/${runId}`,
    { signal },
  );
  return data;
}

export async function listLiveEvaluations(
  limit = 10,
): Promise<EvaluationRunSummary[]> {
  const { data } = await apiClient.get<EvaluationRunSummary[]>(
    "/api/admin/evaluations/live/runs",
    { params: { limit } },
  );
  return data;
}
