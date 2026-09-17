import { z } from "zod";
import { apiClient } from "./api";
import { riskSchema } from "./portfolioRisk";
import { evidenceSummarySchema } from "./evidence";

const readiness = z.enum([
  "research_only",
  "insufficient_evidence",
  "needs_review",
  "blocked",
]);
const draft = z.object({
  symbol: z.string(),
  proposed_action: z.enum(["BUY", "SELL", "HOLD"]),
  intent: z.enum(["open_long", "close_long", "hold"]),
  reasoning: z.string(),
  size_percent: z.number().finite().nullable(),
  entry: z.number().finite().nullable(),
  stop: z.number().finite().nullable(),
  target: z.number().finite().nullable(),
});
export const assessmentSchema = z.object({
  schema_version: z.literal(1),
  policy_version: z.literal("idq-001-a@1"),
  assessment_id: z.string(),
  run_id: z.string().nullable(),
  source: z.string(),
  created_at: z.string(),
  readiness,
  actionable: z.literal(false),
  action: z.null(),
  run_status: z.string().nullable(),
  portfolio_risk: riskSchema.nullable().optional(),
  evidence: evidenceSummarySchema.nullable().optional(),
  results: z.array(
    z.object({
      symbol: z.string(),
      readiness,
      actionable: z.literal(false),
      action: z.null(),
      proposal: draft.nullable(),
      research: z.string(),
      research_truncated: z.boolean(),
      exposure_context: z.enum(["held", "flat", "unknown"]),
      reasons: z.array(z.object({ code: z.string(), message: z.string() })),
    }),
  ),
});
export type DecisionAssessment = z.infer<typeof assessmentSchema>;

export async function listAssessments(
  symbol?: string,
  source?: string,
  signal?: AbortSignal,
): Promise<DecisionAssessment[]> {
  const response = await apiClient.get<unknown>("/api/portfolio/assessments", {
    params: { symbol, source, limit: 20 },
    signal,
  });
  return z.array(assessmentSchema).parse(response.data);
}

export async function getAssessment(
  id: string,
  signal?: AbortSignal,
): Promise<DecisionAssessment> {
  const response = await apiClient.get<unknown>(
    `/api/portfolio/assessments/${encodeURIComponent(id)}`,
    { signal },
  );
  return assessmentSchema.parse(response.data);
}
