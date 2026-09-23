/** Model recommendations: explicit actions/targets, never readiness, quantities or orders. */
import { z } from "zod";
const symbol = z.string().regex(/^[A-Z0-9][A-Z0-9.-]{0,14}$/);
export const modelDecisionSchema = z.object({
  symbol,
  action: z.enum(["BUY", "ADD", "REDUCE", "SELL", "HOLD"]),
  target_weight: z.number().finite().min(0).max(1).nullable(),
  rationale: z.string(),
  evidence_ids: z.array(z.string()),
  key_risks: z.array(z.string()),
  review_triggers: z.array(z.string()),
});
export type ModelDecision = z.infer<typeof modelDecisionSchema>;
export const modelDecisionRecordSchema = z.object({
  schema_version: z.literal(1),
  decision_id: z.string(),
  request_id: z.string(),
  assessment_id: z.string(),
  policy_version_id: z.string(),
  scope: z.array(symbol),
  status: z.enum(["running", "completed", "failed"]),
  created_at: z.string(),
  completed_at: z.string().nullable(),
  provenance: z
    .object({
      prompt: z.literal("portfolio-model-decision@1"),
      role: z.literal("portfolio_decisions"),
      provider: z.string(),
      model: z.string(),
      api: z.string().nullable(),
      routing_revision: z.number().int().nullable(),
    })
    .nullable(),
  output: z
    .object({
      decisions: z.array(modelDecisionSchema),
      portfolio_summary: z.string(),
    })
    .nullable(),
  error_code: z.string().nullable(),
  executable: z.literal(false),
});
export type ModelDecisionRecord = z.infer<typeof modelDecisionRecordSchema>;
