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
  const isRunning = status === "running";
  const isSuccess = status === "success";
  const isCancelled = status === "cancelled";
  const StatusIcon = isRunning ? Loader2 : isSuccess ? CheckCircle : XCircle;
  const statusColor = isRunning
    ? "text-blue-500"
    : isSuccess
      ? "text-green-500"
      : isCancelled
        ? "text-amber-500"
        : "text-red-500";
  const bgColor = isRunning
    ? "bg-blue-50 dark:bg-blue-900/10"
    : isSuccess
      ? "bg-green-50 dark:bg-green-900/10"
      : isCancelled
        ? "bg-amber-50 dark:bg-amber-900/10"
        : "bg-red-50 dark:bg-red-900/10";
  const borderColor = isRunning
    ? "border-blue-200 dark:border-blue-800"
    : isSuccess
      ? "border-green-200 dark:border-green-800"
      : isCancelled
        ? "border-amber-200 dark:border-amber-800"
        : "border-red-200 dark:border-red-800";

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
