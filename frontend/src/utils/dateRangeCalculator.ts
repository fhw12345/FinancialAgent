/**
 * Date Range Calculator Utility
 *
 * Centralizes date range calculation logic to avoid duplication across components.
 */

import type { TimeInterval } from "../services/market";

export interface DateRange {
  start: string;
  end: string;
}

export type DateRangePreset = "1w" | "1m" | "3m" | "6m" | "1y" | "ytd" | "max";

export type DateRangeValidationCode =
  "required" | "invalidOrder" | "future" | "tooLong" | "intradayTooLong";

const DAY_MS = 24 * 60 * 60 * 1000;
const MAX_RANGE_DAYS = 5 * 365;
const MAX_INTRADAY_DAYS = 30;
const DEFAULT_MARKET_TIMEZONE = "America/New_York";

export function getMarketTimeZone(symbol: string): string {
  const normalized = symbol.toUpperCase();
  if (normalized.endsWith(".HK")) return "Asia/Hong_Kong";
  if (normalized.endsWith(".SS") || normalized.endsWith(".SZ")) {
    return "Asia/Shanghai";
  }
  if (normalized.endsWith(".T")) return "Asia/Tokyo";
  if (normalized.endsWith(".L")) return "Europe/London";
  return DEFAULT_MARKET_TIMEZONE;
}

function calendarDate(
  now: Date,
  timeZone: string = DEFAULT_MARKET_TIMEZONE,
): Date {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const values: { year?: number; month?: number; day?: number } = {};
  for (const part of parts) {
    if (part.type === "year" || part.type === "month" || part.type === "day") {
      values[part.type] = Number(part.value);
    }
  }
  if (
    values.year === undefined ||
    values.month === undefined ||
    values.day === undefined
  ) {
    throw new Error(`Unable to resolve calendar date for ${timeZone}`);
  }
  return new Date(Date.UTC(values.year, values.month - 1, values.day));
}

function parseCalendarDate(value: string): Date {
  return new Date(`${value}T00:00:00Z`);
}

function formatCalendarDate(value: Date): string {
  return value.toISOString().split("T")[0];
}

function subtractDays(value: Date, days: number): Date {
  return new Date(value.getTime() - days * DAY_MS);
}

export function isIntradayInterval(interval: TimeInterval): boolean {
  return ["1m", "2m", "5m", "15m", "30m", "60m"].includes(interval);
}

export function getDateRangePreset(
  preset: DateRangePreset,
  now: Date = new Date(),
  timeZone: string = DEFAULT_MARKET_TIMEZONE,
): DateRange {
  const end = calendarDate(now, timeZone);
  let start: Date;

  switch (preset) {
    case "1w":
      start = subtractDays(end, 6);
      break;
    case "1m":
      start = subtractDays(end, 29);
      break;
    case "3m":
      start = subtractDays(end, 89);
      break;
    case "6m":
      start = subtractDays(end, 179);
      break;
    case "1y":
      start = subtractDays(end, 364);
      break;
    case "ytd":
      start = new Date(Date.UTC(end.getUTCFullYear(), 0, 1));
      break;
    case "max":
      start = subtractDays(end, MAX_RANGE_DAYS);
      break;
  }

  return {
    start: formatCalendarDate(start),
    end: formatCalendarDate(end),
  };
}

export function countInclusiveDays(range: DateRange): number {
  if (!range.start || !range.end) return 0;
  return (
    Math.floor(
      (parseCalendarDate(range.end).getTime() -
        parseCalendarDate(range.start).getTime()) /
        DAY_MS,
    ) + 1
  );
}

export function validateDateRange(
  range: DateRange,
  interval: TimeInterval,
  now: Date = new Date(),
  timeZone: string = DEFAULT_MARKET_TIMEZONE,
): DateRangeValidationCode | null {
  if (!range.start || !range.end) return "required";

  const start = parseCalendarDate(range.start);
  const end = parseCalendarDate(range.end);
  const today = calendarDate(now, timeZone);

  if (start > end) return "invalidOrder";
  if (start > today || end > today) return "future";

  const inclusiveDays = countInclusiveDays(range);
  if (inclusiveDays - 1 > MAX_RANGE_DAYS) return "tooLong";
  if (isIntradayInterval(interval) && inclusiveDays > MAX_INTRADAY_DAYS) {
    return "intradayTooLong";
  }
  return null;
}

/**
 * Calculate date range for a given interval.
 * If selectedDateRange has values, returns them unchanged.
 * Otherwise, calculates appropriate start/end dates based on interval.
 *
 * @param selectedDateRange - User-selected date range (may be empty)
 * @param interval - Time interval (1h, 1d, 1w, 1mo)
 * @returns Date range with start/end in YYYY-MM-DD format
 */
export function calculateDateRange(
  selectedDateRange: DateRange,
  interval: TimeInterval,
  now: Date = new Date(),
  timeZone: string = DEFAULT_MARKET_TIMEZONE,
): DateRange {
  // If user has selected custom dates, use them
  if (selectedDateRange.start && selectedDateRange.end) {
    return selectedDateRange;
  }

  // Otherwise, calculate default range based on interval
  // Updated to professional financial analysis standards
  const today = calendarDate(now, timeZone);
  let periodsBack: Date;

  switch (interval) {
    case "1m":
      // 1-minute interval: recent week so weekends/holidays still show bars.
      periodsBack = subtractDays(today, 6);
      break;
    case "2m":
    case "5m":
    case "15m":
    case "30m":
      // Short intraday intervals: stay within the provider's recent window.
      periodsBack = subtractDays(today, 29);
      break;
    case "60m":
      // 60-minute interval: last 2 weeks (professional intraday analysis standard)
      // Captures multi-day swing points for meaningful Fibonacci retracements
      periodsBack = subtractDays(today, 14);
      break;
    case "1w":
      // 1-week interval: last 2 years (professional standard)
      // Provides sufficient context for major support/resistance identification
      periodsBack = subtractDays(today, 2 * 365);
      break;
    case "1mo":
      // 1-month interval: last 5 years (institutional-grade macro analysis)
      // Captures complete market cycles and provides robust stochastic oscillations
      periodsBack = subtractDays(today, MAX_RANGE_DAYS);
      break;
    default:
      // 1-day interval (default): last 6 months
      // Optimal for short-term trading and technical analysis
      periodsBack = subtractDays(today, 6 * 30);
  }

  return {
    start: formatCalendarDate(periodsBack),
    end: formatCalendarDate(today),
  };
}

export function calculateDateRangeForSymbol(
  selectedDateRange: DateRange,
  interval: TimeInterval,
  symbol: string,
  now: Date = new Date(),
): DateRange {
  return calculateDateRange(
    selectedDateRange,
    interval,
    now,
    getMarketTimeZone(symbol),
  );
}

/**
 * Get the default period string for React Query price data endpoint.
 * This is used when no custom date range is selected.
 *
 * @param interval - Time interval
 * @returns Period string for API (e.g., "1mo", "6mo", "1y", "2y")
 */
export function getPeriodForInterval(
  interval: TimeInterval,
): "1d" | "1mo" | "6mo" | "1y" | "2y" {
  switch (interval) {
    case "1m":
      return "1d";
    case "60m":
      return "1mo";
    case "1d":
      return "6mo";
    case "1w":
      return "1y";
    case "1mo":
      return "2y";
    default:
      return "6mo";
  }
}
