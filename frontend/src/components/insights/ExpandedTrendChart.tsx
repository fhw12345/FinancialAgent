/**
 * ExpandedTrendChart component for detailed trend visualization.
 * Shows full line chart with axis labels, tooltips, and score history.
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TrendDataPoint } from "../../types/insights";

interface ExpandedTrendChartProps {
  /** Trend data points (newest first) */
  data: TrendDataPoint[];
  /** Title for the chart */
  title?: string;
  /** Height of the chart in pixels */
  height?: number;
  /** Whether to use dark theme (for composite card) */
  darkTheme?: boolean;
}

/**
 * Expanded line chart with axes, grid, and interactive tooltip.
 */
export function ExpandedTrendChart({
  data,
  title,
  height = 160,
  darkTheme = false,
}: ExpandedTrendChartProps) {
  const { t } = useTranslation(["insights"]);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  // Chart dimensions - wider aspect ratio for better visibility
  const width = 600; // Wider viewBox for full-width display
  const padding = { top: 16, right: 16, bottom: 28, left: 36 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  // Process data (reverse to oldest-first for left-to-right)
  const chartData = useMemo(() => [...data].reverse(), [data]);

  // Calculate scales
  const { points, yMin, yMax, yTicks } = useMemo(() => {
    if (chartData.length === 0) {
      return { points: [], yMin: 0, yMax: 100, yTicks: [0, 25, 50, 75, 100] };
    }

    const scores = chartData.map((d) => d.score);
    const dataMin = Math.min(...scores);
    const dataMax = Math.max(...scores);

    // Add padding to Y range
    const range = dataMax - dataMin || 10;
    const yMinVal = Math.max(0, Math.floor((dataMin - range * 0.1) / 10) * 10);
    const yMaxVal = Math.min(100, Math.ceil((dataMax + range * 0.1) / 10) * 10);

    // Generate Y axis ticks
    const tickCount = 5;
    const tickStep = (yMaxVal - yMinVal) / (tickCount - 1);
    const ticks = Array.from({ length: tickCount }, (_, i) =>
      Math.round(yMinVal + i * tickStep)
    );

    // Calculate points
    const pts = chartData.map((d, i) => ({
      x: padding.left + (i / Math.max(1, chartData.length - 1)) * chartWidth,
      y:
        padding.top +
        chartHeight -
        ((d.score - yMinVal) / (yMaxVal - yMinVal || 1)) * chartHeight,
      ...d,
    }));

    return { points: pts, yMin: yMinVal, yMax: yMaxVal, yTicks: ticks };
  }, [chartData, chartWidth, chartHeight]);

  // No data state
  if (chartData.length === 0) {
    return (
      <div
        className={`flex items-center justify-center ${darkTheme ? "text-blue-200" : "text-gray-400"}`}
        style={{ height }}
      >
        {t("insights:trend.no_data")}
      </div>
    );
  }

  // Build SVG path
  const pathD = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(" ");

  // Determine trend direction
  const isUptrend = chartData[chartData.length - 1].score > chartData[0].score;
  const isFlat =
    Math.abs(chartData[chartData.length - 1].score - chartData[0].score) < 1;

  // Colors
  const lineColor = isFlat ? "#6b7280" : isUptrend ? "#22c55e" : "#ef4444";
  const gridColor = darkTheme ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.08)";
  const textColor = darkTheme ? "rgba(255,255,255,0.6)" : "#6b7280";
  const tooltipBg = darkTheme ? "rgba(0,0,0,0.8)" : "white";
  const tooltipText = darkTheme ? "white" : "#1f2937";

  // Format date for display
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  };

  // Get X axis labels (first, middle, last)
  const xLabels = (() => {
    if (chartData.length < 2) return [];
    const labels = [];
    labels.push({ x: points[0].x, label: formatDate(chartData[0].date) });
    if (chartData.length > 2) {
      const midIdx = Math.floor(chartData.length / 2);
      labels.push({
        x: points[midIdx].x,
        label: formatDate(chartData[midIdx].date),
      });
    }
    labels.push({
      x: points[points.length - 1].x,
      label: formatDate(chartData[chartData.length - 1].date),
    });
    return labels;
  })();

  return (
    <div className="w-full">
      {title && (
        <div
          className={`text-sm font-medium mb-2 ${darkTheme ? "text-blue-100" : "text-gray-700"}`}
        >
          {title}
        </div>
      )}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        style={{ overflow: "visible" }}
        preserveAspectRatio="xMidYMid meet"
        aria-label={`Trend chart showing ${isUptrend ? "upward" : isFlat ? "flat" : "downward"} trend`}
      >
        {/* Grid lines */}
        {yTicks.map((tick) => {
          const y =
            padding.top +
            chartHeight -
            ((tick - yMin) / (yMax - yMin || 1)) * chartHeight;
          return (
            <g key={tick}>
              <line
                x1={padding.left}
                y1={y}
                x2={width - padding.right}
                y2={y}
                stroke={gridColor}
                strokeWidth="1"
              />
              <text
                x={padding.left - 8}
                y={y + 4}
                fill={textColor}
                fontSize="10"
                textAnchor="end"
              >
                {tick}
              </text>
            </g>
          );
        })}

        {/* X axis labels */}
        {xLabels.map((label, i) => (
          <text
            key={i}
            x={label.x}
            y={height - 8}
            fill={textColor}
            fontSize="10"
            textAnchor="middle"
          >
            {label.label}
          </text>
        ))}

        {/* Area fill under line */}
        <path
          d={`${pathD} L ${points[points.length - 1].x} ${padding.top + chartHeight} L ${points[0].x} ${padding.top + chartHeight} Z`}
          fill={lineColor}
          fillOpacity="0.1"
        />

        {/* Trend line */}
        <path
          d={pathD}
          fill="none"
          stroke={lineColor}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Data points */}
        {points.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={hoveredIndex === i ? 5 : 3}
            fill={lineColor}
            stroke={darkTheme ? "#1e293b" : "white"}
            strokeWidth="2"
            className="cursor-pointer transition-all duration-150"
            onMouseEnter={() => setHoveredIndex(i)}
            onMouseLeave={() => setHoveredIndex(null)}
          />
        ))}

        {/* Tooltip with smart positioning */}
        {hoveredIndex !== null && points[hoveredIndex] && (() => {
          const point = points[hoveredIndex];
          // Smart positioning: show below if point is in top 40% of chart area
          const chartTop = padding.top;
          const chartBottom = height - padding.bottom;
          const chartAreaHeight = chartBottom - chartTop;
          const isInTopArea = point.y < chartTop + chartAreaHeight * 0.4;

          // Tooltip dimensions
          const tooltipWidth = 90;
          const tooltipHeight = 32;
          const tooltipOffset = 12; // Gap between point and tooltip

          // Calculate tooltip position
          const tooltipX = point.x - tooltipWidth / 2;
          const tooltipY = isInTopArea
            ? point.y + tooltipOffset // Below point
            : point.y - tooltipHeight - tooltipOffset; // Above point

          // Text Y positions (relative to tooltip)
          const scoreTextY = tooltipY + 13;
          const dateTextY = tooltipY + 25;

          return (
            <g>
              <rect
                x={tooltipX}
                y={tooltipY}
                width={tooltipWidth}
                height={tooltipHeight}
                rx="4"
                fill={tooltipBg}
                filter="drop-shadow(0 2px 4px rgba(0,0,0,0.15))"
              />
              <text
                x={point.x}
                y={scoreTextY}
                fill={tooltipText}
                fontSize="11"
                fontWeight="600"
                textAnchor="middle"
              >
                Score: {point.score.toFixed(1)}
              </text>
              <text
                x={point.x}
                y={dateTextY}
                fill={textColor}
                fontSize="10"
                textAnchor="middle"
              >
                {formatDate(chartData[hoveredIndex].date)}
              </text>
            </g>
          );
        })()}
      </svg>
    </div>
  );
}

/** Skeleton for ExpandedTrendChart */
export function ExpandedTrendChartSkeleton({
  height = 160,
  darkTheme = false,
}: {
  height?: number;
  darkTheme?: boolean;
}) {
  return (
    <div
      className={`rounded-lg animate-pulse ${darkTheme ? "bg-white/10" : "bg-gray-100"}`}
      style={{ height }}
    />
  );
}

export default ExpandedTrendChart;
