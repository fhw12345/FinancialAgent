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
}

export interface WatchlistItemCreate {
  symbol: string;
  notes?: string | null;
}
