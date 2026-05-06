/**
 * Portfolio types matching backend API models.
 */

export interface Holding {
  holding_id: string;
  symbol: string;
  quantity: number;
  avg_price: number;
  current_price: number | null;
  cost_basis: number;
  market_value: number | null;
  unrealized_pl: number | null;
  unrealized_pl_pct: number | null;
  created_at: string;
  updated_at: string;
  last_price_update: string | null;
  last_session: "pre" | "regular" | "post" | "closed" | null;
}

export interface PortfolioSummary {
  holdings_count: number;
  total_cost_basis: number | null;
  total_market_value: number | null;
  total_unrealized_pl: number | null;
  total_unrealized_pl_pct: number | null;
}

/**
 * Portfolio history for charting
 */
export interface PortfolioHistoryDataPoint {
  timestamp: string;
  value: number;
}

export interface AnalysisMarker {
  timestamp: string;
  symbol: string;
  recommendation: string | null;
  summary: string | null;
}

export interface OrderMarker {
  timestamp: string;
  symbol: string;
  side: string; // "buy" | "sell"
  quantity: number;
  status: string;
  filled_avg_price: number | null;
  order_id: string;
}

export interface PortfolioHistoryResponse {
  data_points: PortfolioHistoryDataPoint[];
  markers: AnalysisMarker[];
  order_markers: OrderMarker[];
  current_value: number | null;
  period: string;
}

/**
 * Request types for holdings management
 */
export interface NewHolding {
  symbol: string;
  quantity: number;
  avg_price: number;
}

export interface UpdateHolding {
  quantity?: number;
  avg_price?: number;
}
