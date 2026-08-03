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
  router_accuracy: number;
  execution_mode_accuracy: number;
  unknown_symbol_safety: number;
  prompt_injection_safety: number;
  quality_score: number;
  cost_policy_compliance: number;
  p95_latency_ms: number;
  total_duration_ms: number;
  live_model_calls: number;
  gates_passed: boolean;
  gates: EvaluationGate[];
  evaluated_prompt_versions: Record<string, string>;
  evaluated_model_routes: Record<string, string>;
  results: EvaluationCaseResult[];
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
