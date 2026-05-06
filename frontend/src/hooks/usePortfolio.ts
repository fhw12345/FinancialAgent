/**
 * React Query hooks for portfolio data from Alpaca API.
 *
 * All data is read-only from Alpaca (single source of truth).
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as portfolioApi from "../services/portfolioApi";
import type { NewHolding, UpdateHolding } from "../types/portfolio";

/**
 * Query keys for portfolio data.
 */
export const portfolioKeys = {
  all: ["portfolio"] as const,
  holdings: () => [...portfolioKeys.all, "holdings"] as const,
  summary: () => [...portfolioKeys.all, "summary"] as const,
  history: (period: string) => [...portfolioKeys.all, "history", period] as const,
};

/**
 * Hook to fetch all holdings with auto-refresh.
 *
 * Refetches every 30 seconds to keep prices updated.
 */
export function useHoldings() {
  return useQuery({
    queryKey: portfolioKeys.holdings(),
    queryFn: portfolioApi.getHoldings,
    refetchInterval: 30000, // Refresh every 30s
    staleTime: 15000, // Consider stale after 15s
  });
}

/**
 * Hook to fetch portfolio summary from Alpaca.
 */
export function usePortfolioSummary() {
  return useQuery({
    queryKey: portfolioKeys.summary(),
    queryFn: portfolioApi.getPortfolioSummary,
    refetchInterval: 30000,
    staleTime: 15000,
  });
}

/**
 * Hook to fetch portfolio history for charting.
 *
 * @param period - Time period: "1D", "1M", "1Y", "All"
 */
export function usePortfolioHistory(period: string = "1D") {
  return useQuery({
    queryKey: portfolioKeys.history(period),
    queryFn: () => portfolioApi.getPortfolioHistory(period),
    refetchInterval: 30000, // Refetch every 30 seconds
    staleTime: 25000,
  });
}

/**
 * Hook to add a new holding (manual entry).
 *
 * Invalidates holdings and summary queries on success.
 */
export function useAddHolding() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (holding: NewHolding) => portfolioApi.addHolding(holding),
    onSuccess: () => {
      // Invalidate holdings and summary to refetch
      queryClient.invalidateQueries({ queryKey: portfolioKeys.holdings() });
      queryClient.invalidateQueries({ queryKey: portfolioKeys.summary() });
    },
  });
}

/**
 * Hook to update an existing holding.
 *
 * Invalidates holdings and summary queries on success.
 */
export function useUpdateHolding() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ holdingId, update }: { holdingId: string; update: UpdateHolding }) =>
      portfolioApi.updateHolding(holdingId, update),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: portfolioKeys.holdings() });
      queryClient.invalidateQueries({ queryKey: portfolioKeys.summary() });
    },
  });
}

/**
 * Hook to delete a holding.
 *
 * Invalidates holdings and summary queries on success.
 */
export function useDeleteHolding() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (holdingId: string) => portfolioApi.deleteHolding(holdingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: portfolioKeys.holdings() });
      queryClient.invalidateQueries({ queryKey: portfolioKeys.summary() });
    },
  });
}

/**
 * Manually refresh current_price + P&L for every holding via DataManager.
 * Same logic as the nightly cron, on-demand from a dashboard button.
 */
export function useRefreshHoldingPrices() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => portfolioApi.refreshHoldingPrices(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: portfolioKeys.holdings() });
      queryClient.invalidateQueries({ queryKey: portfolioKeys.summary() });
      // Watchlist GET enriches with live quotes via DataManager (cache 30s);
      // invalidating it forces a fresh round-trip so the watchlist column
      // reflects the same numbers as the holdings table after a refresh.
      queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });
}
