/**
 * Market Data API service
 * Provides symbol search and price data with granularity controls
 */

import axios from "axios";
import { apiClient } from "./api";

// Symbol search types
export interface SymbolSearchResult {
  symbol: string;
  name: string;
  exchange: string;
  type: string;
  match_type?: string;
  confidence?: number;
}

export type SymbolSuggestion = SymbolSearchResult | string;

export class PriceDataError extends Error {
  constructor(
    message: string,
    readonly suggestions: SymbolSuggestion[] = [],
    readonly original?: unknown,
  ) {
    super(message);
    this.name = "PriceDataError";
  }
}

interface PriceErrorDetail {
  message?: unknown;
  suggestions?: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isPriceErrorDetail(value: unknown): value is PriceErrorDetail {
  return isRecord(value);
}

function getErrorDetail(error: unknown): unknown {
  if (axios.isAxiosError<{ detail?: unknown }>(error)) {
    return error.response?.data?.detail;
  }
  if (!isRecord(error) || !isRecord(error.response)) return undefined;
  const data = error.response.data;
  return isRecord(data) ? data.detail : undefined;
}

function isSymbolSearchResult(value: unknown): value is SymbolSearchResult {
  if (value === null || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.symbol === "string" &&
    typeof candidate.name === "string" &&
    typeof candidate.exchange === "string" &&
    typeof candidate.type === "string"
  );
}

export interface SymbolSearchResponse {
  query: string;
  results: SymbolSearchResult[];
}

// Price data types
export interface PriceDataPoint {
  time: string; // YYYY-MM-DD or ISO timestamp
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  market_session?: "pre" | "regular" | "post" | "closed"; // Market session indicator for intraday data
}

export interface PriceDataResponse {
  symbol: string;
  interval: string;
  data: PriceDataPoint[];
  last_updated: string;
}

// Symbol info types
export interface SymbolInfo {
  symbol: string;
  name: string;
  sector: string;
  industry: string;
  exchange: string;
  currency: string;
  market_cap?: number;
  current_price?: number;
}

// Quote types
export interface QuoteData {
  symbol: string;
  price: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  latest_trading_day: string;
  previous_close: number;
  change: number;
  change_percent: string;
}

// Time interval options for charts
export const TIME_INTERVALS = {
  // Intraday intervals
  "1m": "1 Minute",
  "2m": "2 Minutes",
  "5m": "5 Minutes",
  "15m": "15 Minutes",
  "30m": "30 Minutes",
  "60m": "60 Minutes (1 Hour)",
  // Daily+ intervals
  "1d": "1 Day",
  "5d": "5 Days",
  "1w": "1 Week",
  "1mo": "1 Month",
} as const;

export type TimeInterval = keyof typeof TIME_INTERVALS;

// Time period options
export const TIME_PERIODS = {
  "1d": "1 Day",
  "5d": "5 Days",
  "1mo": "1 Month",
  "3mo": "3 Months",
  "6mo": "6 Months",
  "1y": "1 Year",
  "2y": "2 Years",
  "5y": "5 Years",
  ytd: "Year to Date",
  max: "All Time",
} as const;

export type TimePeriod = keyof typeof TIME_PERIODS;

/**
 * Market Data API Service
 */
export const marketService = {
  /**
   * Search for symbols by company name or partial symbol
   */
  async searchSymbols(query: string): Promise<SymbolSearchResponse> {
    const response = await apiClient.get<SymbolSearchResponse>(
      `/api/market/search?q=${encodeURIComponent(query)}`,
    );
    return response.data;
  },

  /**
   * Get price data for a symbol with granularity controls
   */
  async getPriceData(
    symbol: string,
    options: {
      interval?: TimeInterval;
      period?: TimePeriod;
      start_date?: string; // YYYY-MM-DD
      end_date?: string; // YYYY-MM-DD
    } = {},
  ): Promise<PriceDataResponse> {
    const params = new URLSearchParams({
      interval: options.interval || "1d",
      ...(options.period && { period: options.period }),
      ...(options.start_date && { start_date: options.start_date }),
      ...(options.end_date && { end_date: options.end_date }),
    });

    try {
      const response = await apiClient.get<PriceDataResponse>(
        `/api/market/price/${symbol}?${params}`,
      );
      return response.data;
    } catch (error: unknown) {
      const detail = getErrorDetail(error);
      if (typeof detail === "string") {
        throw new PriceDataError(detail, [], error);
      }
      if (isPriceErrorDetail(detail)) {
        throw new PriceDataError(
          typeof detail.message === "string"
            ? detail.message
            : "Price data fetch failed",
          Array.isArray(detail.suggestions)
            ? detail.suggestions.filter(
                (item): item is SymbolSuggestion =>
                  typeof item === "string" || isSymbolSearchResult(item),
              )
            : [],
          error,
        );
      }
      throw error;
    }
  },

  /**
   * Get symbol information for autocomplete enhancement
   */
  async getSymbolInfo(symbol: string): Promise<SymbolInfo> {
    const response = await apiClient.get<SymbolInfo>(
      `/api/market/info/${symbol}`,
    );
    return response.data;
  },

  /**
   * Get real-time quote for a symbol (GLOBAL_QUOTE)
   */
  async getQuote(symbol: string): Promise<QuoteData> {
    const response = await apiClient.get<QuoteData>(
      `/api/market/quote/${symbol}`,
    );
    return response.data;
  },

  /**
   * Convert price data to TradingView Lightweight Charts format
   */
  convertToChartData(
    priceData: PriceDataPoint[],
    chartType: "line" | "candlestick" = "line",
  ) {
    if (chartType === "line") {
      return priceData.map((point) => ({
        time: point.time,
        value: point.close,
      }));
    } else {
      return priceData.map((point) => ({
        time: point.time,
        open: point.open,
        high: point.high,
        low: point.low,
        close: point.close,
      }));
    }
  },

  /**
   * Get chart time intervals based on selected period
   */
  getRecommendedInterval(period: TimePeriod): TimeInterval {
    switch (period) {
      case "1d":
        return "5m";
      case "5d":
        return "15m";
      case "1mo":
        return "60m";
      case "2y":
      case "5y":
        return "1w";
      case "max":
        return "1mo";
      default:
        return "1d";
    }
  },

  /**
   * Format price for display
   */
  formatPrice(price: number, currency: string = "USD"): string {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(price);
  },

  /**
   * Format volume for display
   */
  formatVolume(volume: number): string {
    if (volume >= 1_000_000_000) {
      return `${(volume / 1_000_000_000).toFixed(1)}B`;
    } else if (volume >= 1_000_000) {
      return `${(volume / 1_000_000).toFixed(1)}M`;
    } else if (volume >= 1_000) {
      return `${(volume / 1_000).toFixed(1)}K`;
    }
    return volume.toString();
  },

  /**
   * Calculate price change and percentage
   */
  calculatePriceChange(currentPrice: number, previousPrice: number) {
    const change = currentPrice - previousPrice;
    const changePercent = (change / previousPrice) * 100;

    return {
      change: change,
      changePercent: changePercent,
      isPositive: change >= 0,
      formatted: {
        change: this.formatPrice(Math.abs(change)),
        changePercent: `${changePercent >= 0 ? "+" : ""}${changePercent.toFixed(2)}%`,
      },
    };
  },

  /**
   * Debounced search function for autocomplete
   */
  createDebouncedSearch(delay: number = 300) {
    let timeoutId: ReturnType<typeof setTimeout>;

    return (
      query: string,
      callback: (results: SymbolSearchResponse) => void,
    ) => {
      clearTimeout(timeoutId);

      if (query.length < 1) {
        callback({ query, results: [] });
        return;
      }

      timeoutId = setTimeout(async () => {
        try {
          const results = await this.searchSymbols(query);
          callback(results);
        } catch (error) {
          console.error("Symbol search error:", error);
          callback({ query, results: [] });
        }
      }, delay);
    };
  },
};
