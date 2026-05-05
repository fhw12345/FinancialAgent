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
 * Returns 202 immediately; analysis runs in the background.
 */
export async function triggerWatchlistAnalysis(): Promise<{
  status: string;
  message: string;
}> {
  const response = await apiClient.post<{
    status: string;
    message: string;
  }>("/api/watchlist/analyze");
  return response.data;
}
