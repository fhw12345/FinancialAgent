/** Confirmed research contracts, not trading policies or execution permissions. */
import { z } from "zod";
import { apiClient } from "./api";
import { policySchema } from "./portfolioRisk";
const n = z.number().finite();
export const parametersSchema = z.object({
  methods: z.array(z.enum(["peer_pe_annual@1", "fcff_proxy_dcf@1"])),
  peer_symbols: z.array(z.string()),
  peer_rationale: z.string(),
  discount_rate: n,
  growth_rate: n,
  terminal_growth: n,
  tax_rate: n,
  projection_years: z.number().int(),
  valuation_discount: n,
  earnings_decline_fraction: n,
  debt_to_fcf_limit: n,
  max_financial_age_days: z.number().int(),
  max_price_lag_sessions: z.number().int(),
  fcff_proxy_acknowledged: z.literal(true),
});
export type StrategyParameters = z.infer<typeof parametersSchema>;
const versionSchema = z.object({
  strategy_id: z.literal("fundamental-252@1"),
  version_id: z.string(),
  revision: z.number().int(),
  horizon: z.literal(252),
  horizon_unit: z.literal("XNYS_sessions"),
  benchmark: z.literal("SPY_total_return@1"),
  universe: z.literal("US_USD_nonfinancial_common_equity"),
  parameters: parametersSchema,
  cost_policy_revision: z.number().int(),
  cost_policy: policySchema,
  confirmed_at: z.string(),
  request_id: z.string(),
  input_hash: z.string(),
});
const stateSchema = z.object({
  revision: z.number().int(),
  active_version: z.string().nullable(),
  versions: z.array(versionSchema),
});
export type StrategyState = z.infer<typeof stateSchema>;
const inputSchema = z.object({
  snapshot_id: z.string(),
  evidence_id: z.string(),
  symbol: z.string(),
  metric: z.string(),
  value: n,
  unit: z.string(),
  period: z.string(),
  period_end: z.string(),
});
const valuation = z.object({
  method: z.enum(["peer_pe_annual@1", "fcff_proxy_dcf@1"]),
  status: z.enum(["available", "unavailable", "inapplicable"]),
  reasons: z.array(z.string()),
  inputs: z.array(inputSchema),
  assumptions: z.record(z.union([n, z.string()])),
  peer_multiple: n.nullable(),
  enterprise_value: n.nullable(),
  equity_value: n.nullable(),
  per_share_usd: n.nullable(),
  interpretation: z.literal(
    "conditional_model_estimate_not_verified_fair_value",
  ),
});
export const strategySummarySchema = z.object({
  reviews: z.array(
    z.object({
      review_id: z.string(),
      contract: versionSchema,
      symbol: z.string(),
      snapshot_id: z.string(),
      as_of: z.string(),
      purpose: z.literal("research"),
      status: z.enum([
        "research_only",
        "insufficient_evidence",
        "inapplicable",
      ]),
      errors: z.array(z.string()),
      valuations: z.array(valuation),
      monitoring: z.array(z.string()),
      checks: z.array(
        z.object({
          rule: z.string(),
          status: z.enum(["triggered", "not_triggered", "unavailable"]),
          value: n.nullable(),
          threshold: n,
          unit: z.literal("ratio"),
          evidence_ids: z.array(z.string()),
          reason: z.string(),
        }),
      ),
      conclusion: z
        .object({
          kind: z.literal("strategy_research"),
          symbol: z.string(),
          stance: z.enum(["bullish", "neutral", "bearish", "unknown"]),
          theses: z.array(
            z.object({
              text: z.string(),
              evidence_ids: z.array(z.string()),
              monitoring_rule: z.string(),
            }),
          ),
          scenarios: z.array(
            z.object({
              scenario: z.string(),
              condition: z.string(),
              probability: z.null(),
              probability_basis: z.literal("not_estimated"),
            }),
          ),
          report_markdown: z.string(),
          portfolio_action: z.null(),
          execution_intent: z.null(),
          prose_verification: z.literal("unverified"),
        })
        .nullable(),
      stale: z.boolean(),
      actionable: z.literal(false),
      prompt_versions: z.record(z.string()),
    }),
  ),
  errors: z.array(z.string()),
  legacy_strategy: z.literal(false),
  actionable: z.literal(false),
});
export type StrategySummary = z.infer<typeof strategySummarySchema>;
const headers = { "X-Financial-Agent-Local": "1" };
export async function getRunStrategy(
  runId: string,
  signal?: AbortSignal,
): Promise<StrategySummary | null> {
  return strategySummarySchema
    .nullable()
    .parse(
      (
        await apiClient.get<unknown>(
          `/api/portfolio/research-strategy/runs/${encodeURIComponent(runId)}`,
          { signal },
        )
      ).data,
    );
}
export async function getStrategy(
  signal?: AbortSignal,
): Promise<StrategyState> {
  return stateSchema.parse(
    (
      await apiClient.get<unknown>("/api/portfolio/research-strategy", {
        signal,
      })
    ).data,
  );
}
export async function confirmStrategy(
  parameters: StrategyParameters,
  expected_revision: number,
  cost_policy_revision: number,
  request_id: string,
): Promise<StrategyState> {
  return stateSchema.parse(
    (
      await apiClient.post<unknown>(
        "/api/portfolio/research-strategy",
        {
          parameters,
          expected_revision,
          cost_policy_revision,
          request_id,
          confirm: true,
        },
        { headers },
      )
    ).data,
  );
}
export async function deactivateStrategy(
  expected_revision: number,
): Promise<StrategyState> {
  return stateSchema.parse(
    (
      await apiClient.post<unknown>(
        "/api/portfolio/research-strategy/deactivate",
        { expected_revision },
        { headers },
      )
    ).data,
  );
}
