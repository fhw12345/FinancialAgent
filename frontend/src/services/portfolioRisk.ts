/** Runtime-validated non-actionable risk snapshots; no formula or execution API. */
import { z } from "zod";
import { apiClient } from "./api";
const number = z.number().finite();
const nullable = number.nullable();
export const policySchema = z.object({
  max_position_weight: number,
  max_sector_weight: number,
  min_cash_weight: number,
  max_turnover: number,
  risk_per_trade_weight: number,
  lot_size: number,
  fee_bps: number,
  slippage_bps: number,
});
export const policyStateSchema = z.object({
  revision: z.number().int(),
  policy: policySchema.nullable(),
  confirmed_at: z.string().nullable(),
});
export type RiskPolicy = z.infer<typeof policySchema>;
export type PolicyState = z.infer<typeof policyStateSchema>;
const metrics = z.object({
  status: z.enum(["complete", "unavailable"]),
  equity: nullable,
  cash_weight: nullable,
  account_sigma_annualized: nullable,
  invested_sigma_annualized: nullable,
  invested_hhi: nullable,
  beta_exposure: nullable,
  position_weights: z.record(number),
  sector_weights: z.record(number),
  common_sessions: z.array(z.string()),
  history_equity_coverage: nullable,
  exclusions: z.record(z.array(z.string())),
  errors: z.array(z.string()),
  assumptions: z.array(z.string()),
});
export const riskSchema = z.object({
  snapshot: z.object({
    snapshot_id: z.string(),
    calculator_version: z.literal("idq-002@1"),
    account_scope: z.literal("local_holdings"),
    account_revision: z.string(),
    session_date: z.string(),
    captured_at: z.string(),
    cash: nullable,
    policy: policyStateSchema,
  }),
  current: metrics,
  allocation: z
    .object({
      actionable: z.literal(false),
      status: z.enum(["feasible_preview", "blocked"]),
      constraints: z.array(z.string()),
      proposed: metrics.nullable(),
      turnover: nullable,
      posttrade_cash: nullable,
      cash_without_unfilled_sales: nullable,
      changes: z.array(
        z.object({
          symbol: z.string(),
          requested_target_weight: number,
          current_quantity: number,
          proposed_quantity: number,
          delta_quantity: number,
          mark: number,
          estimated_cost_buffer: number,
          stop_risk_quantity_cap: nullable,
        }),
      ),
    })
    .nullable(),
  stale: z.boolean(),
  stale_reasons: z.array(z.string()),
});
export type RiskReview = z.infer<typeof riskSchema>;
const headers = { "X-Financial-Agent-Local": "1" };
export async function getRisk(
  signal?: AbortSignal,
): Promise<RiskReview | null> {
  return riskSchema
    .nullable()
    .parse(
      (await apiClient.get<unknown>("/api/portfolio/risk", { signal })).data,
    );
}
export async function refreshRisk(): Promise<RiskReview> {
  return riskSchema.parse(
    (
      await apiClient.post<unknown>(
        "/api/portfolio/risk/refresh",
        {},
        { headers },
      )
    ).data,
  );
}
export async function getRiskPolicy(
  signal?: AbortSignal,
): Promise<PolicyState> {
  return policyStateSchema.parse(
    (await apiClient.get<unknown>("/api/portfolio/risk-policy", { signal }))
      .data,
  );
}
export async function confirmRiskPolicy(
  policy: RiskPolicy,
  expected_revision: number,
): Promise<PolicyState> {
  return policyStateSchema.parse(
    (
      await apiClient.put<unknown>(
        "/api/portfolio/risk-policy",
        { policy, expected_revision, confirm: true },
        { headers },
      )
    ).data,
  );
}
