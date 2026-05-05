/**
 * Market Insights Page.
 * Displays AI-powered market analysis with transparent explanations.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ChevronRight,
  RefreshCw,
  TrendingUp,
} from "lucide-react";

import {
  CompositeScoreCard,
  CompositeScoreCardSkeleton,
  MetricCard,
  MetricCardSkeleton,
} from "../components/insights";
import { useCategories, useCategory, useInsightTrend, useRefreshCategory } from "../hooks/useInsights";
import { formatTimestamp } from "../utils/timeFormatter";

/** Available days options for trend history */
const DAYS_OPTIONS = [30, 60, 90] as const;

/** Category detail view */
function CategoryDetail({
  categoryId,
  onBack,
}: {
  categoryId: string;
  onBack: () => void;
}) {
  const { t, i18n } = useTranslation(["insights", "common"]);
  const { data: category, isLoading, isError } = useCategory(categoryId);
  const refreshMutation = useRefreshCategory();
  const [expandedMetrics, setExpandedMetrics] = useState<Set<string>>(new Set());
  const [trendDays, setTrendDays] = useState<number>(30);

  // Fetch trend data for sparklines
  const { data: trendData, isLoading: trendLoading } = useInsightTrend(categoryId, trendDays);

  const toggleMetric = (metricId: string) => {
    setExpandedMetrics((prev) => {
      const next = new Set(prev);
      if (next.has(metricId)) {
        next.delete(metricId);
      } else {
        next.add(metricId);
      }
      return next;
    });
  };

  // Handle swipe for more history
  const handleLoadMoreHistory = () => {
    const currentIndex = DAYS_OPTIONS.indexOf(trendDays as typeof DAYS_OPTIONS[number]);
    if (currentIndex < DAYS_OPTIONS.length - 1) {
      setTrendDays(DAYS_OPTIONS[currentIndex + 1]);
    }
  };

  // Get trend data for a specific metric
  const getMetricTrend = (metricId: string) => {
    if (!trendData?.metrics) return undefined;
    return trendData.metrics[metricId];
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <CompositeScoreCardSkeleton />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <MetricCardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !category) {
    return (
      <div className="p-6 bg-red-50 border border-red-200 rounded-xl text-red-700 flex items-center gap-2">
        <AlertCircle className="w-5 h-5" />
        {t("insights:errors.load_failed")}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with back button */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <button
            onClick={onBack}
            className="p-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
            aria-label={t("common:buttons.back")}
          >
            <ChevronRight className="w-5 h-5 rotate-180" />
          </button>
          <div>
            <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
              <span className="text-2xl">{category.icon}</span>
              {category.name}
            </h2>
            <p className="text-sm text-gray-600 mt-1">{category.description}</p>
          </div>
        </div>
        <button
          onClick={() => refreshMutation.mutate(categoryId)}
          disabled={refreshMutation.isPending}
          className="px-4 py-2.5 text-sm font-medium bg-white border border-gray-200 rounded-xl hover:bg-gray-50 hover:border-gray-300 transition-all flex items-center gap-2 disabled:opacity-50 shadow-sm"
        >
          <RefreshCw
            className={`w-4 h-4 ${refreshMutation.isPending ? "animate-spin" : ""}`}
          />
          {refreshMutation.isPending
            ? t("insights:category.refreshing")
            : t("insights:category.refresh")}
        </button>
      </div>

      {/* Composite score card */}
      {category.composite && (
        <CompositeScoreCard
          composite={category.composite}
          trendData={trendData?.trend}
          trendLoading={trendLoading}
        />
      )}

      {/* Metrics list */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
          {t("insights:category.metrics")}
          <span className="text-sm font-normal text-gray-500">
            ({category.metrics.length})
          </span>
        </h3>
        <div className="space-y-3">
          {category.metrics.map((metric) => (
            <MetricCard
              key={metric.id}
              metric={metric}
              isExpanded={expandedMetrics.has(metric.id)}
              onToggle={() => toggleMetric(metric.id)}
              trendData={getMetricTrend(metric.id)}
              trendLoading={trendLoading}
              onLoadMoreHistory={
                trendDays < 90 ? handleLoadMoreHistory : undefined
              }
            />
          ))}
        </div>
      </div>

      {/* Last updated footer */}
      <div className="text-xs text-gray-500 text-right pt-4 border-t border-gray-100">
        {t("insights:category.last_updated")}:{" "}
        {formatTimestamp(category.last_updated, i18n.language)}
      </div>
    </div>
  );
}

/** Category card for the listing view */
function CategoryListCard({
  name,
  icon,
  description,
  metricCount,
  onClick,
}: {
  name: string;
  icon: string;
  description: string;
  metricCount: number;
  onClick: () => void;
}) {
  const { t } = useTranslation(["insights"]);

  return (
    <button
      onClick={onClick}
      className="w-full bg-white/80 border border-gray-200/50 rounded-xl p-6 text-left hover:shadow-lg hover:shadow-blue-100/50 hover:border-blue-200/50 hover:scale-[1.01] transition-all duration-200 group"
    >
      <div className="flex items-start gap-4">
        <div className="text-4xl p-2 bg-gray-50 rounded-xl group-hover:bg-blue-50 transition-colors">
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
            {name}
          </h3>
          <p className="text-sm text-gray-600 mt-1 line-clamp-2">{description}</p>
          <div className="mt-3 flex items-center gap-2 text-xs text-gray-500">
            <TrendingUp className="w-4 h-4" />
            <span>{metricCount} {t("insights:category.metrics").toLowerCase()}</span>
          </div>
        </div>
        <ChevronRight className="w-5 h-5 text-gray-400 group-hover:text-blue-500 group-hover:translate-x-1 transition-all flex-shrink-0 mt-2" />
      </div>
    </button>
  );
}

/** Skeleton for category card */
function CategoryListCardSkeleton() {
  return (
    <div className="bg-white/80 border border-gray-200/50 rounded-xl p-6 animate-pulse">
      <div className="flex items-start gap-4">
        <div className="w-16 h-16 bg-gray-200 rounded-xl" />
        <div className="flex-1 space-y-3">
          <div className="h-5 w-1/3 bg-gray-200 rounded" />
          <div className="h-4 w-2/3 bg-gray-200 rounded" />
          <div className="h-3 w-1/4 bg-gray-200 rounded" />
        </div>
        <div className="w-5 h-5 bg-gray-200 rounded" />
      </div>
    </div>
  );
}

/** Main insights page component */
export default function InsightsPage() {
  const { t } = useTranslation(["insights", "common"]);
  const { data: categoriesData, isLoading, isError } = useCategories();
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  // Show category detail view if selected
  if (selectedCategory) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 py-8">
        <div className="max-w-5xl mx-auto px-4 sm:px-6">
          <CategoryDetail
            categoryId={selectedCategory}
            onBack={() => setSelectedCategory(null)}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 py-8">
      <div className="max-w-5xl mx-auto px-4 sm:px-6">
        {/* Page header */}
        <div className="mb-8">
          <h1 className="text-2xl sm:text-3xl font-bold bg-gradient-to-r from-gray-900 via-blue-900 to-indigo-900 bg-clip-text text-transparent mb-2">
            {t("insights:page.title")}
          </h1>
          <p className="text-gray-600">{t("insights:page.description")}</p>
        </div>

        {/* Categories list */}
        <div>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            {t("insights:categories.title")}
          </h2>

          {isLoading && (
            <div className="space-y-4">
              {[1, 2].map((i) => (
                <CategoryListCardSkeleton key={i} />
              ))}
            </div>
          )}

          {isError && (
            <div className="p-6 bg-red-50 border border-red-200 rounded-xl text-red-700 flex items-center gap-2">
              <AlertCircle className="w-5 h-5" />
              {t("insights:errors.load_failed")}
            </div>
          )}

          {categoriesData && categoriesData.categories.length === 0 && (
            <div className="p-8 bg-gray-50 border border-gray-200 rounded-xl text-gray-600 text-center">
              <TrendingUp className="w-12 h-12 mx-auto mb-3 text-gray-400" />
              {t("insights:categories.empty")}
            </div>
          )}

          {categoriesData && categoriesData.categories.length > 0 && (
            <div className="grid gap-4">
              {categoriesData.categories.map((cat) => (
                <CategoryListCard
                  key={cat.id}
                  name={cat.name}
                  icon={cat.icon}
                  description={cat.description}
                  metricCount={cat.metric_count}
                  onClick={() => setSelectedCategory(cat.id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
