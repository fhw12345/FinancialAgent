/**
 * Decision tracking — fetch AI decisions enriched with ex-post P&L snapshots.
 */

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../services/api";

export interface PnlSnapshot {
  price: number;
  pnl_pct: number;
  computed_at: string;
}

export interface DecisionMetadata {
  confidence?: number;
  position_size_percent?: number | null;
  reasoning?: string;
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
