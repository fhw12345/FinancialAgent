/**
 * Watchlist types matching backend API models.
 */

export interface WatchlistItem {
  watchlist_id: string;
  symbol: string;
  added_at: string;
  last_analyzed_at: string | null;
  notes: string | null;
  current_price: number | null;
  last_price_update: string | null;
  last_session: "pre" | "regular" | "post" | "closed" | null;
  day_change_percent: number | null;
  // W3.18 — extended-hours companion (response-only, see portfolio.ts).
  ext_hours_price: number | null;
  ext_hours_session: "pre" | "post" | null;
  ext_hours_change_percent: number | null;
  ext_hours_asof: string | null;
}

export interface WatchlistItemCreate {
  symbol: string;
  notes?: string | null;
}
