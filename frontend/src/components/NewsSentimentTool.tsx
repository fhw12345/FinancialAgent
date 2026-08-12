/**
 * News Sentiment Tool Component
 *
 * Displays news articles with sentiment analysis in a collapsible UI.
 * Features:
 * - Visual sentiment scores (color-coded)
 * - Grouped by positive/negative sentiment
 * - Max 3 positive + 3 negative articles
 * - Clickable links to source articles
 * - Timestamp and source information
 */

import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Newspaper,
  TrendingUp,
  TrendingDown,
  ExternalLink,
} from "lucide-react";
import { ToolWrapper } from "./ToolWrapper";
import { alphaVantageApi } from "../services/alphaVantageApi";
import type { NewsFeedItem } from "../types/alphaVantage";
import {
  getSentimentColor,
  getSentimentBgColor,
  formatAVTimestamp,
} from "../types/alphaVantage";

interface NewsSentimentToolProps {
  /** Stock ticker symbol */
  symbol: string;

  /** Maximum positive articles to display (default: 3) */
  maxPositive?: number;

  /** Maximum negative articles to display (default: 3) */
  maxNegative?: number;

  /** Initial expanded state (default: false) */
  defaultExpanded?: boolean;

  /** Optional className */
  className?: string;
}

export const NewsSentimentTool: React.FC<NewsSentimentToolProps> = ({
  symbol,
  maxPositive = 3,
  maxNegative = 3,
  defaultExpanded = false,
  className = "",
}) => {
  const { t } = useTranslation(["market", "common"]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [positive, setPositive] = useState<NewsFeedItem[]>([]);
  const [negative, setNegative] = useState<NewsFeedItem[]>([]);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    const fetchNews = async () => {
      try {
        setLoading(true);
        setError(null);

        const response = await alphaVantageApi.getNewsSentiment(symbol, {
          limit: 50,
          sort: "LATEST",
        });

        const filtered = alphaVantageApi.filterNewsSentiment(
          response,
          maxPositive,
          maxNegative,
        );

        setPositive(filtered.positive);
        setNegative(filtered.negative);
        setTotal(filtered.total);
      } catch (error: unknown) {
        console.error("Failed to fetch news sentiment:", error);
        setError(
          error instanceof Error
            ? error.message
            : "Failed to load news sentiment",
        );
      } finally {
        setLoading(false);
      }
    };

    fetchNews();
  }, [symbol, maxPositive, maxNegative]);

  // Render sentiment score badge
  const renderSentimentBadge = (score: number) => {
    const color = getSentimentColor(score);
    const bgColor = getSentimentBgColor(score);

    return (
      <span
        className={`inline-flex items-center px-2 py-1 rounded border ${bgColor} ${color} font-mono text-xs font-medium`}
      >
        {score > 0 ? "+" : ""}
        {score.toFixed(2)}
      </span>
    );
  };

  // Render single news item
  const renderNewsItem = (item: NewsFeedItem, index: number) => {
    return (
      <div
        key={index}
        className="border-b border-gray-100 last:border-b-0 py-3 first:pt-0 last:pb-0"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            {/* Title */}
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-medium text-gray-900 hover:text-blue-600 hover:underline flex items-center gap-1.5 group"
            >
              <span className="line-clamp-2">{item.title}</span>
              <ExternalLink className="h-3 w-3 text-gray-400 group-hover:text-blue-600 flex-shrink-0" />
            </a>

            {/* Summary */}
            <p className="text-xs text-gray-600 mt-1 line-clamp-2">
              {item.summary}
            </p>

            {/* Metadata */}
            <div className="flex items-center gap-2 mt-2 text-xs text-gray-500">
              <span className="font-medium">{item.source}</span>
              <span>•</span>
              <span>{formatAVTimestamp(item.time_published)}</span>
            </div>
          </div>

          {/* Sentiment Score */}
          <div className="flex-shrink-0">
            {renderSentimentBadge(item.overall_sentiment_score)}
          </div>
        </div>
      </div>
    );
  };

  // Badge text for header
  const badgeText =
    positive.length > 0 || negative.length > 0
      ? `${t("market:news.positiveBadge", { count: positive.length })}, ${t("market:news.negativeBadge", { count: negative.length })}`
      : undefined;

  return (
    <ToolWrapper
      title={t("market:news.sentimentTitle", { symbol })}
      icon={<Newspaper className="h-5 w-5" />}
      badge={badgeText}
      badgeVariant={positive.length > negative.length ? "success" : "default"}
      defaultExpanded={defaultExpanded}
      className={className}
    >
      {/* Loading State */}
      {loading && (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
          <span className="ml-3 text-sm text-gray-600">
            {t("market:news.loading")}
          </span>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-center">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      {/* Success State */}
      {!loading && !error && (
        <div className="space-y-4">
          {/* Positive Sentiment News */}
          {positive.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp className="h-4 w-4 text-green-600" />
                <h4 className="text-sm font-semibold text-green-800">
                  {t("market:news.positiveSentiment", {
                    count: positive.length,
                  })}
                </h4>
              </div>
              <div className="bg-green-50 border border-green-200 rounded-lg p-3 space-y-3">
                {positive.map((item, index) => renderNewsItem(item, index))}
              </div>
            </div>
          )}

          {/* Negative Sentiment News */}
          {negative.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <TrendingDown className="h-4 w-4 text-red-600" />
                <h4 className="text-sm font-semibold text-red-800">
                  {t("market:news.negativeSentiment", {
                    count: negative.length,
                  })}
                </h4>
              </div>
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 space-y-3">
                {negative.map((item, index) => renderNewsItem(item, index))}
              </div>
            </div>
          )}

          {/* No Results */}
          {positive.length === 0 && negative.length === 0 && (
            <div className="text-center py-8">
              <Newspaper className="h-12 w-12 mx-auto text-gray-400 mb-3" />
              <p className="text-sm text-gray-600">
                {t("market:news.noSentimentNews", { symbol })}
              </p>
              {total > 0 && (
                <p className="text-xs text-gray-500 mt-1">
                  {t("market:news.totalScanned", { count: total })}
                </p>
              )}
            </div>
          )}

          {/* Footer Info */}
          {(positive.length > 0 || negative.length > 0) && (
            <div className="text-xs text-gray-500 text-center pt-2 border-t border-gray-200">
              {t("market:news.showingArticles", {
                shown: positive.length + negative.length,
                total,
              })}
            </div>
          )}
        </div>
      )}
    </ToolWrapper>
  );
};
