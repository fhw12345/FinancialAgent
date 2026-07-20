import { describe, expect, it } from "vitest";
import { parseBackendMessage } from "../messageParser";

describe("parseBackendMessage", () => {
  it("restores route selection without leaking it into analysis data", () => {
    const parsed = parseBackendMessage({
      role: "assistant",
      content: "Analysis",
      timestamp: "2026-07-15T00:00:00Z",
      metadata: {
        raw_data: {
          route_selected: {
            type: "route_selected",
            flow: "v3",
            source: "rule",
            reason_code: "live_data_or_tool_request",
          },
          symbol: "AAPL",
        },
      },
    });

    expect(parsed.route_selected).toEqual({
      type: "route_selected",
      flow: "v3",
      source: "rule",
      reason_code: "live_data_or_tool_request",
    });
    expect(parsed.analysis_data).toEqual({ symbol: "AAPL" });
  });

  it("restores symbol clarification without leaking it into analysis data", () => {
    const parsed = parseBackendMessage({
      role: "assistant",
      content: "Please confirm the stock.",
      timestamp: "2026-07-15T00:00:00Z",
      metadata: {
        raw_data: {
          clarification_required: {
            type: "clarification_required",
            clarification_type: "symbol",
            reason_code: "ambiguous_symbol",
            message: "Please confirm the stock.",
            original_request: "Analyze Alpha",
            candidates: [
              {
                symbol: "AAA",
                name: "Alpha A",
                exchange: "NYSE",
                confidence: 0.9,
              },
              {
                symbol: "AAB",
                name: "Alpha B",
                exchange: "NASDAQ",
                confidence: 0.85,
              },
            ],
          },
          symbol: "AAA",
        },
      },
    });

    expect(parsed.clarification_required?.reason_code).toBe("ambiguous_symbol");
    expect(parsed.clarification_required?.candidates).toHaveLength(2);
    expect(parsed.analysis_data).toEqual({ symbol: "AAA" });
  });

  it("does not restore a clarification card for a terminal failed message", () => {
    const parsed = parseBackendMessage({
      role: "assistant",
      content: "Clarification persistence failed.",
      timestamp: "2026-07-20T00:00:00Z",
      metadata: {
        run_status: "failed",
        raw_data: {
          clarification_required: {
            type: "clarification_required",
            clarification_type: "symbol",
            reason_code: "ambiguous_symbol",
            message: "Please confirm the stock.",
            original_request: "Analyze Alpha",
            candidates: [],
          },
        },
      },
    });

    expect(parsed.clarification_required).toBeUndefined();
    expect(parsed.run_status).toBe("failed");
  });
});
