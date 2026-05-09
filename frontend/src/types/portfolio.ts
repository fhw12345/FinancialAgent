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
  // W3.18 — extended-hours companion (response-only, recomputed each
  // GET via yfinance Ticker.info on the backend). Populated when the
  // primary session is regular/closed AND a fresh pre/post print is
  // available; null otherwise.
  ext_hours_price: number | null;
  ext_hours_session: "pre" | "post" | null;
  ext_hours_change_percent: number | null;
  ext_hours_asof: string | null;
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
