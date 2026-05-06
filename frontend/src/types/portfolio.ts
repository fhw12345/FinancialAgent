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
  day_change_percent: number | null;
}

export interface PortfolioSummary {
  holdings_count: number;
  total_cost_basis: number | null;
  total_market_value: number | null;
  total_unrealized_pl: number | null;
  total_unrealized_pl_pct: number | null;
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
