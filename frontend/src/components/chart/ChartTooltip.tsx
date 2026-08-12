/**
 * ChartTooltip Component
 *
 * Displays price, time, and volume information when hovering over the chart.
 */

import React from "react";
import { useTranslation } from "react-i18next";

export interface TooltipData {
  visible: boolean;
  x: number;
  y: number;
  time: string;
  price: number; // For backward compatibility (close price)
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
  isGreen?: boolean;
}

interface ChartTooltipProps {
  tooltipData: TooltipData;
  chartContainerRef: React.RefObject<HTMLDivElement>;
}

const formatPrice = (price: number) => {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price);
};

const formatVolume = (volume: number) => {
  if (volume >= 1_000_000) {
    return `${(volume / 1_000_000).toFixed(1)}M`;
  } else if (volume >= 1_000) {
    return `${(volume / 1_000).toFixed(1)}K`;
  }
  return volume.toString();
};

export const ChartTooltip: React.FC<ChartTooltipProps> = ({
  tooltipData,
  chartContainerRef,
}) => {
  const { t } = useTranslation(["market", "common"]);

  if (!tooltipData.visible) {
    return null;
  }

  // Show OHLC if available, otherwise show single price
  const hasOHLC =
    tooltipData.open !== undefined &&
    tooltipData.high !== undefined &&
    tooltipData.low !== undefined &&
    tooltipData.close !== undefined;

  const directionArrow = tooltipData.isGreen ? "↑" : "↓";
  const colorClass = tooltipData.isGreen
    ? "text-green-400"
    : tooltipData.isGreen === false
      ? "text-red-400"
      : "text-white";

  return (
    <div
      className="absolute z-10 bg-black bg-opacity-90 text-white text-xs rounded px-3 py-2 pointer-events-none font-mono shadow-lg"
      style={{
        left: `${Math.min(tooltipData.x + 10, (chartContainerRef.current?.clientWidth || 0) - 180)}px`,
        top: `${Math.max(tooltipData.y - 10, 0)}px`,
        minWidth: "160px",
      }}
    >
      <div className="font-semibold mb-1">{tooltipData.time}</div>

      {hasOHLC ? (
        // Show OHLC format
        <div className="space-y-0.5">
          <div className="flex justify-between">
            <span className="text-gray-400">{t("market:quote.open")}:</span>
            <span>{formatPrice(tooltipData.open ?? 0)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">{t("market:quote.high")}:</span>
            <span>{formatPrice(tooltipData.high ?? 0)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">{t("market:quote.low")}:</span>
            <span>{formatPrice(tooltipData.low ?? 0)}</span>
          </div>
          <div className={`flex justify-between font-semibold ${colorClass}`}>
            <span className="text-gray-400 font-normal">
              {t("market:quote.close")}:
            </span>
            <span>
              {formatPrice(tooltipData.close ?? 0)} {directionArrow}
            </span>
          </div>
        </div>
      ) : (
        // Fallback to single price display
        <div className={colorClass}>{formatPrice(tooltipData.price)}</div>
      )}

      {tooltipData.volume !== undefined && (
        <div className="text-gray-400 mt-1 pt-1 border-t border-gray-700">
          {t("market:quote.volume")}: {formatVolume(tooltipData.volume)}
        </div>
      )}
    </div>
  );
};
