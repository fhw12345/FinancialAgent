/**
 * Financial Analysis API service
 * Provides type-safe API calls to backend financial analysis endpoints
 */

import { apiClient } from "./api";

// Analysis request types
export interface FibonacciAnalysisRequest {
  symbol: string;
  start_date?: string;
  end_date?: string;
  timeframe?: "60m" | "1d" | "1w" | "1mo";
  include_chart?: boolean;
}

export interface StochasticAnalysisRequest {
  symbol: string;
  start_date?: string;
  end_date?: string;
  timeframe?: "60m" | "1d" | "1w" | "1mo";
  k_period?: number;
  d_period?: number;
}

export interface MacroAnalysisRequest {
  include_sectors?: boolean;
  include_indices?: boolean;
}

export interface StockFundamentalsRequest {
  symbol: string;
}

export interface ChartRequest {
  symbol: string;
  start_date?: string;
  end_date?: string;
  chart_type?: "price" | "fibonacci" | "volume";
  include_indicators?: boolean;
}

// Analysis response types
export interface PricePoint {
  price: number;
  date: string;
}

export interface FibonacciLevel {
  level: number;
  price: number;
  percentage: string;
  is_key_level: boolean;
}

export interface MarketStructure {
  trend_direction: "uptrend" | "downtrend" | "sideways";
  swing_high: PricePoint;
  swing_low: PricePoint;
  structure_quality: "high" | "medium" | "low";
  phase: string;
}

export interface FibonacciAnalysisResponse {
  symbol: string;
  start_date?: string;
  end_date?: string;
  current_price: number;
  analysis_date: string;
  fibonacci_levels: FibonacciLevel[];
  market_structure: MarketStructure;
  confidence_score: number;
  pressure_zone?: Record<string, number>;
  trend_strength: string;
  analysis_summary: string;
  key_insights: string[];
  raw_data: Record<string, any>;
}

export interface StochasticLevel {
  timestamp: string;
  k_percent: number;
  d_percent: number;
  signal: "overbought" | "oversold" | "neutral";
}

export interface StochasticAnalysisResponse {
  symbol: string;
  start_date?: string;
  end_date?: string;
  timeframe: string;
  current_price: number;
  analysis_date: string;
  k_period: number;
  d_period: number;
  current_k: number;
  current_d: number;
  current_signal: "overbought" | "oversold" | "neutral";
  stochastic_levels: StochasticLevel[];
  signal_changes: Array<Record<string, any>>;
  analysis_summary: string;
  key_insights: string[];
  raw_data: Record<string, any>;
}

export interface MacroSentimentResponse {
  analysis_date: string;
  vix_level: number;
  vix_interpretation: string;
  fear_greed_score: number;
  major_indices: Record<string, number>;
  sector_performance: Record<string, number>;
  market_sentiment: "fearful" | "neutral" | "greedy";
  confidence_level: number;
  sentiment_summary: string;
  market_outlook: string;
  key_factors: string[];
}

export interface StockFundamentalsResponse {
  symbol: string;
  company_name: string;
  analysis_date: string;
  current_price: number;
  price_change: number;
  price_change_percent: number;
  volume: number;
  avg_volume: number;
  market_cap: number;
  pe_ratio?: number;
  pb_ratio?: number;
  dividend_yield?: number;
  beta?: number;
  fifty_two_week_high: number;
  fifty_two_week_low: number;
  fundamental_summary: string;
  key_metrics: string[];
}

export interface CompanyOverviewResponse {
  symbol: string;
  company_name: string;
  description: string;
  industry: string;
  sector: string;
  exchange: string;
  country: string;
  market_cap?: number;
  pe_ratio?: number;
  eps?: number;
  profit_margin?: number;
  revenue_ttm?: number;
  dividend_yield?: number;
  beta?: number;
  percent_insiders?: number;
  percent_institutions?: number;
  week_52_high?: number;
  week_52_low?: number;
  overview_summary: string;
  key_metrics: string[];
  formatted_markdown?: string;
}

export interface CashFlowResponse {
  symbol: string;
  company_name: string;
  fiscal_date_ending: string;
  operating_cashflow?: number;
  capital_expenditures?: number;
  free_cashflow?: number;
  dividend_payout?: number;
  cashflow_summary: string;
  formatted_markdown?: string;
}

export interface BalanceSheetResponse {
  symbol: string;
  company_name: string;
  fiscal_date_ending: string;
  total_assets?: number;
  total_liabilities?: number;
  total_shareholder_equity?: number;
  current_assets?: number;
  current_liabilities?: number;
  cash_and_equivalents?: number;
  balance_sheet_summary: string;
  formatted_markdown?: string;
}

export interface NewsArticle {
  title: string;
  url: string;
  source: string;
  sentiment_score: number;
  sentiment_label: string;
}

export interface NewsSentimentResponse {
  symbol: string;
  positive_news: NewsArticle[];
  negative_news: NewsArticle[];
  overall_sentiment: string;
  formatted_markdown?: string;
}

export interface MarketMover {
  ticker: string;
  price: number;
  change_amount: number;
  change_percentage: string;
  volume: number;
}

export interface MarketMoversResponse {
  top_gainers: MarketMover[];
  top_losers: MarketMover[];
  most_active: MarketMover[];
  last_updated: string;
  formatted_markdown?: string;
}

export interface ChartGenerationResponse {
  symbol: string;
  chart_type: string;
  chart_url?: string;
  chart_data: Record<string, any>;
  generation_date: string;
  success: boolean;
  error_message?: string;
}

/**
 * Financial Analysis API Service
 */
export const analysisService = {
  /**
   * Perform Fibonacci retracement analysis
   */
  async fibonacciAnalysis(
    request: FibonacciAnalysisRequest,
  ): Promise<FibonacciAnalysisResponse> {
    const response = await apiClient.post<FibonacciAnalysisResponse>(
      "/api/analysis/fibonacci",
      request,
    );
    return response.data;
  },

  /**
   * Analyze macro market sentiment
   */
  async macroSentimentAnalysis(
    request: MacroAnalysisRequest = {},
  ): Promise<MacroSentimentResponse> {
    const response = await apiClient.post<MacroSentimentResponse>(
      "/api/analysis/macro",
      request,
    );
    return response.data;
  },

  /**
   * Get stock fundamentals
   */
  async stockFundamentals(
    request: StockFundamentalsRequest,
  ): Promise<StockFundamentalsResponse> {
    const response = await apiClient.post<StockFundamentalsResponse>(
      "/api/analysis/fundamentals",
      request,
    );
    return response.data;
  },

  /**
   * Get company overview with key metrics and ownership data
   */
  async companyOverview(
    request: { symbol: string },
  ): Promise<CompanyOverviewResponse> {
    const response = await apiClient.post<CompanyOverviewResponse>(
      "/api/analysis/company-overview",
      request,
    );
    return response.data;
  },

  /**
   * Perform Stochastic Oscillator analysis
   */
  async stochasticAnalysis(
    request: StochasticAnalysisRequest,
  ): Promise<StochasticAnalysisResponse> {
    const response = await apiClient.post<StochasticAnalysisResponse>(
      "/api/analysis/stochastic",
      request,
    );
    return response.data;
  },

  /**
   * Generate financial chart
   */
  async generateChart(request: ChartRequest): Promise<ChartGenerationResponse> {
    const response = await apiClient.post<ChartGenerationResponse>(
      "/api/analysis/chart",
      request,
    );
    return response.data;
  },

  /**
   * Get analysis history
   */
  /**
   * Get cash flow statement
   */
  async cashFlow(
    request: { symbol: string },
  ): Promise<CashFlowResponse> {
    const response = await apiClient.post<CashFlowResponse>(
      "/api/analysis/cash-flow",
      request,
    );
    return response.data;
  },

  /**
   * Get balance sheet
   */
  async balanceSheet(
    request: { symbol: string },
  ): Promise<BalanceSheetResponse> {
    const response = await apiClient.post<BalanceSheetResponse>(
      "/api/analysis/balance-sheet",
      request,
    );
    return response.data;
  },

  /**
   * Get news sentiment
   */
  async newsSentiment(
    request: { symbol: string },
  ): Promise<NewsSentimentResponse> {
    const response = await apiClient.post<NewsSentimentResponse>(
      "/api/analysis/news-sentiment",
      request,
    );
    return response.data;
  },

  /**
   * Get market movers
   */
  async marketMovers(): Promise<MarketMoversResponse> {
    const response = await apiClient.get<MarketMoversResponse>(
      "/api/analysis/market-movers",
    );
    return response.data;
  },

  /**
   * Parse user message and determine analysis intent
   */
  parseAnalysisIntent(message: string): {
    type:
      | "fibonacci"
      | "macro"
      | "fundamentals"
      | "chart"
      | "stochastic"
      | "unknown";
    symbol?: string;
    start_date?: string;
    end_date?: string;
  } {
    const lowerMessage = message.toLowerCase();

    // Extract symbol pattern (e.g., AAPL, TSLA, etc.)
    const symbolMatch = message.match(/\b([A-Z]{1,5})\b/);
    const symbol = symbolMatch ? symbolMatch[1] : undefined;

    // Extract date range patterns
    let start_date: string | undefined;
    let end_date: string | undefined;

    // Look for "from YYYY-MM-DD to YYYY-MM-DD" pattern
    const dateRangeMatch = message.match(
      /from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})/i,
    );
    if (dateRangeMatch) {
      start_date = dateRangeMatch[1];
      end_date = dateRangeMatch[2];
    } else {
      // Look for relative timeframes and convert to dates
      const timeframeMatch = message.match(
        /(\d+)(?:\s*)(?:mo|month|months|m|y|year|years|d|day|days)/i,
      );
      if (timeframeMatch) {
        const amount = parseInt(timeframeMatch[1]);
        const unit = message
          .match(/(?:mo|month|months|m|y|year|years|d|day|days)/i)?.[0]
          ?.toLowerCase();

        const endDate = new Date();
        const startDate = new Date();

        if (unit?.includes("y")) {
          startDate.setFullYear(startDate.getFullYear() - amount);
        } else if (unit?.includes("mo") || unit?.includes("month")) {
          startDate.setMonth(startDate.getMonth() - amount);
        } else if (unit?.includes("d")) {
          startDate.setDate(startDate.getDate() - amount);
        }

        start_date = startDate.toISOString().split("T")[0];
        end_date = endDate.toISOString().split("T")[0];
      }
    }

    // Determine analysis type
    if (lowerMessage.includes("fibonacci") || lowerMessage.includes("fib")) {
      return { type: "fibonacci", symbol, start_date, end_date };
    }

    if (
      lowerMessage.includes("macro") ||
      lowerMessage.includes("market sentiment") ||
      lowerMessage.includes("vix") ||
      lowerMessage.includes("fear") ||
      lowerMessage.includes("greed")
    ) {
      return { type: "macro" };
    }

    if (
      lowerMessage.includes("fundamental") ||
      lowerMessage.includes("pe ratio") ||
      lowerMessage.includes("company") ||
      lowerMessage.includes("valuation") ||
      lowerMessage.includes("earnings") ||
      lowerMessage.includes("dividend")
    ) {
      return { type: "fundamentals", symbol };
    }

    if (
      lowerMessage.includes("stochastic") ||
      lowerMessage.includes("oscillator") ||
      lowerMessage.includes("overbought") ||
      lowerMessage.includes("oversold")
    ) {
      return { type: "stochastic", symbol, start_date, end_date };
    }

    if (
      lowerMessage.includes("chart") ||
      lowerMessage.includes("graph") ||
      lowerMessage.includes("plot")
    ) {
      return { type: "chart", symbol, start_date, end_date };
    }

    return { type: "unknown", symbol };
  },
};
