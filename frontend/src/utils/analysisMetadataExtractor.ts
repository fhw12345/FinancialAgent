/**
 * Analysis Metadata Extractor
 *
 * Extracts only visualization-critical data from full analysis results.
 * This keeps MongoDB storage lean by excluding large price history arrays.
 *
 * Philosophy: Store parameters and results, not raw data.
 * Raw data can be re-fetched from API/cache using the parameters.
 */

import type {
  FibonacciAnalysisResponse,
  StochasticAnalysisResponse,
} from "../services/analysis";

/**
 * Compact metadata for Fibonacci analysis.
 * Contains only what's needed to visualize the overlay.
 */
export interface FibonacciMetadata {
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  fibonacci_levels: Array<{ level: number; price: number; percentage: string }>;
  swing_high: { price: number; date: string };
  swing_low: { price: number; date: string };
  trend_direction: "uptrend" | "downtrend";
  confidence_score?: number;
  raw_data?: FibonacciAnalysisResponse["raw_data"];
}

/**
 * Compact metadata for Stochastic analysis.
 * Contains only signal data, not full K/D arrays.
 */
export interface StochasticMetadata {
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  // Latest values only (not full arrays)
  current_k: number;
  current_d: number;
  signal: "overbought" | "oversold" | "neutral";
  crossover_signal?: "bullish" | "bearish" | null;
}

/**
 * Extract compact metadata from Fibonacci analysis.
 * Excludes price history to save storage.
 */
export function extractFibonacciMetadata(
  analysis: FibonacciAnalysisResponse,
): FibonacciMetadata {
  console.log("📦 Extracting Fibonacci metadata:", {
    hasRawData: !!analysis.raw_data,
    rawDataKeys: Object.keys(analysis.raw_data || {}),
  });

  return {
    symbol: analysis.symbol || "",
    timeframe: (analysis.raw_data?.timeframe as string) || "1d",
    start_date: analysis.start_date || "",
    end_date: analysis.end_date || "",
    fibonacci_levels: analysis.fibonacci_levels || [],
    raw_data: analysis.raw_data, // Include raw_data for top_trends
    swing_high: analysis.market_structure?.swing_high || { price: 0, date: "" },
    swing_low: analysis.market_structure?.swing_low || { price: 0, date: "" },
    trend_direction:
      (analysis.market_structure?.trend_direction as "uptrend" | "downtrend") ||
      "uptrend",
    confidence_score: analysis.confidence_score,
    // Explicitly exclude: price_data (large array)
  };
}

/**
 * Extract compact metadata from Stochastic analysis.
 * Stores only latest values, not full time series.
 */
function numberArray(value: unknown): number[] {
  return Array.isArray(value)
    ? value.filter((item): item is number => typeof item === "number")
    : [];
}

export function extractStochasticMetadata(
  analysis: StochasticAnalysisResponse,
): StochasticMetadata {
  // Defensive: arrays can arrive in raw_data from older backend responses.
  const kArray = numberArray(analysis.raw_data.stochastic_k);
  const dArray = numberArray(analysis.raw_data.stochastic_d);

  // Get latest K and D values
  const latestK = kArray.length > 0 ? kArray[kArray.length - 1] : 50;
  const latestD = dArray.length > 0 ? dArray[dArray.length - 1] : 50;

  // Determine signal
  let signal: "overbought" | "oversold" | "neutral" = "neutral";
  if (latestK > 80 && latestD > 80) {
    signal = "overbought";
  } else if (latestK < 20 && latestD < 20) {
    signal = "oversold";
  }

  // Detect crossover
  let crossover_signal: "bullish" | "bearish" | null = null;
  if (kArray.length >= 2 && dArray.length >= 2) {
    const prevK = kArray[kArray.length - 2];
    const prevD = dArray[dArray.length - 2];

    if (prevK < prevD && latestK > latestD) {
      crossover_signal = "bullish";
    } else if (prevK > prevD && latestK < latestD) {
      crossover_signal = "bearish";
    }
  }

  return {
    symbol: analysis.symbol || "",
    timeframe: analysis.timeframe || "1d",
    start_date: analysis.start_date || "",
    end_date: analysis.end_date || "",
    current_k: latestK,
    current_d: latestD,
    signal,
    crossover_signal,
    // Explicitly exclude: stochastic_k, stochastic_d arrays
    // Explicitly exclude: dates array
    // Explicitly exclude: price_data
  };
}
