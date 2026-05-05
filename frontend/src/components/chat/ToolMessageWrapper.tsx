/**
 * ToolMessageWrapper Component
 *
 * Collapsible wrapper for tool-invoked messages with modern TailwindCSS styling.
 * Displays tool metadata (icon, title, symbol, timestamp) in header with explicit chevron.
 * Collapsed by default with smooth expand/collapse animation.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";
import type { ToolCall } from "../../types/api";
import { formatTimestamp } from "../../utils/timeFormatter";

interface ToolMessageWrapperProps {
  toolCall: ToolCall;
  content: React.ReactNode;
  className?: string;
}

export function ToolMessageWrapper({
  toolCall,
  content,
  className = "",
}: ToolMessageWrapperProps) {
  const { t, i18n } = useTranslation(['chat', 'common']);
  const [isExpanded, setIsExpanded] = useState(false);

  const formattedTime = formatTimestamp(toolCall.invoked_at, i18n.language, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div
      className={`group rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden transition-all duration-200 ${className}`}
    >
      {/* Header - Clickable for expand/collapse */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-3 px-4 py-3 bg-gray-50 dark:bg-gray-800/50 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors duration-150"
        aria-expanded={isExpanded}
        aria-label={isExpanded ? t('chat:tools.collapse', { title: toolCall.title }) : t('chat:tools.expand', { title: toolCall.title })}
      >
        {/* Chevron Icon - Explicit expand indicator */}
        <ChevronRight
          className={`w-4 h-4 text-gray-500 dark:text-gray-400 transition-transform duration-200 flex-shrink-0 ${
            isExpanded ? "rotate-90" : ""
          }`}
        />

        {/* Tool Icon */}
        <span className="text-xl flex-shrink-0" aria-label={t('chat:tools.toolIcon')}>
          {toolCall.icon}
        </span>

        {/* Tool Title */}
        <span className="font-semibold text-gray-900 dark:text-gray-100 flex-shrink-0">
          {toolCall.title}
        </span>

        {/* Symbol (if available) */}
        {toolCall.symbol && (
          <span className="px-2 py-0.5 text-xs font-mono font-bold bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded flex-shrink-0">
            {toolCall.symbol}
          </span>
        )}

        {/* Timestamp */}
        <span className="ml-auto text-sm text-gray-500 dark:text-gray-400 flex-shrink-0">
          {formattedTime}
        </span>
      </button>

      {/* Content - Collapsible with smooth animation */}
      <div
        className={`overflow-hidden transition-all duration-200 ${
          isExpanded ? "max-h-[10000px] opacity-100" : "max-h-0 opacity-0"
        }`}
      >
        <div className="px-4 py-4 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
          {content}
        </div>
      </div>
    </div>
  );
}
