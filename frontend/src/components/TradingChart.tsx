/**
 * Interactive Trading Chart Component
 *
 * This component orchestrates the various parts of the trading chart,
 * including the header, the chart itself, and the tooltip. It manages
 * state and passes data and callbacks to its children.
 */

import React, { useState, useRef } from "react";
import { useTranslation } from "react-i18next";
import { PriceDataPoint, TimeInterval } from "../services/market";
import { ChartHeader } from "./chart/ChartHeader";
import { ChartTooltip } from "./chart/ChartTooltip";
import { useChart } from "./chart/useChart";
import { useChartData } from "./chart/useChartData";

type SupportedTimezone =
  "US/Eastern" | "UTC" | "Asia/Shanghai" | "Europe/London" | "Asia/Tokyo";

interface FibonacciLevel {
  level: number;
  price: number;
  percentage: string;
  is_key_level: boolean;
}

interface PressureZone {
  center_price: number;
  upper_bound: number;
  lower_bound: number;
  zone_width: number;
}

interface TopTrend {
  rank: number;
  type: string;
  period: string;
  magnitude: number;
  high: number;
  low: number;
}

interface FibonacciAnalysisData {
  fibonacci_levels: FibonacciLevel[];
  pressure_zone: PressureZone | null;
  raw_data?: {
    top_trends?: TopTrend[];
    pressure_zones?: Array<PressureZone & { trend_type: string }>;
  };
}

interface TradingChartProps {
  symbol: string;
  data: PriceDataPoint[];
  chartType?: "line" | "candlestick";
  interval: TimeInterval;
  onIntervalChange?: (interval: TimeInterval) => void;
  onDateRangeSelect?: (startDate: string, endDate: string) => void;
  fibonacciAnalysis?: FibonacciAnalysisData | null;
  className?: string;
}

export const TradingChart: React.FC<TradingChartProps> = ({
  symbol,
  data,
  chartType = "candlestick",
  interval,
  onIntervalChange,
  onDateRangeSelect,
  fibonacciAnalysis,
  className = "",
}) => {
  const { t } = useTranslation("market");
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const [selectedTimezone, setSelectedTimezone] =
    useState<SupportedTimezone>("US/Eastern");
  const [tooltip, setTooltip] = useState({
    visible: false,
    x: 0,
    y: 0,
    time: "",
    price: 0,
  });

  const handleDateRangeSelect = (startDate: string, endDate: string) => {
    onDateRangeSelect?.(startDate, endDate);
  };

  const { setChartData } = useChart(
    chartContainerRef,
    chartType,
    handleDateRangeSelect,
    setTooltip,
    interval,
    fibonacciAnalysis,
  );
  const { convertToChartData } = useChartData(
    data,
    chartType,
    selectedTimezone,
  );

  React.useEffect(() => {
    const { priceData, volumeData } = convertToChartData();
    setChartData(priceData, volumeData);
  }, [data, convertToChartData, setChartData]);

  return (
    <div className={`relative ${className}`}>
      <ChartHeader
        symbol={symbol}
        interval={interval}
        selectedTimezone={selectedTimezone}
        onIntervalChange={onIntervalChange}
        onTimezoneChange={setSelectedTimezone}
      />
      <div className="relative">
        <div
          ref={chartContainerRef}
          className="w-full h-96 border rounded-lg"
          data-testid="trading-chart-container"
        />
        <span className="sr-only" data-testid="volume-overlay-summary">
          {t("chart.volumeOverlay", { count: data.length })}
        </span>
        <ChartTooltip
          tooltipData={tooltip}
          chartContainerRef={chartContainerRef}
        />
      </div>
    </div>
  );
};
