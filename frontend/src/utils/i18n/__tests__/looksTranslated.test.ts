/**
 * Unit tests for looksTranslated — the defensive guard that prevents the UI
 * from rendering English content that was incorrectly stored in a `_zh`
 * field on the backend.
 */

import { describe, it, expect } from "vitest";
import { looksTranslated } from "../looksTranslated";

describe("looksTranslated (zh-CN target)", () => {
  it("returns true for an all-Chinese sentence", () => {
    expect(looksTranslated("今天市场情绪明显回暖。", "zh-CN")).toBe(true);
  });

  it("returns false for an all-English sentence", () => {
    expect(
      looksTranslated(
        "Market sentiment improved sharply on better-than-expected earnings.",
        "zh-CN",
      ),
    ).toBe(false);
  });

  it("returns true when CJK ratio exceeds 1% in a mixed string", () => {
    // 4 CJK chars in roughly 60 non-space chars => well above the 1% floor
    // and also clears the 3-char threshold.
    const text =
      "AAPL closed up 1.8%. 行情走强 confirms momentum buyers stepping in.";
    expect(looksTranslated(text, "zh-CN")).toBe(true);
  });

  it("returns false when a single CJK character is buried in a long English doc", () => {
    // 999 non-CJK + 1 CJK = 1000 visible chars; 1/1000 = 0.1% < 1%, and the
    // CJK count is below the 3-character threshold.
    const text = "a".repeat(999) + "中";
    expect(looksTranslated(text, "zh-CN")).toBe(false);
  });

  it("returns true when there are 3+ CJK characters in short text", () => {
    // 3 CJK chars trips the absolute-count threshold even at ~3% ratio.
    expect(looksTranslated("AAPL 买入信号", "zh-CN")).toBe(true);
  });

  it("returns false for empty string", () => {
    expect(looksTranslated("", "zh-CN")).toBe(false);
  });

  it("returns false for whitespace-only string", () => {
    expect(looksTranslated("   \n\t  ", "zh-CN")).toBe(false);
  });

  it("returns false for null or undefined input", () => {
    expect(looksTranslated(null, "zh-CN")).toBe(false);
    expect(looksTranslated(undefined, "zh-CN")).toBe(false);
  });

  it("accepts CJK Extension A characters", () => {
    // U+3400, U+3401, U+3402 — Extension A range.
    expect(looksTranslated("㐀㐁㐂 hello", "zh-CN")).toBe(true);
  });

  it("treats zh-Hant the same as zh-CN (any 'zh' prefix)", () => {
    expect(looksTranslated("All English here.", "zh-Hant")).toBe(false);
    expect(looksTranslated("這是繁體中文。", "zh-Hant")).toBe(true);
  });
});

describe("looksTranslated (non-zh targets)", () => {
  it("returns true for non-zh targets regardless of content (no guard yet)", () => {
    expect(looksTranslated("Anything goes here", "ja-JP")).toBe(true);
    expect(looksTranslated("Plain English", "es")).toBe(true);
  });

  it("still rejects empty input for non-zh targets", () => {
    expect(looksTranslated("", "ja-JP")).toBe(false);
    expect(looksTranslated("   ", "fr")).toBe(false);
  });
});
