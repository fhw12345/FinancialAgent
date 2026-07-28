/**
 * Unit tests for dateRangeCalculator utility.
 *
 * Tests date range calculation logic for different intervals.
 */

import { afterEach, describe, it, expect, beforeEach, vi } from "vitest";
import {
  calculateDateRange,
  calculateDateRangeForSymbol,
  countInclusiveDays,
  getDateRangePreset,
  getPeriodForInterval,
  validateDateRange,
  type DateRange,
} from "../dateRangeCalculator";

describe("dateRangeCalculator", () => {
  // Mock the current date
  beforeEach(() => {
    // Set a fixed date for consistent testing
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2024-01-15T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("calculateDateRange", () => {
    it("should return user-selected dates if provided", () => {
      // Arrange
      const selectedRange: DateRange = {
        start: "2024-01-01",
        end: "2024-01-10",
      };

      // Act
      const result = calculateDateRange(selectedRange, "1d");

      // Assert
      expect(result).toEqual(selectedRange);
    });

    it("should calculate a recent 7-day range for 1m interval", () => {
      // Arrange
      const emptyRange: DateRange = { start: "", end: "" };

      // Act
      const result = calculateDateRange(emptyRange, "1m");

      // Assert
      expect(result.start).toBe("2024-01-09");
      expect(result.end).toBe("2024-01-15");
    });

    it("should calculate 2-week range for 60m interval", () => {
      // Arrange
      const emptyRange: DateRange = { start: "", end: "" };

      // Act
      const result = calculateDateRange(emptyRange, "60m");

      // Assert
      expect(result.end).toBe("2024-01-15");
      // 14 days back
      expect(result.start).toBe("2024-01-01");
    });

    it("should keep legacy short intraday intervals within 30 days", () => {
      for (const interval of ["2m", "5m", "15m", "30m"] as const) {
        expect(calculateDateRange({ start: "", end: "" }, interval)).toEqual({
          start: "2023-12-17",
          end: "2024-01-15",
        });
      }
    });

    it("should calculate 6-month range for 1d interval (default)", () => {
      // Arrange
      const emptyRange: DateRange = { start: "", end: "" };

      // Act
      const result = calculateDateRange(emptyRange, "1d");

      // Assert
      expect(result.end).toBe("2024-01-15");
      // Approximately 6 months back (180 days)
      const startDate = new Date(result.start);
      const endDate = new Date(result.end);
      const daysDiff = Math.floor(
        (endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24),
      );
      expect(daysDiff).toBeGreaterThan(170); // ~180 days
      expect(daysDiff).toBeLessThan(190);
    });

    it("should calculate 2-year range for 1w interval", () => {
      // Arrange
      const emptyRange: DateRange = { start: "", end: "" };

      // Act
      const result = calculateDateRange(emptyRange, "1w");

      // Assert
      expect(result.end).toBe("2024-01-15");
      // Approximately 2 years back (730 days)
      const startDate = new Date(result.start);
      const endDate = new Date(result.end);
      const daysDiff = Math.floor(
        (endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24),
      );
      expect(daysDiff).toBeGreaterThan(720);
      expect(daysDiff).toBeLessThan(740);
    });

    it("should calculate 5-year range for 1mo interval", () => {
      // Arrange
      const emptyRange: DateRange = { start: "", end: "" };

      // Act
      const result = calculateDateRange(emptyRange, "1mo");

      // Assert
      expect(result.end).toBe("2024-01-15");
      // Approximately 5 years back (1825 days)
      const startDate = new Date(result.start);
      const endDate = new Date(result.end);
      const daysDiff = Math.floor(
        (endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24),
      );
      expect(daysDiff).toBeGreaterThan(1800);
      expect(daysDiff).toBeLessThan(1850);
    });

    it("should handle partial user selection (only start)", () => {
      // Arrange
      const partialRange: DateRange = { start: "2024-01-01", end: "" };

      // Act
      const result = calculateDateRange(partialRange, "1d");

      // Assert
      // Should calculate default range since end is missing
      expect(result.end).toBe("2024-01-15");
      expect(result.start).not.toBe("2024-01-01");
    });

    it("should handle partial user selection (only end)", () => {
      // Arrange
      const partialRange: DateRange = { start: "", end: "2024-01-10" };

      // Act
      const result = calculateDateRange(partialRange, "1d");

      // Assert
      // Should calculate default range since start is missing
      expect(result.end).toBe("2024-01-15");
    });
  });

  describe("getPeriodForInterval", () => {
    it("should return 1d for 1m interval", () => {
      expect(getPeriodForInterval("1m")).toBe("1d");
    });

    it("should return 1mo for 60m interval", () => {
      expect(getPeriodForInterval("60m")).toBe("1mo");
    });

    it("should return 6mo for 1d interval", () => {
      expect(getPeriodForInterval("1d")).toBe("6mo");
    });

    it("should return 1y for 1w interval", () => {
      expect(getPeriodForInterval("1w")).toBe("1y");
    });

    it("should return 2y for 1mo interval", () => {
      expect(getPeriodForInterval("1mo")).toBe("2y");
    });

    it("should return 6mo as default", () => {
      // @ts-expect-error - Testing invalid input
      expect(getPeriodForInterval("invalid")).toBe("6mo");
    });
  });

  describe("Date format", () => {
    it("should return dates in YYYY-MM-DD format", () => {
      // Arrange
      const emptyRange: DateRange = { start: "", end: "" };

      // Act
      const result = calculateDateRange(emptyRange, "1d");

      // Assert
      expect(result.start).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(result.end).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    });

    it("should handle dates at month boundaries", () => {
      // Arrange
      vi.setSystemTime(new Date("2024-01-31T23:59:59Z"));
      const emptyRange: DateRange = { start: "", end: "" };

      // Act
      const result = calculateDateRange(emptyRange, "60m");

      // Assert
      expect(result.end).toBe("2024-01-31");
      expect(result.start).toBeTruthy();
    });

    it("should use the US market calendar near timezone boundaries", () => {
      vi.setSystemTime(new Date("2026-07-29T01:00:00Z"));

      const result = calculateDateRange({ start: "", end: "" }, "1d");

      expect(result.end).toBe("2026-07-28");
    });

    it("should use the symbol exchange calendar for Asian tickers", () => {
      vi.setSystemTime(new Date("2026-07-29T01:00:00Z"));

      const result = calculateDateRangeForSymbol(
        { start: "", end: "" },
        "1d",
        "0700.HK",
      );

      expect(result.end).toBe("2026-07-29");
    });
  });

  describe("presets and validation", () => {
    it("should calculate inclusive preset ranges", () => {
      expect(getDateRangePreset("1w")).toEqual({
        start: "2024-01-09",
        end: "2024-01-15",
      });
      expect(
        countInclusiveDays({
          start: "2024-01-09",
          end: "2024-01-15",
        }),
      ).toBe(7);
    });

    it("should calculate year-to-date and five-year max presets", () => {
      expect(getDateRangePreset("ytd").start).toBe("2024-01-01");
      const max = getDateRangePreset("max");
      expect(max.end).toBe("2024-01-15");
      expect(countInclusiveDays(max)).toBe(1826);
    });

    it("should reject incomplete, reversed, future, and excessive ranges", () => {
      expect(validateDateRange({ start: "", end: "2024-01-15" }, "1d")).toBe(
        "required",
      );
      expect(
        validateDateRange({ start: "2024-01-15", end: "2024-01-01" }, "1d"),
      ).toBe("invalidOrder");
      expect(
        validateDateRange({ start: "2024-01-01", end: "2024-01-16" }, "1d"),
      ).toBe("future");
      expect(
        validateDateRange({ start: "2018-01-01", end: "2024-01-15" }, "1d"),
      ).toBe("tooLong");
    });

    it("should enforce the intraday 30-day provider window", () => {
      expect(
        validateDateRange({ start: "2023-12-16", end: "2024-01-15" }, "1m"),
      ).toBe("intradayTooLong");
      expect(
        validateDateRange({ start: "2023-12-17", end: "2024-01-15" }, "1m"),
      ).toBeNull();
    });
  });
});
