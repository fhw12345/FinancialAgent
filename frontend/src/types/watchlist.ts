/**
 * Watchlist types matching backend API models.
 */

export interface WatchlistItem {
  watchlist_id: string;
  symbol: string;
  added_at: string;
  last_analyzed_at: string | null;
  notes: string | null;
}

export interface WatchlistItemCreate {
  symbol: string;
  notes?: string | null;
}
