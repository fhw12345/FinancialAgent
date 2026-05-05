/**
 * Decision tracking — fetch AI decisions enriched with ex-post P&L snapshots.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../services/api";

export interface PnlSnapshot {
  price: number;
  pnl_pct: number;
  computed_at: string;
}

export interface DecisionMetadata {
  confidence?: number;
  position_size_percent?: number | null;
  entry_price?: number | null;
  stop_loss?: number | null;
  take_profit?: number | null;
  reasoning?: string;
  reasoning_zh?: string | null;
  full_research?: string;
  full_research_zh?: string | null;
  // any other fields the backend stuffs in here
  [key: string]: unknown;
}

export interface DecisionRow {
  order_id: string;
  symbol: string;
  side: "buy" | "sell" | "hold";
  decision_type: "order" | "signal";
  decision_price: number | null;
  quantity: number;
  status: string;
  filled_qty: number | null;
  filled_avg_price: number | null;
  filled_at: string | null;
  user_transaction_id: string | null;
  created_at: string;
  analysis_id: string;
  chat_id: string;
  recommendation_source: string | null;
  pnl_snapshots: Record<string, PnlSnapshot | undefined>;
  metadata: DecisionMetadata;
}

interface DecisionsResponse {
  decisions: DecisionRow[];
  count: number;
}

async function fetchDecisions(
  symbol?: string,
  source?: string,
  limit = 100,
): Promise<DecisionsResponse> {
  const params: Record<string, unknown> = { limit };
  if (symbol) params.symbol = symbol;
  if (source) params.source = source;
  const { data } = await apiClient.get<DecisionsResponse>(
    "/api/portfolio/decisions",
    { params },
  );
  return data;
}

export function useDecisions(symbol?: string, source?: string, limit = 100) {
  return useQuery({
    queryKey: ["decisions", symbol ?? "all", source ?? "all", limit],
    queryFn: () => fetchDecisions(symbol, source, limit),
    staleTime: 60_000, // 1 minute — snapshots only update hourly via cron
    refetchOnWindowFocus: false,
  });
}

export interface MarkExecutedPayload {
  filled_qty: number;
  filled_avg_price: number;
  executed_at?: string;
  notes?: string;
}

export interface MarkExecutedResponse {
  order_id: string;
  transaction_id: string;
  symbol: string;
  side: "buy" | "sell";
  filled_qty: number;
  filled_avg_price: number;
  filled_at: string;
  cash_delta: number;
  new_cash_balance: number;
  cash_warning: string | null;
}

export function useMarkOrderExecuted() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      orderId,
      payload,
    }: {
      orderId: string;
      payload: MarkExecutedPayload;
    }) => {
      const { data } = await apiClient.post<MarkExecutedResponse>(
        `/api/portfolio/orders/${orderId}/mark-executed`,
        payload,
      );
      return data;
    },
    onSuccess: () => {
      // Three downstream views need to refresh: decision rows (status flips
      // to filled), settings panel (cash_balance changed), holdings list
      // (qty/avg_price changed for the symbol).
      qc.invalidateQueries({ queryKey: ["decisions"] });
      qc.invalidateQueries({ queryKey: ["portfolio-settings"] });
      qc.invalidateQueries({ queryKey: ["holdings"] });
      qc.invalidateQueries({ queryKey: ["user-transactions"] });
    },
  });
}
