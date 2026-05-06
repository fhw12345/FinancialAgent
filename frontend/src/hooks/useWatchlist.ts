/**
 * React Query hooks for watchlist data.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as watchlistApi from "../services/watchlistApi";
import type { WatchlistItemCreate } from "../types/watchlist";

/**
 * Query keys for watchlist data.
 */
export const watchlistKeys = {
  all: ["watchlist"] as const,
  list: () => [...watchlistKeys.all, "list"] as const,
};

/**
 * Hook to fetch user's watchlist.
 */
export function useWatchlist() {
  return useQuery({
    queryKey: watchlistKeys.list(),
    queryFn: watchlistApi.getWatchlist,
    staleTime: 30000, // Consider stale after 30s
  });
}

/**
 * Hook to add symbol to watchlist.
 */
export function useAddToWatchlist() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (item: WatchlistItemCreate) => watchlistApi.addToWatchlist(item),
    onSuccess: () => {
      // Invalidate and refetch watchlist
      queryClient.invalidateQueries({ queryKey: watchlistKeys.list() });
    },
  });
}

/**
 * Hook to remove symbol from watchlist.
 */
export function useRemoveFromWatchlist() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (watchlistId: string) => watchlistApi.removeFromWatchlist(watchlistId),
    onSuccess: () => {
      // Invalidate and refetch watchlist
      queryClient.invalidateQueries({ queryKey: watchlistKeys.list() });
    },
  });
}

/**
 * Hook to manually trigger watchlist analysis.
 *
 * Pass a symbol to analyze just that one row; pass nothing to batch analyze
 * the whole watchlist (backend skips already-held symbols).
 */
export function useTriggerWatchlistAnalysis() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (symbol?: string) => watchlistApi.triggerWatchlistAnalysis(symbol),
    onSuccess: () => {
      // Invalidate watchlist to refresh "last_analyzed_at" timestamps
      queryClient.invalidateQueries({ queryKey: watchlistKeys.list() });
    },
  });
}
