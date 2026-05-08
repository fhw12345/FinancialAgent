/**
 * W3.7 unit tests — ResearchPanel footnote extraction helpers.
 *
 * Pure-function tests of `extractFootnotes` and `parseSourceId`. The
 * full DOM rendering (chip + bottom list) is covered by W3.12 e2e
 * (`e2e_source_footnote.py`); the unit tests here pin the regex and
 * the indexing semantics so the e2e doesn't have to debug regex
 * issues at the playwright layer.
 */
import { describe, it, expect } from "vitest";

import {
  extractFootnotes,
  parseSourceId,
  SOURCE_ID_PATTERN,
} from "../ResearchPanel";

describe("SOURCE_ID_PATTERN", () => {
  it("matches the W3.2-W3.5 wrapper output shapes", () => {
    const samples = [
      "[FH-Q-AAPL-2026-05-09]",
      "[AV-OV-NVDA-2025-09-30]",
      "[YF-CF-MSFT-2025-12-31]",
      "[FH-N-AMZN-2026-05-08]",
      "[FH-INS-TSLA-2026-05-07]",
    ];
    for (const s of samples) {
      SOURCE_ID_PATTERN.lastIndex = 0;
      expect(SOURCE_ID_PATTERN.exec(s)).not.toBeNull();
    }
  });

  it("ignores text that merely looks bracketed", () => {
    const cases = [
      "[1]", // existing footnote-style ref shouldn't match
      "[hello]",
      "[FH-aapl-2026-05-09]", // lowercase symbol -> backend never emits this
      "[FH-Q-AAPL-2026/05/09]", // wrong date separator
    ];
    for (const c of cases) {
      SOURCE_ID_PATTERN.lastIndex = 0;
      expect(SOURCE_ID_PATTERN.exec(c)).toBeNull();
    }
  });
});

describe("extractFootnotes", () => {
  it("returns empty registry when no bullet contains a token", () => {
    const out = extractFootnotes([
      "Pure judgement bullet, no numbers",
      "Another qualitative call",
    ]);
    expect(out.ids).toEqual([]);
    expect(out.bullets).toHaveLength(2);
    // Both bullets become a single text segment.
    expect(out.bullets[0].segments).toEqual([
      { kind: "text", value: "Pure judgement bullet, no numbers" },
    ]);
  });

  it("extracts a single token from a bullet and assigns index 1", () => {
    const out = extractFootnotes([
      "Q4 capex raised 18% YoY [FH-N-EXMP-2026-02-08]",
    ]);
    expect(out.ids).toEqual(["FH-N-EXMP-2026-02-08"]);
    expect(out.bullets[0].segments).toEqual([
      { kind: "text", value: "Q4 capex raised 18% YoY " },
      { kind: "ref", id: "FH-N-EXMP-2026-02-08", index: 1 },
    ]);
  });

  it("assigns sequential indices across bullets in citation order", () => {
    const out = extractFootnotes([
      "Datacenter capex up [FH-N-EXMP-2026-02-08]",
      "Margin expanding [AV-OV-EXMP-2025-12-31]",
      "Buyback authorized [FH-N-EXMP-2026-01-22]",
    ]);
    expect(out.ids).toEqual([
      "FH-N-EXMP-2026-02-08",
      "AV-OV-EXMP-2025-12-31",
      "FH-N-EXMP-2026-01-22",
    ]);
    expect(out.bullets[0].segments[1]).toMatchObject({ index: 1 });
    expect(out.bullets[1].segments[1]).toMatchObject({ index: 2 });
    expect(out.bullets[2].segments[1]).toMatchObject({ index: 3 });
  });

  it("dedupes a repeated source-ID across bullets", () => {
    const out = extractFootnotes([
      "Capex guide [FH-N-EXMP-2026-02-08] from Q4",
      "Same earnings call [FH-N-EXMP-2026-02-08] flagged margins",
    ]);
    expect(out.ids).toEqual(["FH-N-EXMP-2026-02-08"]);
    // Both bullets cite index 1, not 1 and 2.
    expect(out.bullets[0].segments[1]).toMatchObject({ index: 1 });
    expect(out.bullets[1].segments[1]).toMatchObject({ index: 1 });
  });

  it("handles two tokens in one bullet", () => {
    const out = extractFootnotes([
      "P/E [AV-OV-EXMP-2025-12-31] vs cohort median per quote [FH-Q-EXMP-2026-05-09]",
    ]);
    expect(out.ids).toEqual([
      "AV-OV-EXMP-2025-12-31",
      "FH-Q-EXMP-2026-05-09",
    ]);
    expect(out.bullets[0].segments).toHaveLength(4); // text, ref, text, ref
  });

  it("preserves trailing text after the last token", () => {
    const out = extractFootnotes([
      "[FH-Q-AAPL-2026-05-09] is the latest quote",
    ]);
    expect(out.bullets[0].segments).toEqual([
      { kind: "ref", id: "FH-Q-AAPL-2026-05-09", index: 1 },
      { kind: "text", value: " is the latest quote" },
    ]);
  });

  it("skips empty thesis array", () => {
    const out = extractFootnotes([]);
    expect(out.ids).toEqual([]);
    expect(out.bullets).toEqual([]);
  });
});

describe("parseSourceId", () => {
  it("parses each W3.x prefix family", () => {
    expect(parseSourceId("FH-Q-AAPL-2026-05-09")).toEqual({
      provider: "FH",
      field: "Q",
      symbol: "AAPL",
      asof: "2026-05-09",
    });
    expect(parseSourceId("AV-OV-NVDA-2025-09-30")).toEqual({
      provider: "AV",
      field: "OV",
      symbol: "NVDA",
      asof: "2025-09-30",
    });
    expect(parseSourceId("YF-CF-MSFT-2025-12-31")).toEqual({
      provider: "YF",
      field: "CF",
      symbol: "MSFT",
      asof: "2025-12-31",
    });
    expect(parseSourceId("FH-INS-TSLA-2026-05-07")).toEqual({
      provider: "FH",
      field: "INS",
      symbol: "TSLA",
      asof: "2026-05-07",
    });
  });

  it("preserves dotted symbols like BRK.B", () => {
    // Backend's _news_source_id uppercases symbol verbatim, so a
    // hyphenated dotted ticker stays as one segment with a dot.
    expect(parseSourceId("FH-Q-BRK.B-2026-05-09")).toEqual({
      provider: "FH",
      field: "Q",
      symbol: "BRK.B",
      asof: "2026-05-09",
    });
  });

  it("returns null on shapes the backend wouldn't emit", () => {
    expect(parseSourceId("garbage")).toBeNull();
    expect(parseSourceId("FH-Q")).toBeNull();
    expect(parseSourceId("FH-Q-AAPL-bad-date")).toBeNull();
    expect(parseSourceId("FH-Q-AAPL-2026-05")).toBeNull(); // partial date
  });
});
