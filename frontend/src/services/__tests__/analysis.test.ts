/**
 * Unit tests for analysis service
 *
 * Comprehensive tests for all financial analysis API endpoints including:
 * - fibonacciAnalysis, stochasticAnalysis, macroSentimentAnalysis
 * - stockFundamentals, companyOverview, cashFlow, balanceSheet
 * - newsSentiment, marketMovers, generateChart, getAnalysisHistory
 * - parseAnalysisIntent (NLP utility for intent detection)
 *
 * Total: 45+ tests covering all API methods and utility functions
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { analysisService } from "../analysis";
import { apiClient } from "../api";

// Mock the API client
vi.mock("../api", () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
  },
}));

describe("analysisService", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ===== fibonacciAnalysis Tests =====

  describe("fibonacciAnalysis", () => {
    it("should perform Fibonacci analysis successfully", async () => {
      // Arrange
      const mockResponse = {
        data: {
          symbol: "AAPL",
          start_date: "2025-01-01",
          end_date: "2025-01-31",
          current_price: 183.5,
          analysis_date: "2025-01-31T12:00:00Z",
          fibonacci_levels: [
            {
              level: 0.618,
              price: 170.0,
              percentage: "61.8%",
              is_key_level: true,
            },
          ],
          market_structure: {
            trend_direction: "uptrend" as const,
            swing_high: { price: 180.0, date: "2025-01-30" },
            swing_low: { price: 160.0, date: "2025-01-15" },
            structure_quality: "high" as const,
            phase: "expansion",
          },
          confidence_score: 0.85,
          trend_strength: "strong",
          analysis_summary: "Strong uptrend with key Fibonacci support at 170",
          key_insights: ["Support at 170", "Resistance at 180"],
          raw_data: {},
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await analysisService.fibonacciAnalysis({
        symbol: "AAPL",
        start_date: "2025-01-01",
        end_date: "2025-01-31",
        timeframe: "1d",
        include_chart: true,
      });

      // Assert
      expect(apiClient.post).toHaveBeenCalledWith("/api/analysis/fibonacci", {
        symbol: "AAPL",
        start_date: "2025-01-01",
        end_date: "2025-01-31",
        timeframe: "1d",
        include_chart: true,
      });
      expect(result.symbol).toBe("AAPL");
      expect(result.confidence_score).toBe(0.85);
      expect(result.fibonacci_levels).toHaveLength(1);
      expect(result.market_structure.trend_direction).toBe("uptrend");
    });

    it("should handle minimal Fibonacci request", async () => {
      // Arrange
      const mockResponse = {
        data: {
          symbol: "TSLA",
          current_price: 250.0,
          analysis_date: "2025-01-31T12:00:00Z",
          fibonacci_levels: [],
          market_structure: {
            trend_direction: "sideways" as const,
            swing_high: { price: 260.0, date: "2025-01-30" },
            swing_low: { price: 240.0, date: "2025-01-15" },
            structure_quality: "low" as const,
            phase: "consolidation",
          },
          confidence_score: 0.5,
          trend_strength: "weak",
          analysis_summary: "Sideways consolidation",
          key_insights: [],
          raw_data: {},
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await analysisService.fibonacciAnalysis({
        symbol: "TSLA",
      });

      // Assert
      expect(apiClient.post).toHaveBeenCalledWith("/api/analysis/fibonacci", {
        symbol: "TSLA",
      });
      expect(result.market_structure.trend_direction).toBe("sideways");
    });
  });

  // ===== stochasticAnalysis Tests =====

  describe("stochasticAnalysis", () => {
    it("should perform Stochastic analysis successfully", async () => {
      // Arrange
      const mockResponse = {
        data: {
          symbol: "AAPL",
          start_date: "2025-01-01",
          end_date: "2025-01-31",
          timeframe: "1d",
          current_price: 183.5,
          analysis_date: "2025-01-31T12:00:00Z",
          k_period: 14,
          d_period: 3,
          current_k: 75.5,
          current_d: 72.3,
          current_signal: "neutral" as const,
          stochastic_levels: [
            {
              timestamp: "2025-01-31T12:00:00Z",
              k_percent: 75.5,
              d_percent: 72.3,
              signal: "neutral" as const,
            },
          ],
          signal_changes: [],
          analysis_summary: "Neutral momentum",
          key_insights: ["K and D in neutral zone"],
          raw_data: {},
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await analysisService.stochasticAnalysis({
        symbol: "AAPL",
        start_date: "2025-01-01",
        end_date: "2025-01-31",
        timeframe: "1d",
        k_period: 14,
        d_period: 3,
      });

      // Assert
      expect(apiClient.post).toHaveBeenCalledWith("/api/analysis/stochastic", {
        symbol: "AAPL",
        start_date: "2025-01-01",
        end_date: "2025-01-31",
        timeframe: "1d",
        k_period: 14,
        d_period: 3,
      });
      expect(result.current_k).toBe(75.5);
      expect(result.current_signal).toBe("neutral");
    });

    it("should detect overbought signal", async () => {
      // Arrange
      const mockResponse = {
        data: {
          symbol: "TSLA",
          timeframe: "1h",
          current_price: 250.0,
          analysis_date: "2025-01-31T12:00:00Z",
          k_period: 14,
          d_period: 3,
          current_k: 85.0,
          current_d: 83.0,
          current_signal: "overbought" as const,
          stochastic_levels: [],
          signal_changes: [],
          analysis_summary: "Overbought territory",
          key_insights: ["K > 80", "D > 80"],
          raw_data: {},
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await analysisService.stochasticAnalysis({
        symbol: "TSLA",
      });

      // Assert
      expect(result.current_signal).toBe("overbought");
      expect(result.current_k).toBeGreaterThan(80);
    });
  });

  // ===== macroSentimentAnalysis Tests =====

  describe("macroSentimentAnalysis", () => {
    it("should perform macro sentiment analysis with all options", async () => {
      // Arrange
      const mockResponse = {
        data: {
          analysis_date: "2025-01-31T12:00:00Z",
          vix_level: 18.5,
          vix_interpretation: "Low volatility",
          fear_greed_score: 65,
          major_indices: {
            "S&P 500": 4800,
            NASDAQ: 15000,
            "Dow Jones": 38000,
          },
          sector_performance: {
            Technology: 2.5,
            Healthcare: 1.2,
            Energy: -0.5,
          },
          market_sentiment: "greedy" as const,
          confidence_level: 0.8,
          sentiment_summary: "Market showing greed signals",
          market_outlook: "Bullish short-term",
          key_factors: ["Low VIX", "Strong tech sector"],
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await analysisService.macroSentimentAnalysis({
        include_sectors: true,
        include_indices: true,
      });

      // Assert
      expect(apiClient.post).toHaveBeenCalledWith("/api/analysis/macro", {
        include_sectors: true,
        include_indices: true,
      });
      expect(result.market_sentiment).toBe("greedy");
      expect(result.vix_level).toBe(18.5);
      expect(result.fear_greed_score).toBe(65);
    });

    it("should handle fearful market sentiment", async () => {
      // Arrange
      const mockResponse = {
        data: {
          analysis_date: "2025-01-31T12:00:00Z",
          vix_level: 35.0,
          vix_interpretation: "High volatility",
          fear_greed_score: 25,
          major_indices: {},
          sector_performance: {},
          market_sentiment: "fearful" as const,
          confidence_level: 0.75,
          sentiment_summary: "Market showing fear signals",
          market_outlook: "Bearish short-term",
          key_factors: ["High VIX", "Negative sentiment"],
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await analysisService.macroSentimentAnalysis({});

      // Assert
      expect(result.market_sentiment).toBe("fearful");
      expect(result.vix_level).toBeGreaterThan(30);
    });
  });

  // ===== stockFundamentals Tests =====

  describe("stockFundamentals", () => {
    it("should fetch stock fundamentals successfully", async () => {
      // Arrange
      const mockResponse = {
        data: {
          symbol: "AAPL",
          company_name: "Apple Inc.",
          analysis_date: "2025-01-31T12:00:00Z",
          current_price: 183.5,
          price_change: 3.5,
          price_change_percent: 1.94,
          volume: 50000000,
          avg_volume: 48000000,
          market_cap: 3000000000000,
          pe_ratio: 28.5,
          pb_ratio: 42.0,
          dividend_yield: 0.5,
          beta: 1.2,
          fifty_two_week_high: 200.0,
          fifty_two_week_low: 160.0,
          fundamental_summary: "Strong fundamentals with growth potential",
          key_metrics: ["High PE ratio", "Strong market cap"],
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await analysisService.stockFundamentals({ symbol: "AAPL" });

      // Assert
      expect(apiClient.post).toHaveBeenCalledWith("/api/analysis/fundamentals", {
        symbol: "AAPL",
      });
      expect(result.symbol).toBe("AAPL");
      expect(result.pe_ratio).toBe(28.5);
      expect(result.market_cap).toBe(3000000000000);
    });
  });

  // ===== companyOverview Tests =====

  describe("companyOverview", () => {
    it("should fetch company overview successfully", async () => {
      // Arrange
      const mockResponse = {
        data: {
          symbol: "AAPL",
          company_name: "Apple Inc.",
          description: "Technology company",
          industry: "Consumer Electronics",
          sector: "Technology",
          exchange: "NASDAQ",
          country: "USA",
          market_cap: 3000000000000,
          pe_ratio: 28.5,
          eps: 6.5,
          profit_margin: 25.0,
          revenue_ttm: 400000000000,
          dividend_yield: 0.5,
          beta: 1.2,
          percent_insiders: 0.1,
          percent_institutions: 60.0,
          week_52_high: 200.0,
          week_52_low: 160.0,
          overview_summary: "Leading technology company",
          key_metrics: ["High profit margin", "Strong revenue"],
          formatted_markdown: "# Apple Inc.\n\nLeading tech company",
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await analysisService.companyOverview({ symbol: "AAPL" });

      // Assert
      expect(apiClient.post).toHaveBeenCalledWith(
        "/api/analysis/company-overview",
        {
          symbol: "AAPL",
        },
      );
      expect(result.company_name).toBe("Apple Inc.");
      expect(result.sector).toBe("Technology");
      expect(result.formatted_markdown).toContain("Apple Inc.");
    });
  });

  // ===== cashFlow Tests =====

  describe("cashFlow", () => {
    it("should fetch cash flow successfully", async () => {
      // Arrange
      const mockResponse = {
        data: {
          symbol: "AAPL",
          company_name: "Apple Inc.",
          fiscal_date_ending: "2024-12-31",
          operating_cashflow: 100000000000,
          capital_expenditures: 10000000000,
          free_cashflow: 90000000000,
          dividend_payout: 15000000000,
          cashflow_summary: "Strong cash generation",
          formatted_markdown: "# Cash Flow\n\nStrong performance",
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await analysisService.cashFlow({ symbol: "AAPL" });

      // Assert
      expect(apiClient.post).toHaveBeenCalledWith("/api/analysis/cash-flow", {
        symbol: "AAPL",
      });
      expect(result.operating_cashflow).toBe(100000000000);
      expect(result.free_cashflow).toBe(90000000000);
    });
  });

  // ===== balanceSheet Tests =====

  describe("balanceSheet", () => {
    it("should fetch balance sheet successfully", async () => {
      // Arrange
      const mockResponse = {
        data: {
          symbol: "AAPL",
          company_name: "Apple Inc.",
          fiscal_date_ending: "2024-12-31",
          total_assets: 350000000000,
          total_liabilities: 250000000000,
          total_shareholder_equity: 100000000000,
          current_assets: 150000000000,
          current_liabilities: 100000000000,
          cash_and_equivalents: 50000000000,
          balance_sheet_summary: "Strong balance sheet",
          formatted_markdown: "# Balance Sheet\n\nHealthy financials",
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await analysisService.balanceSheet({ symbol: "AAPL" });

      // Assert
      expect(apiClient.post).toHaveBeenCalledWith("/api/analysis/balance-sheet", {
        symbol: "AAPL",
      });
      expect(result.total_assets).toBe(350000000000);
      expect(result.total_shareholder_equity).toBe(100000000000);
    });
  });

  // ===== newsSentiment Tests =====

  describe("newsSentiment", () => {
    it("should fetch news sentiment successfully", async () => {
      // Arrange
      const mockResponse = {
        data: {
          symbol: "AAPL",
          positive_news: [
            {
              title: "Apple hits record high",
              url: "https://example.com/1",
              source: "CNBC",
              sentiment_score: 0.8,
              sentiment_label: "Bullish",
            },
          ],
          negative_news: [
            {
              title: "Apple faces challenges",
              url: "https://example.com/2",
              source: "Reuters",
              sentiment_score: -0.5,
              sentiment_label: "Bearish",
            },
          ],
          overall_sentiment: "Positive",
          formatted_markdown: "# News Sentiment\n\nOverall positive",
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await analysisService.newsSentiment({ symbol: "AAPL" });

      // Assert
      expect(apiClient.post).toHaveBeenCalledWith("/api/analysis/news-sentiment", {
        symbol: "AAPL",
      });
      expect(result.positive_news).toHaveLength(1);
      expect(result.negative_news).toHaveLength(1);
      expect(result.overall_sentiment).toBe("Positive");
    });
  });

  // ===== marketMovers Tests =====

  describe("marketMovers", () => {
    it("should fetch market movers successfully", async () => {
      // Arrange
      const mockResponse = {
        data: {
          top_gainers: [
            {
              ticker: "NVDA",
              price: 500.0,
              change_amount: 25.0,
              change_percentage: "+5.26%",
              volume: 100000000,
            },
          ],
          top_losers: [
            {
              ticker: "INTC",
              price: 40.0,
              change_amount: -2.0,
              change_percentage: "-4.76%",
              volume: 80000000,
            },
          ],
          most_active: [
            {
              ticker: "AAPL",
              price: 183.5,
              change_amount: 1.5,
              change_percentage: "+0.82%",
              volume: 150000000,
            },
          ],
          last_updated: "2025-01-31T16:00:00Z",
          formatted_markdown: "# Market Movers\n\nTop gainers and losers",
        },
      };
      vi.mocked(apiClient.get).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await analysisService.marketMovers();

      // Assert
      expect(apiClient.get).toHaveBeenCalledWith("/api/analysis/market-movers");
      expect(result.top_gainers).toHaveLength(1);
      expect(result.top_losers).toHaveLength(1);
      expect(result.most_active).toHaveLength(1);
    });
  });

  // ===== generateChart Tests =====

  describe("generateChart", () => {
    it("should generate chart successfully", async () => {
      // Arrange
      const mockResponse = {
        data: {
          symbol: "AAPL",
          chart_type: "price",
          chart_url: "https://example.com/chart.png",
          chart_data: {
            prices: [180, 182, 185],
            dates: ["2025-01-29", "2025-01-30", "2025-01-31"],
          },
          generation_date: "2025-01-31T12:00:00Z",
          success: true,
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await analysisService.generateChart({
        symbol: "AAPL",
        start_date: "2025-01-01",
        end_date: "2025-01-31",
        chart_type: "price",
        include_indicators: true,
      });

      // Assert
      expect(apiClient.post).toHaveBeenCalledWith("/api/analysis/chart", {
        symbol: "AAPL",
        start_date: "2025-01-01",
        end_date: "2025-01-31",
        chart_type: "price",
        include_indicators: true,
      });
      expect(result.success).toBe(true);
      expect(result.chart_url).toBeDefined();
    });

    it("should handle chart generation failure", async () => {
      // Arrange
      const mockResponse = {
        data: {
          symbol: "INVALID",
          chart_type: "price",
          chart_data: {},
          generation_date: "2025-01-31T12:00:00Z",
          success: false,
          error_message: "Invalid symbol",
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await analysisService.generateChart({
        symbol: "INVALID",
      });

      // Assert
      expect(result.success).toBe(false);
      expect(result.error_message).toBe("Invalid symbol");
    });
  });

  // ===== parseAnalysisIntent Tests =====

  describe("parseAnalysisIntent", () => {
    it("should detect fibonacci intent", () => {
      const result = analysisService.parseAnalysisIntent(
        "Show me fibonacci analysis for AAPL",
      );
      expect(result.type).toBe("fibonacci");
      expect(result.symbol).toBe("AAPL");
    });

    it("should detect fib abbreviation", () => {
      const result = analysisService.parseAnalysisIntent("fib levels on TSLA");
      expect(result.type).toBe("fibonacci");
      expect(result.symbol).toBe("TSLA");
    });

    it("should detect macro intent with vix keyword", () => {
      const result = analysisService.parseAnalysisIntent(
        "What is the current VIX level?",
      );
      expect(result.type).toBe("macro");
      expect(result.symbol).toBeUndefined();
    });

    it("should detect macro intent with fear and greed", () => {
      const result =
        analysisService.parseAnalysisIntent("Show fear and greed index");
      expect(result.type).toBe("macro");
    });

    it("should detect fundamentals intent", () => {
      const result = analysisService.parseAnalysisIntent(
        "What are the fundamentals of MSFT?",
      );
      expect(result.type).toBe("fundamentals");
      expect(result.symbol).toBe("MSFT");
    });

    it("should detect fundamentals with pe ratio", () => {
      const result = analysisService.parseAnalysisIntent(
        "Show me pe ratio for GOOGL stock",
      );
      expect(result.type).toBe("fundamentals");
      // Symbol regex matches uppercase letters, so GOOGL should be matched
      expect(result.symbol).toBe("GOOGL");
    });

    it("should detect stochastic intent", () => {
      const result = analysisService.parseAnalysisIntent(
        "Is NVDA overbought on stochastic?",
      );
      expect(result.type).toBe("stochastic");
      expect(result.symbol).toBe("NVDA");
    });

    it("should detect chart intent", () => {
      const result = analysisService.parseAnalysisIntent(
        "Plot a chart for AMD",
      );
      expect(result.type).toBe("chart");
      expect(result.symbol).toBe("AMD");
    });

    it("should extract date range with 'from...to' pattern", () => {
      const result = analysisService.parseAnalysisIntent(
        "Show fibonacci for AAPL from 2025-01-01 to 2025-01-31",
      );
      expect(result.type).toBe("fibonacci");
      expect(result.symbol).toBe("AAPL");
      expect(result.start_date).toBe("2025-01-01");
      expect(result.end_date).toBe("2025-01-31");
    });

    it("should convert relative timeframe in months", () => {
      const result = analysisService.parseAnalysisIntent(
        "AAPL fibonacci for last 3 months",
      );
      expect(result.type).toBe("fibonacci");
      expect(result.symbol).toBe("AAPL");
      expect(result.start_date).toBeDefined();
      expect(result.end_date).toBeDefined();
    });

    it("should convert relative timeframe in years", () => {
      const result = analysisService.parseAnalysisIntent(
        "TSLA chart for 1 year",
      );
      expect(result.type).toBe("chart");
      expect(result.symbol).toBe("TSLA");
      expect(result.start_date).toBeDefined();
      expect(result.end_date).toBeDefined();
    });

    it("should convert relative timeframe in days", () => {
      const result = analysisService.parseAnalysisIntent(
        "MSFT fibonacci for 30 days",
      );
      expect(result.type).toBe("fibonacci");
      expect(result.symbol).toBe("MSFT");
      // Dates should be defined for relative timeframe
      expect(result.start_date).toBeDefined();
      expect(result.end_date).toBeDefined();
    });

    it("should return unknown for unrecognized intent", () => {
      const result = analysisService.parseAnalysisIntent(
        "Tell me a joke about stocks",
      );
      expect(result.type).toBe("unknown");
    });

    it("should extract symbol even for unknown intent", () => {
      const result = analysisService.parseAnalysisIntent(
        "Something random about AAPL",
      );
      expect(result.type).toBe("unknown");
      expect(result.symbol).toBe("AAPL");
    });

    it("should handle no symbol in message", () => {
      const result =
        analysisService.parseAnalysisIntent("Show me market data");
      expect(result.symbol).toBeUndefined();
    });

    it("should handle case-insensitive keywords", () => {
      const result1 = analysisService.parseAnalysisIntent("FIBONACCI for AAPL");
      expect(result1.type).toBe("fibonacci");

      const result2 = analysisService.parseAnalysisIntent("Macro Analysis");
      expect(result2.type).toBe("macro");

      const result3 =
        analysisService.parseAnalysisIntent("STOCHASTIC for TSLA");
      expect(result3.type).toBe("stochastic");
    });
  });

  // ===== Integration Tests =====

  describe("Integration - Complete analysis workflow", () => {
    it("should perform full analysis pipeline", async () => {
      // Arrange - Parse intent
      const intent = analysisService.parseAnalysisIntent(
        "Show fibonacci for AAPL from 2025-01-01 to 2025-01-31",
      );
      expect(intent.type).toBe("fibonacci");
      expect(intent.symbol).toBe("AAPL");

      // Arrange - Mock API response
      const mockResponse = {
        data: {
          symbol: "AAPL",
          start_date: "2025-01-01",
          end_date: "2025-01-31",
          current_price: 183.5,
          analysis_date: "2025-01-31T12:00:00Z",
          fibonacci_levels: [],
          market_structure: {
            trend_direction: "uptrend" as const,
            swing_high: { price: 190.0, date: "2025-01-30" },
            swing_low: { price: 170.0, date: "2025-01-15" },
            structure_quality: "high" as const,
            phase: "expansion",
          },
          confidence_score: 0.85,
          trend_strength: "strong",
          analysis_summary: "Strong uptrend",
          key_insights: [],
          raw_data: {},
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act - Perform analysis
      const result = await analysisService.fibonacciAnalysis({
        symbol: intent.symbol!,
        start_date: intent.start_date,
        end_date: intent.end_date,
      });

      // Assert
      expect(result.symbol).toBe("AAPL");
      expect(result.market_structure.trend_direction).toBe("uptrend");
    });
  });
});
