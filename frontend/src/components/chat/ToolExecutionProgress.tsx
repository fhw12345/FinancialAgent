/**
 * ToolExecutionProgress Component
 *
 * Real-time progress indicator for agent tool executions.
 * Displays tool status (running, success, error) with animated progress bar.
 *
 * Used during agent mode (v3) to show which tools are being called
 * and their execution status in real-time.
 */

import { CheckCircle, XCircle, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

export interface ToolExecutionProgressProps {
  toolName: string;
  displayName: string;
  icon: string;
  status: "running" | "success" | "error" | "cancelled";
  symbol?: string;
  inputs?: Record<string, unknown>;
  output?: string;
  error?: string;
  durationMs?: number;
}

/**
 * Map tool names to user-friendly display names.
 * Fallback to titleized tool_name if not in map.
 */
const DEFAULT_TOOL_METADATA: Record<
  string,
  { displayName: string; icon: string }
> = {
  search_ticker: { displayName: "Search Ticker", icon: "🔍" },
  get_company_overview: { displayName: "Company Overview", icon: "🏢" },
  get_news_sentiment: { displayName: "News Sentiment", icon: "📰" },
  get_financial_statements: { displayName: "Financial Statements", icon: "📊" },
  get_market_movers: { displayName: "Market Movers", icon: "📈" },
  fibonacci_analysis_tool: { displayName: "Fibonacci Analysis", icon: "📐" },
  stochastic_analysis_tool: { displayName: "Stochastic Analysis", icon: "📉" },
};

export function ToolExecutionProgress({
  displayName,
  icon,
  status,
  symbol,
  output,
  error,
  durationMs,
}: ToolExecutionProgressProps) {
  const { t } = useTranslation(["chat", "common"]);
  // Get status icon and color
  const StatusIcon = {
    running: Loader2,
    success: CheckCircle,
    error: XCircle,
    cancelled: XCircle,
  }[status];

  const statusColor = {
    running: "text-blue-500",
    success: "text-green-500",
    error: "text-red-500",
    cancelled: "text-amber-500",
  }[status];

  const bgColor = {
    running: "bg-blue-50 dark:bg-blue-900/10",
    success: "bg-green-50 dark:bg-green-900/10",
    error: "bg-red-50 dark:bg-red-900/10",
    cancelled: "bg-amber-50 dark:bg-amber-900/10",
  }[status];

  const borderColor = {
    running: "border-blue-200 dark:border-blue-800",
    success: "border-green-200 dark:border-green-800",
    error: "border-red-200 dark:border-red-800",
    cancelled: "border-amber-200 dark:border-amber-800",
  }[status];

  // Format duration
  const formattedDuration = durationMs
    ? durationMs < 1000
      ? `${durationMs}ms`
      : `${(durationMs / 1000).toFixed(1)}s`
    : null;

  return (
    <div
      className={`rounded-lg border ${borderColor} ${bgColor} overflow-hidden transition-all duration-200 mb-2`}
    >
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3">
        {/* Tool Icon */}
        <span className="text-xl flex-shrink-0" aria-label="Tool icon">
          {icon}
        </span>

        {/* Tool Name */}
        <span className="font-semibold text-gray-900 dark:text-gray-100 flex-shrink-0">
          {displayName}
        </span>

        {/* Symbol Badge (if available) */}
        {symbol && (
          <span className="px-2 py-0.5 text-xs font-mono font-bold bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded flex-shrink-0">
            {symbol}
          </span>
        )}

        {/* Status Icon */}
        <StatusIcon
          className={`w-5 h-5 ${statusColor} flex-shrink-0 ml-auto ${
            status === "running" ? "animate-spin" : ""
          }`}
        />

        {/* Duration (if completed) */}
        {formattedDuration && (
          <span className="text-sm text-gray-500 dark:text-gray-400 flex-shrink-0">
            {formattedDuration}
          </span>
        )}
      </div>

      {/* Progress Bar (only for running status) */}
      {status === "running" && (
        <div className="px-4 pb-3">
          <div className="h-1 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 dark:bg-blue-400 animate-pulse transition-all duration-300"
              style={{ width: "70%" }}
            />
          </div>
        </div>
      )}

      {/* Output Preview (collapsed, for success) */}
      {status === "success" && output && (
        <details className="border-t border-gray-200 dark:border-gray-700">
          <summary className="px-4 py-2 cursor-pointer text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
            {t("chat:tools.viewResultPreview")}
          </summary>
          <div className="px-4 py-3 bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700">
            <pre className="text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap font-mono overflow-x-auto">
              {output}
            </pre>
          </div>
        </details>
      )}

      {/* Error Message (for error status) */}
      {status === "error" && error && (
        <div className="px-4 py-3 border-t border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20">
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}
      {status === "cancelled" && error && (
        <div className="border-t border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-800 dark:bg-amber-900/20">
          <p className="text-sm text-amber-700 dark:text-amber-300">{error}</p>
        </div>
      )}
    </div>
  );
}

/**
 * Helper function to get tool metadata from tool name.
 * Used when backend doesn't provide display_name/icon in event.
 */
export function getToolMetadata(toolName: string): {
  displayName: string;
  icon: string;
} {
  return (
    DEFAULT_TOOL_METADATA[toolName] || {
      displayName: toolName
        .replace(/_/g, " ")
        .replace(/\b\w/g, (l) => l.toUpperCase()),
      icon: "🔧",
    }
  );
}
