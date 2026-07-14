/**
 * Alpha Vantage API Client
 *
 * Provides typed methods for accessing Alpha Vantage market data endpoints.
 * Calls the local backend market-data endpoints.
 */

import { apiClient } from "./api";
import type {
  CompanyOverview,
  NewsSentimentResponse,
  CashFlowResponse,
  BalanceSheetResponse,
  MarketMoversResponse,
} from "../types/alphaVantage";

/**
 * Alpha Vantage API Service
 */
export const alphaVantageApi = {
  /**
   * Get comprehensive company overview and fundamentals
   *
   * Returns raw Alpha Vantage OVERVIEW response with:
   * - Company info (Name, Description, Industry, Sector)
   * - Market metrics (Market Cap, P/E Ratio, EPS, Beta)
   * - Financial ratios (Profit Margin, Revenue, Dividend Yield)
   * - Price metrics (52-week high/low, Moving averages)
   *
   * @param symbol - Stock ticker symbol (e.g., "AAPL", "MSFT")
   * @returns Company overview data
   */
  async getCompanyOverview(symbol: string): Promise<CompanyOverview> {
    const response = await apiClient.get<CompanyOverview>(
      `/api/market/overview/${symbol.toUpperCase()}`,
    );
    return response.data;
  },

  /**
   * Get news articles with sentiment analysis for a stock
   *
   * Returns filtered news feed with sentiment scores and classifications.
   * Default limit is 50 articles, sorted by latest first.
   *
   * @param symbol - Stock ticker symbol (e.g., "AAPL", "TSLA")
   * @param options - Optional parameters for limit and sort order
   * @returns News sentiment data with feed and sentiment definitions
   */
  async getNewsSentiment(
    symbol: string,
    options: {
      limit?: number; // 1-1000, default 50
      sort?: "LATEST" | "EARLIEST" | "RELEVANCE"; // default "LATEST"
    } = {},
  ): Promise<NewsSentimentResponse> {
    const params = new URLSearchParams({
      limit: (options.limit || 50).toString(),
      sort: options.sort || "LATEST",
    });

    const response = await apiClient.get<NewsSentimentResponse>(
      `/api/market/news-sentiment/${symbol.toUpperCase()}?${params}`,
    );
    return response.data;
  },

  /**
   * Get cash flow statements (annual and quarterly)
   *
   * Returns annual and quarterly cash flow data including:
   * - Operating Cash Flow, Capital Expenditures
   * - Free Cash Flow (Operating - CapEx)
   * - Dividend Payout, Cash Changes
   *
   * @param symbol - Stock ticker symbol (e.g., "AAPL", "MSFT")
   * @returns Cash flow data with annual and quarterly reports
   */
  async getCashFlow(symbol: string): Promise<CashFlowResponse> {
    const response = await apiClient.get<CashFlowResponse>(
      `/api/market/cash-flow/${symbol.toUpperCase()}`,
    );
    return response.data;
  },

  /**
   * Get balance sheet statements (annual and quarterly)
   *
   * Returns annual and quarterly balance sheet data including:
   * - Total Assets, Total Liabilities, Shareholder Equity
   * - Current Assets/Liabilities, Cash, Debt
   * - Inventory, Goodwill, Intangible Assets
   *
   * @param symbol - Stock ticker symbol (e.g., "AAPL", "MSFT")
   * @returns Balance sheet data with annual and quarterly reports
   */
  async getBalanceSheet(symbol: string): Promise<BalanceSheetResponse> {
    const response = await apiClient.get<BalanceSheetResponse>(
      `/api/market/balance-sheet/${symbol.toUpperCase()}`,
    );
    return response.data;
  },

  /**
   * Get today's top market movers
   *
   * Returns three categories of top performers:
   * - Top Gainers: Stocks with highest price increase (% and $)
   * - Top Losers: Stocks with largest price decrease (% and $)
   * - Most Active: Stocks with highest trading volume
   *
   * Each category shows top 20 stocks with ticker, price, change, and volume.
   *
   * @returns Market movers data with gainers, losers, and most active
   */
  async getMarketMovers(): Promise<MarketMoversResponse> {
    const response = await apiClient.get<MarketMoversResponse>(
      "/api/market/market-movers",
    );
    return response.data;
  },

  /**
   * Filter news sentiment to top positive and negative articles
   *
   * Utility function to extract the most relevant positive/negative news
   * from a full sentiment response.
   *
   * @param response - Full news sentiment response
   * @param maxPositive - Maximum positive sentiment articles (default: 3)
   * @param maxNegative - Maximum negative sentiment articles (default: 3)
   * @returns Filtered news feed with top positive and negative articles
   */
  filterNewsSentiment(
    response: NewsSentimentResponse,
    maxPositive: number = 3,
    maxNegative: number = 3,
  ) {
    const { feed } = response;

    // Filter by sentiment
    const positive = feed
      .filter((item) => item.overall_sentiment_score > 0.15)
      .sort((a, b) => b.overall_sentiment_score - a.overall_sentiment_score)
      .slice(0, maxPositive);

    const negative = feed
      .filter((item) => item.overall_sentiment_score < -0.15)
      .sort((a, b) => a.overall_sentiment_score - b.overall_sentiment_score)
      .slice(0, maxNegative);

    return {
      positive,
      negative,
      total: feed.length,
    };
  },
};
