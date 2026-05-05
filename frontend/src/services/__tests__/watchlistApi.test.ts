/**
 * Unit tests for watchlist API service
 *
 * Tests CRUD operations for watchlist management:
 * - getWatchlist (fetch all items)
 * - addToWatchlist (create new item)
 * - removeFromWatchlist (delete by ID)
 * - triggerWatchlistAnalysis (manual analysis trigger)
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  getWatchlist,
  addToWatchlist,
  removeFromWatchlist,
  triggerWatchlistAnalysis,
} from "../watchlistApi";
import { apiClient } from "../api";

// Mock the API client
vi.mock("../api", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

describe("watchlistApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ===== getWatchlist Tests =====

  describe("getWatchlist", () => {
    it("should fetch watchlist successfully", async () => {
      // Arrange
      const mockResponse = {
        data: [
          {
            watchlist_id: "w1",
            user_id: "u1",
            symbol: "AAPL",
            added_at: "2025-01-31T12:00:00Z",
            notes: "Apple stock",
          },
          {
            watchlist_id: "w2",
            user_id: "u1",
            symbol: "TSLA",
            added_at: "2025-01-31T11:00:00Z",
            notes: "Tesla stock",
          },
        ],
      };
      vi.mocked(apiClient.get).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await getWatchlist();

      // Assert
      expect(apiClient.get).toHaveBeenCalledWith("/api/watchlist");
      expect(result).toHaveLength(2);
      expect(result[0].symbol).toBe("AAPL");
      expect(result[1].symbol).toBe("TSLA");
    });

    it("should return empty array when no watchlist items", async () => {
      // Arrange
      const mockResponse = {
        data: [],
      };
      vi.mocked(apiClient.get).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await getWatchlist();

      // Assert
      expect(result).toHaveLength(0);
    });
  });

  // ===== addToWatchlist Tests =====

  describe("addToWatchlist", () => {
    it("should add symbol to watchlist successfully", async () => {
      // Arrange
      const newItem = {
        symbol: "NVDA",
        notes: "GPU manufacturer",
      };
      const mockResponse = {
        data: {
          watchlist_id: "w3",
          user_id: "u1",
          symbol: "NVDA",
          added_at: "2025-01-31T13:00:00Z",
          notes: "GPU manufacturer",
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await addToWatchlist(newItem);

      // Assert
      expect(apiClient.post).toHaveBeenCalledWith("/api/watchlist", newItem);
      expect(result.watchlist_id).toBe("w3");
      expect(result.symbol).toBe("NVDA");
      expect(result.notes).toBe("GPU manufacturer");
    });

    it("should add symbol without notes", async () => {
      // Arrange
      const newItem = {
        symbol: "MSFT",
      };
      const mockResponse = {
        data: {
          watchlist_id: "w4",
          user_id: "u1",
          symbol: "MSFT",
          added_at: "2025-01-31T14:00:00Z",
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await addToWatchlist(newItem);

      // Assert
      expect(result.symbol).toBe("MSFT");
      expect(result.notes).toBeUndefined();
    });
  });

  // ===== removeFromWatchlist Tests =====

  describe("removeFromWatchlist", () => {
    it("should remove watchlist item successfully", async () => {
      // Arrange
      vi.mocked(apiClient.delete).mockResolvedValueOnce({});

      // Act
      await removeFromWatchlist("w1");

      // Assert
      expect(apiClient.delete).toHaveBeenCalledWith("/api/watchlist/w1");
    });

    it("should handle different watchlist IDs", async () => {
      // Arrange
      vi.mocked(apiClient.delete).mockResolvedValue({});

      // Act & Assert
      await removeFromWatchlist("w123");
      expect(apiClient.delete).toHaveBeenCalledWith("/api/watchlist/w123");

      await removeFromWatchlist("abc-def-ghi");
      expect(apiClient.delete).toHaveBeenCalledWith("/api/watchlist/abc-def-ghi");
    });
  });

  // ===== triggerWatchlistAnalysis Tests =====

  describe("triggerWatchlistAnalysis", () => {
    it("should trigger analysis successfully", async () => {
      // Arrange
      const mockResponse = {
        data: {
          status: "success",
          message: "Analysis triggered for 5 symbols",
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await triggerWatchlistAnalysis();

      // Assert
      expect(apiClient.post).toHaveBeenCalledWith(
        "/api/watchlist/analyze"
      );
      expect(result.status).toBe("success");
      expect(result.message).toBe("Analysis triggered for 5 symbols");
    });

    it("should handle empty watchlist", async () => {
      // Arrange
      const mockResponse = {
        data: {
          status: "success",
          message: "No symbols in watchlist",
        },
      };
      vi.mocked(apiClient.post).mockResolvedValueOnce(mockResponse);

      // Act
      const result = await triggerWatchlistAnalysis();

      // Assert
      expect(result.status).toBe("success");
      expect(result.message).toBe("No symbols in watchlist");
    });
  });

  // ===== Integration Tests =====

  describe("Integration - Complete CRUD workflow", () => {
    it("should perform full CRUD operations", async () => {
      // Arrange
      const getResponse = { data: [] };
      const addResponse = {
        data: {
          watchlist_id: "w1",
          user_id: "u1",
          symbol: "AAPL",
          added_at: "2025-01-31T12:00:00Z",
        },
      };
      const analyzeResponse = {
        data: {
          status: "success",
          message: "Analysis triggered for 1 symbol",
        },
      };

      vi.mocked(apiClient.get).mockResolvedValueOnce(getResponse);
      vi.mocked(apiClient.post)
        .mockResolvedValueOnce(addResponse)
        .mockResolvedValueOnce(analyzeResponse);
      vi.mocked(apiClient.delete).mockResolvedValueOnce({});

      // Act - Get empty watchlist
      let watchlist = await getWatchlist();
      expect(watchlist).toHaveLength(0);

      // Act - Add symbol
      const newItem = await addToWatchlist({ symbol: "AAPL" });
      expect(newItem.symbol).toBe("AAPL");

      // Act - Trigger analysis
      const analysisResult = await triggerWatchlistAnalysis();
      expect(analysisResult.status).toBe("success");

      // Act - Remove symbol
      await removeFromWatchlist("w1");
      expect(apiClient.delete).toHaveBeenCalledWith("/api/watchlist/w1");
    });
  });
});
