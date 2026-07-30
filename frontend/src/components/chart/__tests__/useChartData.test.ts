import { describe, expect, it } from "vitest";
import { buildChartSeriesData, VOLUME_COLORS } from "../useChartData";

describe("buildChartSeriesData", () => {
  it("clears price and volume data together", () => {
    expect(buildChartSeriesData([], "candlestick", "UTC")).toEqual({
      priceData: [],
      volumeData: [],
    });
  });

  it("keeps price and volume timestamps aligned after sorting", () => {
    const result = buildChartSeriesData(
      [
        {
          time: "2026-06-02",
          open: 11,
          high: 12,
          low: 9,
          close: 10,
          volume: 200,
        },
        {
          time: "2026-06-01",
          open: 10,
          high: 12,
          low: 9,
          close: 11,
          volume: 100,
        },
      ],
      "candlestick",
      "US/Eastern",
    );

    expect(result.priceData.map((point) => point.time)).toEqual([
      "2026-06-01",
      "2026-06-02",
    ]);
    expect(result.volumeData.map((point) => point.time)).toEqual([
      "2026-06-01",
      "2026-06-02",
    ]);
    expect(result.volumeData.map((point) => point.value)).toEqual([100, 200]);
  });

  it("uses direction and market-session colors", () => {
    const result = buildChartSeriesData(
      [
        {
          time: "2026-06-01T09:00:00",
          open: 10,
          high: 11,
          low: 9,
          close: 11,
          volume: 100,
          market_session: "pre",
        },
        {
          time: "2026-06-01T10:00:00",
          open: 11,
          high: 12,
          low: 10,
          close: 10,
          volume: 200,
          market_session: "regular",
        },
        {
          time: "2026-06-01T17:00:00",
          open: 10,
          high: 12,
          low: 9,
          close: 11,
          volume: 300,
          market_session: "post",
        },
        {
          time: "2026-06-01T18:00:00",
          open: 11,
          high: 12,
          low: 10,
          close: 12,
          volume: 400,
          market_session: "regular",
        },
        {
          time: "2026-06-01T19:00:00",
          open: 12,
          high: 12,
          low: 11,
          close: 11,
          volume: 500,
          market_session: "closed",
        },
      ],
      "line",
      "UTC",
    );

    expect(result.volumeData.map((point) => point.color)).toEqual([
      VOLUME_COLORS.pre,
      VOLUME_COLORS.down,
      VOLUME_COLORS.post,
      VOLUME_COLORS.up,
      VOLUME_COLORS.closed,
    ]);
  });
});
