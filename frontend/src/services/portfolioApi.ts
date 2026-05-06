/**
 * Portfolio API client for Alpaca paper trading integration.
 *
 * All portfolio data comes from Alpaca API (single source of truth).
 * No manual holdings management - Alpaca handles all positions.
 */

import { apiClient } from "./api";
import type {
  Holding,
  PortfolioSummary,
  NewHolding,
  UpdateHolding,
} from "../types/portfolio";

/**
 * Get all holdings from Alpaca (single source of truth).
 */
export async function getHoldings(): Promise<Holding[]> {
  const response = await apiClient.get<Holding[]>("/api/portfolio/holdings");
  return response.data;
}

/**
 * Get portfolio summary from Alpaca account.
 */
export async function getPortfolioSummary(): Promise<PortfolioSummary> {
  const response = await apiClient.get<PortfolioSummary>(
    "/api/portfolio/summary"
  );
  return response.data;
}

/**
 * Format P/L for display.
 *
 * @param pl - Profit/loss amount
 * @param plPct - Profit/loss percentage
 * @returns Formatted string like "+$500.00 (+3.33%)"
 */
export function formatPL(pl: number | null, plPct: number | null): string {
  if (pl === null || plPct === null) {
    return "N/A";
  }

  const sign = pl >= 0 ? "+" : "";
  const plFormatted = `${sign}$${Math.abs(pl).toFixed(2)}`;

  // Use more decimal places for very small percentages
  const absPlPct = Math.abs(plPct);
  let plPctFormatted: string;
  if (absPlPct < 0.01 && absPlPct > 0) {
    // Show 4 decimal places for tiny percentages
    plPctFormatted = `${sign}${plPct.toFixed(4)}%`;
  } else {
    // Show 2 decimal places for normal percentages
    plPctFormatted = `${sign}${plPct.toFixed(2)}%`;
  }

  return `${plFormatted} (${plPctFormatted})`;
}

/**
 * Get P/L color for styling.
 *
 * @param pl - Profit/loss amount
 * @returns Color for styling: "green" (profit), "red" (loss), "gray" (neutral)
 */
export function getPLColor(
  pl: number | null
): "green" | "red" | "gray" {
  if (pl === null) return "gray";
  if (pl > 0) return "green";
  if (pl < 0) return "red";
  return "gray";
}

/**
 * Add a new holding (manual entry).
 *
 * @param holding - New holding data (symbol, quantity, avg_price)
 * @returns Created holding with full details
 */
export async function addHolding(holding: NewHolding): Promise<Holding> {
  const response = await apiClient.post<Holding>(
    "/api/portfolio/holdings",
    holding
  );
  return response.data;
}

/**
 * Update an existing holding.
 *
 * @param holdingId - ID of the holding to update
 * @param update - Fields to update (quantity, avg_price)
 * @returns Updated holding with full details
 */
export async function updateHolding(
  holdingId: string,
  update: UpdateHolding
): Promise<Holding> {
  const response = await apiClient.patch<Holding>(
    `/api/portfolio/holdings/${holdingId}`,
    update
  );
  return response.data;
}

/**
 * Delete a holding.
 *
 * @param holdingId - ID of the holding to delete
 */
export async function deleteHolding(holdingId: string): Promise<void> {
  await apiClient.delete(`/api/portfolio/holdings/${holdingId}`);
}

export async function refreshHoldingPrices(): Promise<{
  refreshed: number;
  failed: number;
  total: number;
}> {
  const { data } = await apiClient.post("/api/portfolio/holdings/refresh-prices");
  return data;
}
