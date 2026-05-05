/**
 * Market Movers Component
 *
 * Displays today's top market performers in three categories:
 * - Top Gainers (highest price increase)
 * - Top Losers (largest price decrease)
 * - Most Active (highest trading volume)
 *
 * Features:
 * - Color-coded price changes
 * - Tab navigation between categories
 * - Clickable tickers
 * - Volume formatting
 * - Auto-refresh capability
 */

import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  TrendingUp,
  TrendingDown,
  Activity,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import { alphaVantageApi } from "../services/alphaVantageApi";
import type { MarketMover } from "../types/alphaVantage";
import { parseNumericString, formatLargeNumber } from "../types/alphaVantage";
import { formatTime } from "../utils/timeFormatter";

interface MarketMoversProps {
  /** Optional callback when ticker is clicked */
  onTickerClick?: (ticker: string) => void;

  /** Number of items to display per category (default: 5) */
  limit?: number;

  /** Optional className */
  className?: string;
}

type CategoryTab = "gainers" | "losers" | "active";

export const MarketMovers: React.FC<MarketMoversProps> = ({
  onTickerClick,
  limit = 5,
  className = "",
}) => {
  const { t, i18n } = useTranslation(["market", "common"]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [gainers, setGainers] = useState<MarketMover[]>([]);
  const [losers, setLosers] = useState<MarketMover[]>([]);
  const [active, setActive] = useState<MarketMover[]>([]);
  const [activeTab, setActiveTab] = useState<CategoryTab>("gainers");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchMarketMovers = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await alphaVantageApi.getMarketMovers();

      // Fetch 10 items for scrolling
      setGainers(response.top_gainers.slice(0, 10));
      setLosers(response.top_losers.slice(0, 10));
      setActive(response.most_actively_traded.slice(0, 10));
      setLastUpdated(new Date());
    } catch (err: any) {
      console.error("Failed to fetch market movers:", err);
      setError(err?.message || "Failed to load market movers");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMarketMovers();
  }, [limit]);

  const handleRefresh = () => {
    fetchMarketMovers();
  };

  const handleTickerClick = (ticker: string) => {
    if (onTickerClick) {
      onTickerClick(ticker);
    }
  };

  // Render single mover item
  const renderMoverItem = (mover: MarketMover, index: number) => {
    const price = parseNumericString(mover.price);
    const changeAmount = parseFloat(mover.change_amount);
    const changePercent = mover.change_percentage;
    const volume = parseNumericString(mover.volume);

    const isPositive = changeAmount >= 0;
    const colorClass = isPositive ? "text-green-600" : "text-red-600";
    const bgClass = isPositive ? "bg-green-50" : "bg-red-50";

    return (
      <div
        key={`${mover.ticker}-${index}`}
        className="flex items-center justify-between p-3 hover:bg-gray-50 rounded-lg transition-colors"
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {/* Rank */}
          <span className="text-xs font-medium text-gray-500 w-6">
            #{index + 1}
          </span>

          {/* Ticker */}
          <button
            onClick={() => handleTickerClick(mover.ticker)}
            className="font-semibold text-gray-900"
          >
            {mover.ticker}
          </button>

          {/* Price */}
          <span className="text-sm text-gray-700">${price.toFixed(2)}</span>
        </div>

        {/* Change */}
        <div className="flex items-center gap-2">
          {activeTab !== "active" && (
            <div className={`flex items-center gap-1 ${bgClass} px-2 py-1 rounded`}>
              {isPositive ? (
                <TrendingUp className={`h-3 w-3 ${colorClass}`} />
              ) : (
                <TrendingDown className={`h-3 w-3 ${colorClass}`} />
              )}
              <span className={`text-xs font-medium ${colorClass}`}>
                {changePercent}
              </span>
            </div>
          )}

          {/* Volume for active tab */}
          {activeTab === "active" && (
            <div className="bg-blue-50 px-2 py-1 rounded">
              <span className="text-xs font-medium text-blue-700">
                {formatLargeNumber(volume)}
              </span>
            </div>
          )}
        </div>
      </div>
    );
  };

  // Tab button component
  const TabButton = ({
    tab,
    label,
    icon,
    count,
  }: {
    tab: CategoryTab;
    label: string;
    icon: React.ReactNode;
    count: number;
  }) => (
    <button
      onClick={() => setActiveTab(tab)}
      className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-colors ${
        activeTab === tab
          ? "bg-blue-100 text-blue-700"
          : "bg-gray-100 text-gray-700 hover:bg-gray-200"
      }`}
    >
      {icon}
      <span>{label}</span>
      <span
        className={`px-1.5 py-0.5 rounded text-xs ${
          activeTab === tab ? "bg-blue-200" : "bg-gray-200"
        }`}
      >
        {count}
      </span>
    </button>
  );

  // Get current data based on active tab
  const getCurrentData = () => {
    switch (activeTab) {
      case "gainers":
        return gainers;
      case "losers":
        return losers;
      case "active":
        return active;
      default:
        return [];
    }
  };

  return (
    <div className={`bg-white border border-gray-200 rounded-lg ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <h3 className="text-lg font-semibold text-gray-900">{t("market:movers.title")}</h3>
        <button
          onClick={handleRefresh}
          disabled={loading}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          aria-label={t("market:movers.refreshAriaLabel")}
        >
          <RefreshCw
            className={`h-4 w-4 text-gray-600 ${loading ? "animate-spin" : ""}`}
          />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 px-4 py-3 bg-gray-50 border-b border-gray-200 overflow-x-auto">
        <TabButton
          tab="gainers"
          label={t("market:movers.topGainers")}
          icon={<TrendingUp className="h-4 w-4" />}
          count={gainers.length}
        />
        <TabButton
          tab="losers"
          label={t("market:movers.topLosers")}
          icon={<TrendingDown className="h-4 w-4" />}
          count={losers.length}
        />
        <TabButton
          tab="active"
          label={t("market:movers.mostActive")}
          icon={<Activity className="h-4 w-4" />}
          count={active.length}
        />
      </div>

      {/* Content */}
      <div className="p-4">
        {/* Loading State */}
        {loading && (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
            <span className="ml-3 text-sm text-gray-600">
              {t("market:movers.loadingMovers")}
            </span>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-red-800">
                {t("market:movers.failedToLoad")}
              </p>
              <p className="text-xs text-red-700 mt-1">{error}</p>
            </div>
          </div>
        )}

        {/* Success State */}
        {!loading && !error && (
          <div>
            {getCurrentData().length > 0 ? (
              <div className="max-h-[280px] overflow-y-auto space-y-1 scrollbar-thin scrollbar-thumb-gray-300 scrollbar-track-gray-100">
                {getCurrentData().map((mover, index) =>
                  renderMoverItem(mover, index),
                )}
              </div>
            ) : (
              <div className="text-center py-8">
                <Activity className="h-12 w-12 mx-auto text-gray-400 mb-3" />
                <p className="text-sm text-gray-600">{t("market:movers.noData")}</p>
              </div>
            )}

            {/* Footer */}
            {lastUpdated && getCurrentData().length > 0 && (
              <div className="text-xs text-gray-500 text-center mt-4 pt-4 border-t border-gray-200">
                {t("market:movers.lastUpdated", { time: formatTime(lastUpdated, i18n.language) })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
