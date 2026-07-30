/**
 * useChart Hook
 *
 * This hook encapsulates the logic for initializing and managing the TradingView Lightweight Chart.
 * It handles chart creation, series management, data updates, event handling, and resizing.
 */

import { useEffect, useRef, useCallback } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  MouseEventParams,
  CandlestickData,
  HistogramData,
  LineData,
  IPriceLine,
} from "lightweight-charts";

type ChartType = "line" | "candlestick";

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

interface FibonacciAnalysisData {
  fibonacci_levels: FibonacciLevel[];
  pressure_zone: PressureZone | null;
  raw_data?: any;
}

let nextChartInstanceId = 0;

export const useChart = (
  chartContainerRef: React.RefObject<HTMLDivElement>,
  chartType: ChartType,
  onDateRangeSelect?: (startDate: string, endDate: string) => void,
  setTooltip?: (tooltip: any) => void,
  interval?: string,
  fibonacciAnalysis?: FibonacciAnalysisData | null,
) => {
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line" | "Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const fibonacciLinesRef = useRef<IPriceLine[]>([]);
  const onDateRangeSelectRef = useRef(onDateRangeSelect);
  const setTooltipRef = useRef(setTooltip);
  const lastTooltipRef = useRef<any>(null);

  // Update refs when props change
  useEffect(() => {
    onDateRangeSelectRef.current = onDateRangeSelect;
    setTooltipRef.current = setTooltip;
  }, [onDateRangeSelect, setTooltip]);

  useEffect(() => {
    const chartContainer = chartContainerRef.current;
    if (!chartContainer) return;

    const chart = createChart(chartContainer, {
      layout: {
        background: { color: "#ffffff" },
        textColor: "#333",
      },
      width: chartContainer.clientWidth,
      height: 400,
      rightPriceScale: {
        borderColor: "#cccccc",
        scaleMargins: {
          top: 0.05,
          bottom: 0.25,
        },
      },
      timeScale: {
        borderColor: "#cccccc",
        timeVisible: true,
        secondsVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
      },
      grid: {
        vertLines: { color: "#f0f0f0" },
        horzLines: { color: "#f0f0f0" },
      },
      crosshair: {
        mode: 1,
        vertLine: { labelVisible: false },
        horzLine: { labelVisible: false },
      },
    });

    chartRef.current = chart;

    if (chartType === "line") {
      seriesRef.current = chart.addLineSeries({
        color: "#2962FF",
        lineWidth: 2,
      });
    } else {
      seriesRef.current = chart.addCandlestickSeries({
        upColor: "#26a69a",
        downColor: "#ef5350",
        borderVisible: false,
        wickUpColor: "#26a69a",
        wickDownColor: "#ef5350",
      });
    }
    volumeSeriesRef.current = chart.addHistogramSeries({
      priceScaleId: "volume",
      priceFormat: { type: "volume" },
      priceLineVisible: false,
      lastValueVisible: false,
    });
    chart.priceScale("volume").applyOptions({
      visible: false,
      scaleMargins: {
        top: 0.78,
        bottom: 0,
      },
    });
    chartContainer.dataset.chartInstance = String(++nextChartInstanceId);
    chartContainer.dataset.volumeOverlay = "ready";
    chartContainer.dataset.volumeBars = "0";

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      delete chartContainer.dataset.volumeOverlay;
      delete chartContainer.dataset.volumeBars;
      delete chartContainer.dataset.chartInstance;
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [chartType, chartContainerRef]);

  useEffect(() => {
    if (!chartRef.current || !seriesRef.current) return;

    let dateSelection = {
      startDate: null as string | null,
      endDate: null as string | null,
      clickCount: 0,
    };

    const handleClick = (param: MouseEventParams) => {
      if (!param.time) return;

      let date: Date;
      if (typeof param.time === "number") {
        date = new Date(param.time * 1000);
      } else {
        date = new Date(param.time as string);
      }
      const timeStr = date.toISOString().split("T")[0];

      if (dateSelection.clickCount === 0) {
        dateSelection.startDate = timeStr;
        dateSelection.clickCount = 1;
      } else {
        const startDate = dateSelection.startDate ?? "";
        const endDate = timeStr;

        const finalStartDate = startDate <= endDate ? startDate : endDate;
        const finalEndDate = startDate <= endDate ? endDate : startDate;

        onDateRangeSelectRef.current?.(finalStartDate, finalEndDate);
        dateSelection = { startDate: null, endDate: null, clickCount: 0 };
      }
    };

    const handleCrosshairMove = (param: MouseEventParams) => {
      if (
        !param.point ||
        !param.time ||
        !seriesRef.current ||
        !setTooltipRef.current
      ) {
        if (lastTooltipRef.current?.visible !== false) {
          lastTooltipRef.current = { visible: false };
          setTooltipRef.current?.({ visible: false });
        }
        return;
      }

      const data = param.seriesData.get(seriesRef.current);
      if (!data) {
        if (lastTooltipRef.current?.visible !== false) {
          lastTooltipRef.current = { visible: false };
          setTooltipRef.current?.({ visible: false });
        }
        return;
      }

      const price =
        "value" in data ? data.value : "close" in data ? data.close : 0;
      const isGreen =
        "close" in data && "open" in data ? data.close >= data.open : undefined;

      // Extract OHLC data for candlestick charts
      const open = "open" in data ? data.open : undefined;
      const high = "high" in data ? data.high : undefined;
      const low = "low" in data ? data.low : undefined;
      const close = "close" in data ? data.close : undefined;

      const volumeData = volumeSeriesRef.current
        ? param.seriesData.get(volumeSeriesRef.current)
        : undefined;
      const volume =
        volumeData && "value" in volumeData ? volumeData.value : undefined;

      let timeStr: string;
      if (typeof param.time === "number") {
        const date = new Date(param.time * 1000);
        timeStr =
          interval && (interval.includes("m") || interval.includes("h"))
            ? `${date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}, ${date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false })}`
            : date.toLocaleDateString("en-US", {
                year: "numeric",
                month: "short",
                day: "numeric",
              });
      } else {
        timeStr = new Date(param.time as string).toLocaleDateString("en-US", {
          year: "numeric",
          month: "short",
          day: "numeric",
        });
      }

      const newTooltip = {
        visible: true,
        x: param.point.x,
        y: param.point.y,
        time: timeStr,
        price: price,
        open,
        high,
        low,
        close,
        volume,
        isGreen,
      };

      // Only update if tooltip data has actually changed
      if (
        !lastTooltipRef.current ||
        lastTooltipRef.current.x !== newTooltip.x ||
        lastTooltipRef.current.y !== newTooltip.y ||
        lastTooltipRef.current.price !== newTooltip.price ||
        lastTooltipRef.current.time !== newTooltip.time
      ) {
        lastTooltipRef.current = newTooltip;
        setTooltipRef.current?.(newTooltip);
      }
    };

    chartRef.current.subscribeClick(handleClick);
    chartRef.current.subscribeCrosshairMove(handleCrosshairMove);

    return () => {
      if (chartRef.current) {
        chartRef.current.unsubscribeClick(handleClick);
        chartRef.current.unsubscribeCrosshairMove(handleCrosshairMove);
      }
    };
  }, [chartType, interval]);

  // Effect to handle Fibonacci analysis updates
  useEffect(() => {
    if (!chartRef.current || !seriesRef.current) return;

    // Clear existing Fibonacci lines
    fibonacciLinesRef.current.forEach((line) => {
      seriesRef.current?.removePriceLine(line);
    });
    fibonacciLinesRef.current = [];

    console.log("📈 useChart: Rendering Fibonacci overlay:", {
      hasFibonacciAnalysis: !!fibonacciAnalysis,
      hasRawData: !!fibonacciAnalysis?.raw_data,
      topTrendsCount: fibonacciAnalysis?.raw_data?.top_trends?.length || 0,
    });

    if (!fibonacciAnalysis) return;

    // Get the top trends from raw data
    const topTrends = fibonacciAnalysis.raw_data?.top_trends || [];
    console.log("🎯 Top trends for overlay:", topTrends);

    // For the biggest trend (#1): show only 61.8% line
    if (topTrends.length > 0) {
      const mainTrend = topTrends[0];

      // Calculate 61.8% level for the biggest trend
      const high = mainTrend["high"];
      const low = mainTrend["low"];
      const isUptrend = mainTrend["type"].includes("Uptrend");

      // Calculate 61.8% retracement level
      const level618Price = isUptrend
        ? high - (high - low) * 0.618 // Retracement from high in uptrend
        : low + (high - low) * 0.618; // Extension from low in downtrend

      // Determine arrow direction
      const arrow = isUptrend ? "↑" : "↓";

      // Add single 61.8% line for biggest trend
      const line618 = seriesRef.current.createPriceLine({
        price: level618Price,
        color: "#FF6B6B",
        lineWidth: 1,
        lineStyle: 0,
        axisLabelVisible: true,
        title: `1${arrow}`,
      });
      fibonacciLinesRef.current.push(line618);
    }

    // For trends #2 and #3: show only 61.8% level calculated for each trend
    topTrends.slice(1, 3).forEach((trend: any, index: number) => {
      const trendNumber = index + 2; // 2 or 3

      // Calculate 61.8% retracement level for this specific trend
      const high = trend["high"]; // Use correct field name from backend
      const low = trend["low"]; // Use correct field name from backend
      const level618Price = trend["type"].includes("Uptrend")
        ? high - (high - low) * 0.618 // Retracement from high in uptrend
        : low + (high - low) * 0.618; // Extension from low in downtrend

      if (seriesRef.current) {
        const arrow = trend["type"].includes("Uptrend") ? "↑" : "↓";
        // Different colors for trends 2 and 3
        const color = trendNumber === 2 ? "#4CAF50" : "#FF9800"; // Green for trend 2, Orange for trend 3
        const line = seriesRef.current.createPriceLine({
          price: level618Price,
          color: color,
          lineWidth: 1,
          lineStyle: 1, // Dashed
          axisLabelVisible: true,
          title: `${trendNumber}${arrow}`,
        });
        fibonacciLinesRef.current.push(line);
      }
    });
  }, [chartType, fibonacciAnalysis]);

  const setChartData = useCallback(
    (data: (LineData | CandlestickData)[], volumeData: HistogramData[]) => {
      if (seriesRef.current && volumeSeriesRef.current) {
        seriesRef.current.setData(data);
        volumeSeriesRef.current.setData(volumeData);
        if (chartContainerRef.current) {
          chartContainerRef.current.dataset.volumeBars = String(
            volumeData.length,
          );
        }
        chartRef.current?.timeScale().fitContent();
      }
    },
    [chartContainerRef],
  );

  return { chartRef, seriesRef, volumeSeriesRef, setChartData };
};
