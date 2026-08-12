/**
 * API service for Market Insights Platform.
 * Communicates with backend /api/insights/ endpoints.
 */

import { apiClient } from "./api";
import type {
  CategoriesListResponse,
  CompositeScore,
  InsightCategory,
  InsightMetric,
  RefreshResponse,
  TrendResponse,
} from "../types/insights";

// Re-export types for use by hooks
export type { RefreshResponse };

/**
 * Get list of all available insight categories.
 * Returns lightweight metadata without full metric details.
 */
export async function getCategories(): Promise<CategoriesListResponse> {
  const response = await apiClient.get<CategoriesListResponse>(
    "/api/insights/categories",
  );
  return response.data;
}

/**
 * Get complete data for a specific category including all metrics.
 *
 * @param categoryId - Category identifier (e.g., 'ai_sector_risk')
 * @param forceRefresh - If true, bypass cache and recalculate
 */
export async function getCategory(
  categoryId: string,
  forceRefresh: boolean = false,
): Promise<InsightCategory> {
  const response = await apiClient.get<InsightCategory>(
    `/api/insights/${categoryId}`,
    { params: { force_refresh: forceRefresh } },
  );
  return response.data;
}

/**
 * Get just the composite score for a category.
 * Lighter-weight call for overview/summary views.
 *
 * @param categoryId - Category identifier
 */
export async function getCompositeScore(
  categoryId: string,
): Promise<CompositeScore> {
  const response = await apiClient.get<CompositeScore>(
    `/api/insights/${categoryId}/composite`,
  );
  return response.data;
}

/**
 * Get a single metric with full explanation.
 *
 * @param categoryId - Category identifier
 * @param metricId - Metric identifier within the category
 */
export async function getMetric(
  categoryId: string,
  metricId: string,
): Promise<InsightMetric> {
  const response = await apiClient.get<InsightMetric>(
    `/api/insights/${categoryId}/${metricId}`,
  );
  return response.data;
}

/**
 * Force refresh a category's data.
 * Clears cache and recalculates from fresh API data.
 * Use sparingly - makes multiple Alpha Vantage API calls.
 *
 * @param categoryId - Category identifier
 */
export async function refreshCategory(
  categoryId: string,
): Promise<RefreshResponse> {
  const response = await apiClient.post<RefreshResponse>(
    `/api/insights/${categoryId}/refresh`,
  );
  return response.data;
}

/**
 * Get historical trend data for a category.
 * Returns composite and individual metric trends over time.
 *
 * @param categoryId - Category identifier
 * @param days - Number of days of history (7, 14, 30, 60, or 90)
 */
export async function getTrend(
  categoryId: string,
  days: number = 30,
): Promise<TrendResponse> {
  const response = await apiClient.get<TrendResponse>(
    `/api/insights/${categoryId}/trend`,
    { params: { days } },
  );
  return response.data;
}

/**
 * Get color class based on metric status.
 * Utility function for consistent UI styling.
 */
export function getStatusColor(status: string): string {
  switch (status) {
    case "low":
      return "text-green-600";
    case "normal":
      return "text-blue-600";
    case "elevated":
      return "text-orange-600";
    case "high":
      return "text-red-600";
    default:
      return "text-gray-600";
  }
}

/**
 * Get background color class based on metric status.
 */
export function getStatusBgColor(status: string): string {
  switch (status) {
    case "low":
      return "bg-green-100";
    case "normal":
      return "bg-blue-100";
    case "elevated":
      return "bg-orange-100";
    case "high":
      return "bg-red-100";
    default:
      return "bg-gray-100";
  }
}

/**
 * Format score for display (0-100 scale).
 */
export function formatScore(score: number): string {
  if (score < 0) return "N/A";
  return score.toFixed(0);
}

/**
 * Get status label for display.
 */
export function getStatusLabel(status: string): string {
  switch (status) {
    case "low":
      return "Low Risk";
    case "normal":
      return "Normal";
    case "elevated":
      return "Elevated";
    case "high":
      return "High Risk";
    default:
      return status;
  }
}
