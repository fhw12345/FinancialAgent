/**
 * Watchlist API service.
 * Manages watched stock symbols for automated analysis.
 */

import { apiClient } from "./api";
import { WatchlistItem, WatchlistItemCreate } from "../types/watchlist";

/**
 * Get all watchlist items for the user.
 */
export async function getWatchlist(): Promise<WatchlistItem[]> {
  const response = await apiClient.get<WatchlistItem[]>("/api/watchlist");
  return response.data;
}

/**
 * Add a symbol to the watchlist.
 */
export async function addToWatchlist(
  item: WatchlistItemCreate
): Promise<WatchlistItem> {
  const response = await apiClient.post<WatchlistItem>("/api/watchlist", item);
  return response.data;
}

/**
 * Remove a symbol from the watchlist.
 */
export async function removeFromWatchlist(watchlistId: string): Promise<void> {
  await apiClient.delete(`/api/watchlist/${watchlistId}`);
}

/**
 * Manually trigger analysis for the watchlist symbols.
 * - No symbol → batch analyze all watchlist (skips already-held).
 * - With symbol → run analysis for just that one (used by per-row buttons).
 */
export async function triggerWatchlistAnalysis(symbol?: string): Promise<{
  status: string;
  message?: string;
  symbol?: string;
}> {
  const url = symbol
    ? `/api/watchlist/analyze?symbol=${encodeURIComponent(symbol)}`
    : "/api/watchlist/analyze";
  const response = await apiClient.post<{
    status: string;
    message?: string;
    symbol?: string;
  }>(url);
  return response.data;
}
