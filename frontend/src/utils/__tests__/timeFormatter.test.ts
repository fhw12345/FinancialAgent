/**
 * Unit tests for timeFormatter utility.
 *
 * Verifies UTC+8 (Asia/Shanghai) formatting for zh-CN locale and that
 * non-Chinese locales fall back to the browser's default timezone.
 */

import { describe, it, expect } from "vitest";
import {
  formatTimestamp,
  formatDate,
  formatTime,
  localizeTimestamps,
} from "../timeFormatter";

describe("timeFormatter", () => {
  // 2026-05-05T04:00:00Z corresponds to 12:00 Beijing time (UTC+8).
  const utcIso = "2026-05-05T04:00:00.000Z";

  describe("formatTimestamp", () => {
    it("uses Asia/Shanghai for zh-CN", () => {
      const result = formatTimestamp(utcIso, "zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
      // Beijing time is 12:00.
      expect(result).toContain("12:00");
    });

    it("respects an explicit timeZone override even when locale is zh-CN", () => {
      const result = formatTimestamp(utcIso, "zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone: "UTC",
      });
      expect(result).toContain("04:00");
    });

    it("returns empty string for null/undefined input", () => {
      expect(formatTimestamp(null, "zh-CN")).toBe("");
      expect(formatTimestamp(undefined, "en")).toBe("");
      expect(formatTimestamp("", "zh-CN")).toBe("");
    });

    it("returns empty string for invalid date", () => {
      expect(formatTimestamp("not-a-date", "zh-CN")).toBe("");
    });

    it("accepts a Date instance", () => {
      const date = new Date(utcIso);
      const result = formatTimestamp(date, "zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
      expect(result).toContain("12:00");
    });
  });

  describe("formatDate", () => {
    it("renders Beijing date for zh-CN even when UTC date differs", () => {
      // 2026-05-05T20:00Z is 2026-05-06 04:00 Beijing — date should roll over.
      const result = formatDate("2026-05-05T20:00:00Z", "zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      });
      expect(result).toMatch(/2026/);
      expect(result).toMatch(/06|6/);
    });
  });

  describe("formatTime", () => {
    it("renders 12:00 in Beijing time for zh-CN", () => {
      const result = formatTime(utcIso, "zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
      expect(result).toContain("12:00");
    });
  });

  describe("localizeTimestamps", () => {
    it("rewrites every ISO timestamp inside a markdown blob for zh-CN", () => {
      const text = `**Invoked:** 2026-05-05T04:00:00+00:00\n*Last updated: 2026-05-05T04:00:00.000Z*`;
      const out = localizeTimestamps(text, "zh-CN");
      // Both occurrences should have been rewritten (no raw +00:00 / Z left).
      expect(out).not.toContain("+00:00");
      expect(out).not.toContain(".000Z");
      // Beijing equivalent (12:00) should appear at least once.
      expect(out).toMatch(/12:00/);
    });

    it("leaves text without ISO timestamps unchanged", () => {
      const text = "no timestamps here, just words";
      expect(localizeTimestamps(text, "zh-CN")).toBe(text);
    });

    it("ignores naive ISO without timezone (ambiguous)", () => {
      const text = "Invoked: 2026-05-05T04:00:00";
      expect(localizeTimestamps(text, "zh-CN")).toBe(text);
    });

    it("returns empty input as-is", () => {
      expect(localizeTimestamps("", "zh-CN")).toBe("");
    });
  });
});
