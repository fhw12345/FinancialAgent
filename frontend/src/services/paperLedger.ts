/** Manual PAPER scenario API. Exact decimal strings; never a real/AI-approved execution. */
import { z } from "zod";
import { apiClient } from "./api";
const decimal = z.string().refine((value) => {
  const absolute = value.startsWith("-") ? value.slice(1) : value;
  const parts = absolute.split(".");
  return parts.length <= 2 && parts.every((part) => /^[0-9]+$/.test(part));
});
const symbol = z.string();
export const paperSettingsSchema = z.object({
  name: z.string(),
  initial_cash: decimal,
  symbols: z.array(symbol),
  commission_bps: decimal,
  slippage_bps: decimal,
  currency: z.literal("USD"),
  basis: z.literal("FIFO-inclusive-buy-fees@1"),
  arithmetic: z.literal("decimal-half-even-cents@1"),
  corporate_actions: z.literal("manual-reconciliation@1"),
});
const trade = z.object({
  kind: z.literal("trade"),
  symbol,
  side: z.enum(["buy", "sell"]),
  quantity: decimal,
  reference_price: decimal,
  origin: z.literal("manual_unverified_scenario"),
});
const split = z.object({
  kind: z.literal("split"),
  symbol,
  numerator: z.number().int(),
  denominator: z.number().int(),
  origin: z.literal("manual_unverified_scenario"),
});
const dividend = z.object({
  kind: z.literal("dividend"),
  symbol,
  gross_per_share: decimal,
  withholding: decimal,
  origin: z.literal("manual_unverified_scenario"),
});
const close = z.object({ kind: z.literal("close") });
const mark = z.object({
  symbol,
  session_date: z.string(),
  price: decimal.nullable(),
  currency: z.literal("USD").nullable(),
  source: z.string(),
  error: z.string().nullable(),
});
const valuation = z.object({
  kind: z.literal("valuation"),
  session_date: z.string(),
  ledger_sequence: z.number().int(),
  fetched_at: z.string(),
  reconciliation: z.literal("corporate-actions-inspected-through-this-session"),
  marks: z.array(mark),
});
const payload = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("created"), settings: paperSettingsSchema }),
  trade,
  split,
  dividend,
  close,
  valuation,
]);
const experiment = z.object({
  schema_version: z.literal(1),
  experiment_id: z.string(),
  sequence: z.number().int(),
  events: z.array(
    z.object({
      event_id: z.string(),
      sequence: z.number().int(),
      request_id: z.string(),
      request_hash: z.string(),
      recorded_at: z.string(),
      payload,
      previous_hash: z.string(),
      event_hash: z.string(),
    }),
  ),
});
export const paperViewSchema = z.object({
  experiment,
  settings: paperSettingsSchema,
  projection: z.object({
    cash: decimal,
    realized_pnl: decimal,
    commissions: decimal,
    dividend_income: decimal,
    positions: z.array(
      z.object({ symbol, quantity: decimal, cost_basis: decimal }),
    ),
    lots: z.array(
      z.object({
        event_id: z.string(),
        symbol,
        quantity: decimal,
        cost_basis: decimal,
      }),
    ),
    closed: z.boolean(),
    last_ledger_sequence: z.number().int(),
  }),
  valuation: z
    .object({
      session_date: z.string(),
      recorded_at: z.string(),
      status: z.enum(["complete", "unavailable"]),
      nav: decimal.nullable(),
      scenario_pnl: decimal.nullable(),
      marked_positions: z.number().int(),
      total_positions: z.number().int(),
      errors: z.array(z.string()),
      stale: z.boolean(),
      stale_reasons: z.array(z.string()),
      marks: z.array(mark),
    })
    .nullable(),
  current_session: z.string(),
  trade_receipts: z.array(
    z.object({
      event_id: z.string(),
      effective_price: decimal,
      principal: decimal,
      commission: decimal,
    }),
  ),
  provenance: z.literal("manual_unverified_scenario"),
  ai_validated: z.literal(false),
  broker_execution: z.literal(false),
});
export type PaperView = z.infer<typeof paperViewSchema>;
export type ManualPaperEntry = z.infer<
  typeof trade | typeof split | typeof dividend | typeof close
>;
const summary = z.object({
  experiment_id: z.string(),
  name: z.string(),
  sequence: z.number().int(),
  closed: z.boolean(),
});
export type PaperSummary = z.infer<typeof summary>;
export type NewPaperSettings = Pick<
  z.infer<typeof paperSettingsSchema>,
  "name" | "initial_cash" | "symbols" | "commission_bps" | "slippage_bps"
>;
const headers = { "X-Financial-Agent-Local": "1" };
const root = "/api/portfolio/paper/experiments";
export async function listPaper(signal?: AbortSignal): Promise<PaperSummary[]> {
  return z
    .array(summary)
    .parse((await apiClient.get<unknown>(root, { signal })).data);
}
export async function getPaper(
  id: string,
  signal?: AbortSignal,
): Promise<PaperView> {
  return paperViewSchema.parse(
    (
      await apiClient.get<unknown>(`${root}/${encodeURIComponent(id)}`, {
        signal,
      })
    ).data,
  );
}
export async function createPaper(
  settings: NewPaperSettings,
  request_id: string,
): Promise<PaperView> {
  return paperViewSchema.parse(
    (
      await apiClient.post<unknown>(
        root,
        {
          settings,
          request_id,
          confirm: true,
          acknowledgment: "manual-paper-only-no-real-account-or-ai-approval",
        },
        { headers },
      )
    ).data,
  );
}
const version = (view: PaperView, request_id: string) => ({
  request_id,
  expected_sequence: view.experiment.sequence,
  confirm: true,
  acknowledgment: "manual-scenario-not-ai-approved-or-market-fill",
});
export async function journalPaper(
  view: PaperView,
  entry: ManualPaperEntry,
  requestId: string,
): Promise<PaperView> {
  return paperViewSchema.parse(
    (
      await apiClient.post<unknown>(
        `${root}/${encodeURIComponent(view.experiment.experiment_id)}/journal`,
        { ...version(view, requestId), entry },
        { headers },
      )
    ).data,
  );
}
export async function refreshPaper(
  view: PaperView,
  requestId: string,
): Promise<PaperView> {
  return paperViewSchema.parse(
    (
      await apiClient.post<unknown>(
        `${root}/${encodeURIComponent(view.experiment.experiment_id)}/valuation`,
        {
          ...version(view, requestId),
          session_date: view.current_session,
          reconciliation: "corporate-actions-inspected-through-this-session",
        },
        { headers, timeout: 120000 },
      )
    ).data,
  );
}
export async function exportPaper(id: string): Promise<string> {
  const value = experiment.parse(
    (await apiClient.get<unknown>(`${root}/${encodeURIComponent(id)}/manifest`))
      .data,
  );
  return JSON.stringify(value, null, 2);
}
