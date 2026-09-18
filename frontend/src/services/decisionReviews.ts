/** Human paper-review receipts are distinct from research, trades and future paper fills. */
import { z } from "zod";
import { isAxiosError } from "axios";
import { apiClient } from "./api";
import { riskSchema } from "./portfolioRisk";
const n = z.number().finite();
const revision = z.number().int().nonnegative();
const symbol = z.string().regex(/^[A-Z0-9][A-Z0-9.-]{0,14}$/);
export const reviewTargetSchema = z
  .object({ symbol, target_weight: n.min(0).max(1) })
  .strict();
export type ReviewTarget = z.infer<typeof reviewTargetSchema>;
export const reviewPolicyInputSchema = z
  .object({
    risk_policy_revision: revision.min(1),
    strategy_version: z.string(),
    allowed_symbols: z.array(symbol).min(1).max(100),
    max_account_sigma: n.positive().max(3),
    lifetime_minutes: z.number().int().min(1).max(1440),
    acknowledged_contract: z.literal("manual-target-paper-review@1"),
    instrument_attestation: z.literal("USD-US-nonfinancial-common-equities"),
    evidence_acknowledgment: z.literal(
      "forward-close-not-truth-or-historical-PIT",
    ),
  })
  .strict();
export type ReviewPolicyInput = z.infer<typeof reviewPolicyInputSchema>;
const policySchema = z.object({
  version_id: z.string(),
  policy: reviewPolicyInputSchema,
  confirmed_at: z.string(),
  revision,
});
const settingsSchema = z.object({
  revision,
  generation: revision,
  policy: policySchema.nullable(),
  versions: z.array(policySchema),
  account_revision: z.string(),
  risk_policy_revision: revision,
  strategy_version: z.string().nullable(),
  uncertain: z.boolean(),
  in_flight: revision,
  current_batch_id: z.string().nullable(),
  reasons: z.array(z.string()),
  approval_available: z.literal(true),
  execution_available: z.literal(false),
});
export type ReviewSettings = z.infer<typeof settingsSchema>;
const readiness = z.enum([
  "ready",
  "research_only",
  "needs_review",
  "insufficient_evidence",
  "blocked",
]);
const reasonSchema = z.object({
  code: z.string(),
  severity: readiness,
  symbol: symbol.nullable(),
});
const requestSchema = z.object({
  expected_revision: revision,
  expected_generation: revision,
  request_id: z.string(),
});
const proposalRequest = requestSchema.extend({
  assessment_id: z.string(),
  targets: z.array(reviewTargetSchema).min(1).max(20),
});
const approveRequest = requestSchema.extend({
  symbols: z.array(symbol).min(1).max(20),
  confirm: z.literal(true),
  acknowledgment: z.literal("review-only-no-real-or-paper-fill"),
});
export const preparedReviewSchema = z.object({
  schema_version: z.literal(1),
  gate_version: z.literal("idq-001-b@1"),
  batch_id: z.string(),
  request: proposalRequest,
  request_hash: z.string(),
  receipt_hash: z.string(),
  source_hash: z.string().nullable(),
  run_id: z.string().nullable(),
  created_at: z.string(),
  expires_at: z.string(),
  policy: policySchema.nullable(),
  risk: riskSchema.nullable(),
  reasons: z.array(reasonSchema),
  trades: z.array(
    z.object({
      symbol,
      action: z.enum(["BUY", "SELL", "HOLD"]),
      intent: z.enum([
        "open_long",
        "add_long",
        "reduce_long",
        "close_long",
        "hold",
      ]),
      exposure: z.enum(["held", "flat"]),
      delta_quantity: n,
      reference_price: n,
      execution_price: z.null(),
    }),
  ),
  proofs: z.array(
    z.object({
      symbol,
      snapshot_id: z.string(),
      manifest_hash: z.string(),
      dossier_id: z.string(),
      strategy_review_id: z.string(),
      monitoring: z.record(z.string()),
      unverified_context: z.array(z.string()),
    }),
  ),
  executable: z.literal(false),
});
export const reviewViewSchema = z.object({
  batch: preparedReviewSchema,
  readiness,
  reasons: z.array(reasonSchema),
  lifecycle: z.enum([
    "unpublished",
    "current",
    "superseded",
    "cancelled",
    "approved",
  ]),
  approvable: z.boolean(),
  approval: z
    .object({
      approval_id: z.string(),
      batch_id: z.string(),
      request: approveRequest,
      approved_at: z.string(),
      world_revision: revision,
      generation: revision,
      executable: z.literal(false),
    })
    .nullable(),
  approval_receipt: z
    .object({
      approval_id: z.string(),
      batch_id: z.string(),
      receipt_hash: z.string(),
      evaluation: preparedReviewSchema,
    })
    .nullable(),
  approval_current: z.boolean(),
  control_revision: revision,
  control_generation: revision,
  executable: z.literal(false),
});
export type ReviewView = z.infer<typeof reviewViewSchema>;
export type ReviewRevision = z.infer<typeof requestSchema>;
const headers = { "X-Financial-Agent-Local": "1" };
const root = "/api/portfolio";
export const revisionFor = (
  state: ReviewSettings,
  request_id: string,
): ReviewRevision => ({
  expected_revision: state.revision,
  expected_generation: state.generation,
  request_id,
});
export async function getReviewSettings(
  signal?: AbortSignal,
): Promise<ReviewSettings> {
  return settingsSchema.parse(
    (await apiClient.get<unknown>(`${root}/review-policy`, { signal })).data,
  );
}
export async function confirmReviewPolicy(
  policy: ReviewPolicyInput,
  version: ReviewRevision,
): Promise<ReviewSettings> {
  return settingsSchema.parse(
    (
      await apiClient.post<unknown>(
        `${root}/review-policy`,
        { ...version, policy, confirm: true },
        { headers },
      )
    ).data,
  );
}
export async function deactivateReviewPolicy(
  version: ReviewRevision,
): Promise<ReviewSettings> {
  return settingsSchema.parse(
    (
      await apiClient.post<unknown>(
        `${root}/review-policy/deactivate`,
        version,
        { headers },
      )
    ).data,
  );
}
export async function reconcileReviewAccount(
  state: ReviewSettings,
  version: ReviewRevision,
): Promise<ReviewSettings> {
  return settingsSchema.parse(
    (
      await apiClient.post<unknown>(
        `${root}/review-control/reconcile`,
        {
          ...version,
          account_revision: state.account_revision,
          acknowledgment: "declared-account-inspected-no-writers-in-flight",
        },
        { headers },
      )
    ).data,
  );
}
export async function getReviewBatches(
  signal?: AbortSignal,
): Promise<ReviewView[]> {
  return z
    .array(reviewViewSchema)
    .parse(
      (await apiClient.get<unknown>(`${root}/review-batches`, { signal })).data,
    );
}
export async function proposeReview(
  body: z.infer<typeof proposalRequest>,
): Promise<ReviewView> {
  return reviewViewSchema.parse(
    (
      await apiClient.post<unknown>(`${root}/review-batches`, body, {
        headers,
        timeout: 120000,
      })
    ).data,
  );
}
export async function approveReview(
  batchId: string,
  body: z.infer<typeof approveRequest>,
): Promise<ReviewView> {
  return reviewViewSchema.parse(
    (
      await apiClient.post<unknown>(
        `${root}/review-batches/${encodeURIComponent(batchId)}/approve`,
        body,
        { headers, timeout: 120000 },
      )
    ).data,
  );
}
export async function cancelReview(
  batchId: string,
  version: ReviewRevision,
): Promise<ReviewView> {
  return reviewViewSchema.parse(
    (
      await apiClient.post<unknown>(
        `${root}/review-batches/${encodeURIComponent(batchId)}/cancel`,
        version,
        { headers },
      )
    ).data,
  );
}
export function reviewError(error: unknown): string {
  const response = z
    .object({ message: z.string().optional(), detail: z.string().optional() })
    .safeParse(isAxiosError<unknown>(error) ? error.response?.data : null);
  return response.success
    ? (response.data.message ?? response.data.detail ?? "Review rejected")
    : "Review unavailable; reload / 审阅失败，请重新读取";
}
