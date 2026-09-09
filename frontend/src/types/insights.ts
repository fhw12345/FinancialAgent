/**
 * TypeScript interfaces for Market Insights Platform.
 * Maps to backend Pydantic models in src/api/schemas/insights_models.py
 */

/** Status levels for metric scores */
export type MetricStatus = "low" | "normal" | "elevated" | "high";

/** Rich explanation structure for each metric */
export interface MetricExplanation {
  summary: string;
  detail: string;
  methodology: string;
  formula: string | null;
  historical_context: string;
  actionable_insight: string;
}

/** Individual metric with score and explanation */
export interface InsightMetric {
  id: string;
  name: string;
  score: number;
  status: MetricStatus;
  explanation: MetricExplanation;
  data_sources: string[];
  last_updated: string;
  raw_data: Record<string, unknown>;
}

/** Composite score aggregating multiple metrics */
export interface CompositeScore {
  score: number;
  status: MetricStatus;
  weights: Record<string, number>;
  breakdown: Record<string, number>;
  interpretation: string;
}

/** Lightweight category metadata for listing */
export interface CategoryMetadata {
  id: string;
  name: string;
  icon: string;
  description: string;
  metric_count: number;
  last_updated: string | null;
}

/** Complete category with all metrics */
export interface InsightCategory {
  id: string;
  name: string;
  icon: string;
  description: string;
  metrics: InsightMetric[];
  composite: CompositeScore | null;
  last_updated: string;
}

/** API Response: List of categories */
export interface CategoriesListResponse {
  categories: CategoryMetadata[];
  count: number;
}

/** API Response: Refresh operation result */
export interface RefreshResponse {
  prefetch_errors?: Record<string, string>;
  success: boolean;
  category_id: string;
  message: string;
  last_updated: string;
}

/** Single data point in a trend series */
export interface TrendDataPoint {
  date: string; // YYYY-MM-DD format
  score: number; // 0-100
  status: MetricStatus;
}

/** API Response: Trend data for a category */
export interface TrendResponse {
  category_id: string;
  days: number;
  trend: TrendDataPoint[]; // Composite score trend
  metrics: Record<string, TrendDataPoint[]>; // Individual metric trends
}
