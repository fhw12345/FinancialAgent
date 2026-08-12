/**
 * useChartData Hook
 *
 * This hook is responsible for converting raw price data into a format
 * that can be consumed by the Lightweight Charts library. It handles timezone
 * conversions and adapts the data structure for line or candlestick charts.
 */

import { useCallback } from "react";
import {
  CandlestickData,
  HistogramData,
  LineData,
  Time,
} from "lightweight-charts";
import { PriceDataPoint } from "../../services/market";

type SupportedTimezone =
  "US/Eastern" | "UTC" | "Asia/Shanghai" | "Europe/London" | "Asia/Tokyo";
type ChartType = "line" | "candlestick";

export const VOLUME_COLORS = {
  up: "rgba(38, 166, 154, 0.55)",
  down: "rgba(239, 83, 80, 0.55)",
  pre: "rgba(59, 130, 246, 0.45)",
  post: "rgba(139, 92, 246, 0.45)",
  closed: "rgba(107, 114, 128, 0.35)",
} as const;

const convertTimezone = (
  easternTimeStr: string,
  targetTimezone: SupportedTimezone,
): Date => {
  const easternDate = new Date(easternTimeStr + "-05:00"); // EST, TODO: handle EDT (-04:00) detection

  if (targetTimezone === "US/Eastern") {
    return easternDate;
  }

  const easternOffset = -5; // EST hours
  const targetOffset =
    targetTimezone === "Asia/Shanghai"
      ? 8
      : targetTimezone === "Asia/Tokyo"
        ? 9
        : 0;
  const offsetDiff = targetOffset - easternOffset;

  return new Date(easternDate.getTime() + offsetDiff * 60 * 60 * 1000);
};

function volumeColor(point: PriceDataPoint): string {
  if (point.market_session === "pre") return VOLUME_COLORS.pre;
  if (point.market_session === "post") return VOLUME_COLORS.post;
  if (point.market_session === "closed") return VOLUME_COLORS.closed;
  return point.close >= point.open ? VOLUME_COLORS.up : VOLUME_COLORS.down;
}

export function buildChartSeriesData(
  data: PriceDataPoint[],
  chartType: ChartType,
  selectedTimezone: SupportedTimezone,
): {
  priceData: Array<LineData | CandlestickData>;
  volumeData: HistogramData[];
} {
  const convertTime = (timeStr: string): Time => {
    if (timeStr.includes("T")) {
      const convertedDate = convertTimezone(timeStr, selectedTimezone);
      return Math.floor(convertedDate.getTime() / 1000) as Time;
    }
    return timeStr as Time;
  };

  const convertedData = data
    .map((point) => ({
      ...point,
      convertedTime: convertTime(point.time),
    }))
    .sort((a, b) => {
      if (
        typeof a.convertedTime === "number" &&
        typeof b.convertedTime === "number"
      ) {
        return a.convertedTime - b.convertedTime;
      }
      return String(a.convertedTime).localeCompare(String(b.convertedTime));
    });

  const priceData =
    chartType === "line"
      ? convertedData.map((point) => ({
          time: point.convertedTime,
          value: point.close,
        }))
      : convertedData.map((point) => ({
          time: point.convertedTime,
          open: point.open,
          high: point.high,
          low: point.low,
          close: point.close,
        }));
  const volumeData = convertedData.map((point) => ({
    time: point.convertedTime,
    value: point.volume,
    color: volumeColor(point),
  }));

  return { priceData, volumeData };
}

export const useChartData = (
  data: PriceDataPoint[],
  chartType: ChartType,
  selectedTimezone: SupportedTimezone,
) => {
  const convertToChartData = useCallback(
    () => buildChartSeriesData(data, chartType, selectedTimezone),
    [data, chartType, selectedTimezone],
  );

  return { convertToChartData };
};
